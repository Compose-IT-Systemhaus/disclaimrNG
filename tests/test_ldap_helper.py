"""Tests for the LDAP helper used by the DirectoryServer admin endpoints.

These tests stub out :mod:`ldap` so they can run without a live directory
server. The goal is to verify the error-handling shape of the helper, not the
underlying ``python-ldap`` library.
"""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

import ldap
import pytest

from disclaimr import ldap_helper
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer, DirectoryServerURL


@pytest.fixture
def server(db) -> DirectoryServer:
    srv = DirectoryServer.objects.create(
        name="LDAP",
        flavor=constants.DIR_FLAVOR_LDAP,
        base_dn="dc=example,dc=com",
        auth=constants.DIR_AUTH_NONE,
    )
    DirectoryServerURL.objects.create(
        directory_server=srv, url="ldap://primary", position=0
    )
    DirectoryServerURL.objects.create(
        directory_server=srv, url="ldap://secondary", position=1
    )
    return srv


def test_test_connection_with_no_urls(db):
    srv = DirectoryServer.objects.create(
        name="Empty", base_dn="dc=x,dc=y", auth=constants.DIR_AUTH_NONE
    )
    result = ldap_helper.test_connection(srv)
    assert result.ok is False
    assert "No URLs" in result.summary


def test_test_connection_first_url_succeeds(server):
    conn = MagicMock()
    conn.search_s.return_value = []
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn) as init:
        result = ldap_helper.test_connection(server)
    assert init.call_count == 2  # both URLs probed independently
    assert result.ok is True
    assert all(p.ok for p in result.probes)


def test_test_connection_handles_server_down(server):
    def _initialize(url):
        m = MagicMock()
        if "primary" in url:
            m.simple_bind_s.side_effect = ldap.SERVER_DOWN("nope")
        else:
            m.search_s.return_value = []
        return m

    with patch.object(ldap_helper.ldap, "initialize", side_effect=_initialize):
        result = ldap_helper.test_connection(server)
    assert result.ok is True  # secondary worked
    primary_probe = next(p for p in result.probes if "primary" in p.url)
    assert primary_probe.ok is False
    assert "unreachable" in primary_probe.detail


def _answers(conn, entries, *, size_limited=False):
    """Let ``conn`` hand out ``entries`` one result at a time, as python-ldap does."""
    steps = [(ldap.RES_SEARCH_ENTRY, [entry], 1, []) for entry in entries]
    steps.append(ldap.SIZELIMIT_EXCEEDED({}) if size_limited else (ldap.RES_SEARCH_RESULT, [], 1, []))
    conn.search_ext.return_value = 1
    conn.result3.side_effect = steps
    return conn


def test_discover_attributes_returns_sorted_union(server):
    conn = _answers(MagicMock(), [
        ("cn=alice,dc=example,dc=com", {"cn": [b"Alice"], "mail": [b"a@x"]}),
        ("cn=bob,dc=example,dc=com", {"telephoneNumber": [b"+1"], "cn": [b"Bob"]}),
    ])
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == sorted(
        ["cn", "mail", "telephoneNumber"], key=str.lower
    )
    assert result.sample_dn.startswith("cn=alice")
    args, kwargs = conn.search_ext.call_args
    assert args[2] == "(&(objectClass=person)(!(objectClass=computer)))" and kwargs["sizelimit"] == 5


def test_discover_attributes_keeps_the_entries_when_the_size_limit_hits(server):
    """Active Directory has more than five people: the search ends with
    SIZELIMIT_EXCEEDED, and the entries received until then must not get lost."""
    conn = _answers(
        MagicMock(),
        [(f"cn=u{i},dc=example,dc=com", {"cn": [b"x"], "department": [b"y"]}) for i in range(5)],
        size_limited=True,
    )
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == ["cn", "department"]


