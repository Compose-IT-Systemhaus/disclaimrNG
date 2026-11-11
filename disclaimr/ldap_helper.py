"""LDAP helpers for the disclaimrNG admin UI.

Used by the directory-server admin to power the "test connection" and
"discover attributes" buttons. The milter pipeline does its own bind/search
via :mod:`disclaimr.milter_helper` — this module is purely for the
interactive admin experience.
"""

from __future__ import annotations

import hashlib
import os
import socket
import ssl
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import ldap

from disclaimrwebadmin import constants

if TYPE_CHECKING:  # pragma: no cover
    from disclaimrwebadmin.models import DirectoryServer


@dataclass
class URLProbe:
    url: str
    ok: bool
    detail: str = ""


@dataclass
class TestResult:
    """Outcome of a connection test against all of a server's URLs."""

    ok: bool
    probes: list[URLProbe] = field(default_factory=list)
    summary: str = ""


@dataclass
class AttributeDiscoveryResult:
    """Outcome of an attribute discovery query."""

    ok: bool
    attributes: list[str] = field(default_factory=list)
    sample_dn: str = ""
    detail: str = ""


# Bound, network-level timeouts so an unreachable LDAP server can never hang the milter
# (or a synchronous admin view) for more than a few seconds; python-ldap's default is
# no limit, which used to take down gunicorn workers.
LDAP_TIMEOUT = 5


def _ca_file(pem: str) -> str:
    """Path of a file holding ``pem``: libldap only reads CA certificates from files.

    Named after the content, so every process and worker shares one file per CA.
    """
    digest = hashlib.sha256(pem.encode()).hexdigest()
    path = Path(tempfile.gettempdir()) / "disclaimr-ldap-ca" / f"{digest[:16]}.pem"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        scratch = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        scratch.write_text(pem)
        scratch.replace(path)  # atomic: a concurrent reader never sees a half-written file
    return str(path)


def open_connection(url: str, directory_server: DirectoryServer | None = None):
    """Return an unbound connection to ``url`` with the project's options.

    ``ldaps://`` is verified against the CA certificate stored on the directory
    server; without one, against the container's CA store (``LDAPTLS_CACERT`` is set
    by the entrypoint). Active Directory answers subtree searches on the domain root
    with referrals; chasing them (anonymously) only costs time.
    """
    conn = ldap.initialize(url)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, LDAP_TIMEOUT)
    conn.set_option(ldap.OPT_TIMEOUT, LDAP_TIMEOUT)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    pem = directory_server.ca_certificate if directory_server else ""
    if pem and url.lower().startswith("ldaps://"):
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
        conn.set_option(ldap.OPT_X_TLS_CACERTFILE, _ca_file(pem))
        # libldap applies pending TLS options only now; must be the last TLS option.
        conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
    return conn


def _bind(directory_server: DirectoryServer, url: str):
    """Open a connection to ``url`` and bind using the server's credentials."""
    conn = open_connection(url, directory_server)

    bind_dn = ""
    bind_pw = ""
    if directory_server.auth == constants.DIR_AUTH_SIMPLE:
        bind_dn = directory_server.userdn
        bind_pw = directory_server.password

    conn.simple_bind_s(bind_dn, bind_pw)
    return conn


# OpenSSL verify codes for a certificate that is fine but issued for another name / IP.
_NAME_MISMATCH = {62, 64}


def tls_problem(directory_server: DirectoryServer, url: str) -> str | None:
    """Why an ``ldaps://`` connection fails, in words — or ``None`` if TLS itself works.

    libldap reports every TLS failure as "Can't contact LDAP server". This repeats the
    handshake with Python's ``ssl`` and the same trust (the server's stored CA, else
    ``LDAPTLS_CACERT``, else the system store) to name the cause.
    """
    parts = urlsplit(url)
    host, port = parts.hostname or "", parts.port or 636
    pem = directory_server.ca_certificate
    try:
        if pem:
            context = ssl.create_default_context(cadata=pem)
        else:
            context = ssl.create_default_context(cafile=os.environ.get("LDAPTLS_CACERT"))
    except (ssl.SSLError, ValueError, OSError) as exc:
        return f"the CA certificate cannot be used: {exc}"
    try:
        sock = socket.create_connection((host, port), LDAP_TIMEOUT)
    except OSError as exc:
        return f"port {port} on {host} not reachable: {exc}"
    try:
        with context.wrap_socket(sock, server_hostname=host):
            return None
    except ssl.SSLCertVerificationError as exc:
        if exc.verify_code in _NAME_MISMATCH:
            return (
                f"the certificate is not issued for {host} — enter the host name from the "
                "certificate (not the IP address)"
            )
        return (
            f"certificate not trusted ({exc.verify_message}) — upload the certificate of "
            "the CA that issued the server certificate"
        )
    except (ssl.SSLError, OSError) as exc:
        return f"TLS handshake failed: {exc}"
    finally:
        sock.close()


