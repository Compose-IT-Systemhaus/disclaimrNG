"""LDAP helpers for the disclaimrNG admin UI.

Used by the directory-server admin to power the "test connection" and
"discover attributes" buttons. The milter pipeline does its own bind/search
via :mod:`disclaimr.milter_helper` — this module is purely for the
interactive admin experience.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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


def _bind(directory_server: "DirectoryServer", url: str):
    """Open a connection to ``url`` and bind using the server's credentials."""
    conn = ldap.initialize(url)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
    conn.set_option(ldap.OPT_TIMEOUT, 5)
    conn.set_option(ldap.OPT_REFERRALS, 0)

    bind_dn = ""
    bind_pw = ""
    if directory_server.auth == constants.DIR_AUTH_SIMPLE:
        bind_dn = directory_server.userdn
        bind_pw = directory_server.password

    conn.simple_bind_s(bind_dn, bind_pw)
    return conn


def test_connection(directory_server: "DirectoryServer") -> TestResult:
    """Try to bind to every configured URL and report the result of each."""
    urls = list(directory_server.directoryserverurl_set.order_by("position"))
    if not urls:
        return TestResult(ok=False, summary="No URLs configured.")

    probes: list[URLProbe] = []
    for entry in urls:
        url = entry.url
        try:
            conn = _bind(directory_server, url)
        except ldap.SERVER_DOWN as exc:
            probes.append(URLProbe(url=url, ok=False, detail=f"unreachable: {exc}"))
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
    directory_server: "DirectoryServer", sample_size: int = 5
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