def test_discover_attributes_skips_referrals(server):
    conn = _answers(MagicMock(), [
        (None, ["ldap://referral.example.com"]),  # referral entries have dn=None
        ("cn=carol,dc=example,dc=com", {"sn": [b"Smith"]}),
    ])
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == ["sn"]
    assert result.sample_dn.startswith("cn=carol")


def test_discover_attributes_says_when_nobody_is_found(server):
    with patch.object(ldap_helper.ldap, "initialize", side_effect=lambda url: _answers(MagicMock(), [])):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is False
    assert "no person entries found under dc=example,dc=com" in result.detail


def test_discover_attributes_falls_through_on_error(server):
    def _initialize(url):
        m = MagicMock()
        if "primary" in url:
            m.simple_bind_s.side_effect = ldap.LDAPError("boom")
        else:
            _answers(m, [("cn=dan,dc=example,dc=com", {"mail": [b"d@x"]})])
        return m

    with patch.object(ldap_helper.ldap, "initialize", side_effect=_initialize):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == ["mail"]


# ---------------------------------------------------------------------------
# tls_problem: why an ldaps:// connection fails
# ---------------------------------------------------------------------------


def _verify_error(code: int, message: str) -> ssl.SSLCertVerificationError:
    exc = ssl.SSLCertVerificationError("certificate verify failed")
    exc.verify_code, exc.verify_message = code, message
    return exc


@pytest.fixture
def tls_server(db) -> DirectoryServer:
    return DirectoryServer.objects.create(
        name="AD", base_dn="dc=x,dc=y", auth=constants.DIR_AUTH_NONE, use_tls=True
    )


def _handshake(error=None):
    """Patch the TCP connect and let the TLS handshake raise ``error`` (or succeed)."""
    context = MagicMock()
    if error:
        context.wrap_socket.side_effect = error
    return (
        patch.object(ldap_helper.socket, "create_connection", return_value=MagicMock()),
        patch.object(ldap_helper.ssl, "create_default_context", return_value=context),
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, None),
        (_verify_error(20, "unable to get local issuer certificate"), "certificate not trusted"),
        (_verify_error(62, "hostname mismatch"), "not issued for dc1.example.com"),
        (_verify_error(64, "IP address mismatch"), "not the IP address"),
        (ssl.SSLError("handshake failure"), "TLS handshake failed"),
    ],
)
def test_tls_problem_names_the_cause(tls_server, error, expected):
    connect, context = _handshake(error)
    with connect, context:
        problem = ldap_helper.tls_problem(tls_server, "ldaps://dc1.example.com:636")
    if expected is None:
        assert problem is None
    else:
        assert expected in problem


def test_tls_problem_reports_an_unreachable_port(tls_server):
    with patch.object(
        ldap_helper.socket, "create_connection", side_effect=OSError("connection refused")
    ):
        problem = ldap_helper.tls_problem(tls_server, "ldaps://dc1.example.com")
    assert problem.startswith("port 636 on dc1.example.com not reachable")


def test_tls_problem_reports_an_unusable_ca(tls_server):
    tls_server.ca_certificate = "-----BEGIN CERTIFICATE-----\nbroken\n-----END CERTIFICATE-----"
    assert "cannot be used" in ldap_helper.tls_problem(tls_server, "ldaps://dc1")


def test_connection_test_uses_the_tls_cause_for_ldaps_only(tls_server):
    conn = MagicMock()
    conn.simple_bind_s.side_effect = ldap.SERVER_DOWN("Can't contact LDAP server")
    with (
        patch.object(ldap_helper.ldap, "initialize", return_value=conn),
        patch.object(ldap_helper, "tls_problem", return_value="certificate not trusted (x)") as tls,
    ):
        result = ldap_helper.test_connection(tls_server, ["ldaps://dc1", "ldap://dc2"])
    assert [p.detail for p in result.probes] == [
        "certificate not trusted (x)",
        "unreachable: Can't contact LDAP server",
    ]
    tls.assert_called_once_with(tls_server, "ldaps://dc1")