def test_connection(
    directory_server: DirectoryServer, urls: list[str] | None = None
) -> TestResult:
    """Try to bind to every URL and report the result of each.

    ``urls`` defaults to the saved ones; the admin passes those of an unsaved form.
    """
    if urls is None:
        urls = [
            u.url for u in directory_server.directoryserverurl_set.order_by("position")
        ]
    if not urls:
        return TestResult(ok=False, summary="No URLs configured.")

    probes: list[URLProbe] = []
    for url in urls:
        try:
            conn = _bind(directory_server, url)
        except ldap.SERVER_DOWN as exc:
            problem = tls_problem(directory_server, url) if url.lower().startswith("ldaps://") else None
            probes.append(URLProbe(url=url, ok=False, detail=problem or f"unreachable: {exc}"))
            continue
        except ldap.INVALID_CREDENTIALS:
            probes.append(URLProbe(url=url, ok=False, detail="invalid credentials"))
            continue
        except ldap.LDAPError as exc:
            probes.append(URLProbe(url=url, ok=False, detail=f"ldap error: {exc}"))
            continue

        try:
            conn.search_s(directory_server.base_dn, ldap.SCOPE_BASE, "(objectClass=*)")
            probes.append(URLProbe(url=url, ok=True, detail="bind + base search ok"))
        except ldap.NO_SUCH_OBJECT:
            probes.append(
                URLProbe(url=url, ok=False, detail="base DN not found")
            )
        except ldap.LDAPError as exc:
            probes.append(URLProbe(url=url, ok=False, detail=f"search error: {exc}"))
        finally:
            try:
                conn.unbind_s()
            except ldap.LDAPError:
                pass

    overall = any(p.ok for p in probes)
    if overall:
        ok_count = sum(1 for p in probes if p.ok)
        summary = f"{ok_count}/{len(probes)} URL(s) reachable."
    else:
        summary = "All URLs failed."
    return TestResult(ok=overall, probes=probes, summary=summary)


def discover_attributes(
    directory_server: DirectoryServer, sample_size: int = 5
) -> AttributeDiscoveryResult:
    """Sample ``sample_size`` entries from the directory and union their attribute names.

    The returned list is what gets surfaced as autocomplete vocabulary in the
    template editor. We don't read the schema directly — schema lookups need
    extra privileges on AD and produce a flood of attributes admins don't
    care about. Sampling real entries gives a more useful list.
    """
    urls = list(directory_server.directoryserverurl_set.order_by("position"))
    if not urls:
        return AttributeDiscoveryResult(ok=False, detail="No URLs configured.")

    last_error = ""
    for entry in urls:
        url = entry.url
        try:
            conn = _bind(directory_server, url)
        except ldap.LDAPError as exc:
            last_error = f"{url}: {exc}"
            continue

        try:
            results = conn.search_ext_s(
                directory_server.base_dn,
                ldap.SCOPE_SUBTREE,
                "(objectClass=*)",
                sizelimit=sample_size,
            )
        except ldap.SIZELIMIT_EXCEEDED as exc:
            results = getattr(exc, "args", [{}])[0].get("results", [])
        except ldap.NO_SUCH_OBJECT:
            last_error = f"{url}: base DN not found"
            conn.unbind_s()
            continue
        except ldap.LDAPError as exc:
            last_error = f"{url}: {exc}"
            try:
                conn.unbind_s()
            except ldap.LDAPError:
                pass
            continue

        attrs: set[str] = set()
        sample_dn = ""
        for dn, values in results:
            if dn is None:  # skip referral chasings
                continue
            if not sample_dn:
                sample_dn = dn
            attrs.update(values.keys())

        try:
            conn.unbind_s()
        except ldap.LDAPError:
            pass

        if attrs:
            return AttributeDiscoveryResult(
                ok=True,
                attributes=sorted(attrs, key=str.lower),
                sample_dn=sample_dn,
            )
        last_error = f"{url}: search returned no entries"

    return AttributeDiscoveryResult(ok=False, detail=last_error or "All URLs failed.")
