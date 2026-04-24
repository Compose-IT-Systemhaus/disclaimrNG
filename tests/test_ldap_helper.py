"""Tests for the LDAP helper used by the DirectoryServer admin endpoints.

These tests stub out :mod:`ldap` so they can run without a live directory
server. The goal is to verify the error-handling shape of the helper, not the
underlying ``python-ldap`` library.
"""

from __future__ import annotations

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


def test_discover_attributes_returns_sorted_union(server):
    conn = MagicMock()
    conn.search_ext_s.return_value = [
        ("cn=alice,dc=example,dc=com", {"cn": [b"Alice"], "mail": [b"a@x"]}),
        ("cn=bob,dc=example,dc=com", {"telephoneNumber": [b"+1"], "cn": [b"Bob"]}),
    ]
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == sorted(
        ["cn", "mail", "telephoneNumber"], key=str.lower
    )
    assert result.sample_dn.startswith("cn=alice")


def test_discover_attributes_skips_referrals(server):
    conn = MagicMock()
    conn.search_ext_s.return_value = [
        (None, ["ldap://referral.example.com"]),  # referral entries have dn=None
        ("cn=carol,dc=example,dc=com", {"sn": [b"Smith"]}),
    ]
    with patch.object(ldap_helper.ldap, "initialize", return_value=conn):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == ["sn"]
    assert result.sample_dn.startswith("cn=carol")


def test_discover_attributes_falls_through_on_error(server):
    def _initialize(url):
        m = MagicMock()
        if "primary" in url:
            m.simple_bind_s.side_effect = ldap.LDAPError("boom")
        else:
            m.search_ext_s.return_value = [
                ("cn=dan,dc=example,dc=com", {"mail": [b"d@x"]}),
            ]
        return m

    with patch.object(ldap_helper.ldap, "initialize", side_effect=_initialize):
        result = ldap_helper.discover_attributes(server)
    assert result.ok is True
    assert result.attributes == ["mail"]
