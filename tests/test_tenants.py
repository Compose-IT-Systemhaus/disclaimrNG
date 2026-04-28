"""Tests for the multi-tenant layer.

Covers the Tenant model's sender-domain matching, the env-bootstrap
``sync_tenants`` command, the LDAP_SERVER_<H>_TENANT cross-link in
``sync_directory_servers``, and the milter's tenant fallback in
:meth:`MilterHelper._directory_servers_for`.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from disclaimr.milter_helper import MilterHelper
from disclaimrwebadmin.models import (
    Action,
    DirectoryServer,
    Disclaimer,
    Rule,
    Tenant,
    TenantDomain,
)


def _run_tenants(monkeypatch, env: dict[str, str], *args: str) -> str:
    monkeypatch.delenv("TENANTS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    out = StringIO()
    call_command("sync_tenants", *args, stdout=out)
    return out.getvalue()


def _run_servers(monkeypatch, env: dict[str, str], *args: str) -> str:
    monkeypatch.delenv("LDAP_SERVERS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    out = StringIO()
    call_command("sync_directory_servers", *args, stdout=out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Tenant.match_sender
# ---------------------------------------------------------------------------


def test_match_sender_returns_tenant_for_known_domain(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")

    found = Tenant.match_sender("alice@acme.com")
    assert found == tenant


def test_match_sender_is_case_insensitive(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")

    assert Tenant.match_sender("Alice@ACME.com") == tenant


def test_match_sender_returns_none_for_unknown_domain(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")
    assert Tenant.match_sender("bob@other.tld") is None


def test_match_sender_skips_disabled_tenant(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme", enabled=False)
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")
    assert Tenant.match_sender("alice@acme.com") is None


def test_match_sender_handles_malformed_address(db):
    Tenant.objects.create(name="Acme", slug="acme")
    assert Tenant.match_sender("no-at-sign") is None
    assert Tenant.match_sender("trailing@") is None


# ---------------------------------------------------------------------------
# sync_tenants
# ---------------------------------------------------------------------------


def test_sync_tenants_no_handles_is_a_noop(db, monkeypatch):
    output = _run_tenants(monkeypatch, {})
    assert "nothing to sync" in output
    assert Tenant.objects.count() == 0


def test_sync_tenants_creates_tenant_with_domains(db, monkeypatch):
    env = {
        "TENANTS": "acme",
        "TENANT_ACME_NAME": "Acme Corp",
        "TENANT_ACME_DOMAINS": "acme.com,acme.de",
    }
    _run_tenants(monkeypatch, env)
    tenant = Tenant.objects.get(slug="acme")
    assert tenant.name == "Acme Corp"
    domains = set(tenant.domains.values_list("domain", flat=True))
    assert domains == {"acme.com", "acme.de"}


def test_sync_tenants_rerun_updates_domains(db, monkeypatch):
    env = {
        "TENANTS": "acme",
        "TENANT_ACME_DOMAINS": "old.com",
    }
    _run_tenants(monkeypatch, env)

    env["TENANT_ACME_DOMAINS"] = "new1.com,new2.com"
    _run_tenants(monkeypatch, env)

    tenant = Tenant.objects.get(slug="acme")
    domains = set(tenant.domains.values_list("domain", flat=True))
    assert domains == {"new1.com", "new2.com"}


def test_sync_tenants_prune_removes_env_managed_only(db, monkeypatch):
    env = {
        "TENANTS": "acme,globex",
        "TENANT_ACME_DOMAINS": "acme.com",
        "TENANT_GLOBEX_DOMAINS": "globex.com",
    }
    _run_tenants(monkeypatch, env)

    Tenant.objects.create(name="Manual", slug="manual", description="hand-rolled")
    assert Tenant.objects.count() == 3

    env["TENANTS"] = "acme"
    _run_tenants(monkeypatch, env, "--prune")

    slugs = set(Tenant.objects.values_list("slug", flat=True))
    assert slugs == {"acme", "manual"}


def test_sync_tenants_dry_run_writes_nothing(db, monkeypatch):
    env = {
        "TENANTS": "acme",
        "TENANT_ACME_DOMAINS": "acme.com",
    }
    output = _run_tenants(monkeypatch, env, "--dry-run")
    assert "Dry run" in output
    assert Tenant.objects.count() == 0


# ---------------------------------------------------------------------------
# sync_directory_servers — tenant linkage
# ---------------------------------------------------------------------------


def test_directory_server_links_to_tenant_by_slug(db, monkeypatch):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=acme,dc=com",
        "LDAP_SERVER_PRIMARY_URL": "ldap://acme",
        "LDAP_SERVER_PRIMARY_TENANT": "acme",
    }
    _run_servers(monkeypatch, env)
    srv = DirectoryServer.objects.get()
    assert srv.tenant == tenant


def test_directory_server_unknown_tenant_raises(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=x,dc=y",
        "LDAP_SERVER_PRIMARY_URL": "ldap://x",
        "LDAP_SERVER_PRIMARY_TENANT": "ghost",
    }
    monkeypatch.delenv("LDAP_SERVERS", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(CommandError, match="ghost"):
        call_command("sync_directory_servers", stdout=StringIO())


def test_directory_server_no_tenant_var_leaves_link_empty(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=x,dc=y",
        "LDAP_SERVER_PRIMARY_URL": "ldap://x",
    }
    _run_servers(monkeypatch, env)
    assert DirectoryServer.objects.get().tenant is None


# ---------------------------------------------------------------------------
# Milter — _directory_servers_for tenant fallback
# ---------------------------------------------------------------------------


@pytest.fixture
def helper() -> MilterHelper:
    h = MilterHelper(configuration={"sender_ip": []})
    h.mail_data["envelope_from"] = "alice@acme.com"
    h.mail_data["envelope_rcpt"] = "bob@external.tld"
    return h


def _make_action_with_tenant_servers(*, server_count: int = 1):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")
    for i in range(server_count):
        DirectoryServer.objects.create(
            name=f"acme-{i}",
            tenant=tenant,
            base_dn="dc=acme,dc=com",
        )
    rule = Rule.objects.create(name="r")
    disclaimer = Disclaimer.objects.create(name="d", tenant=tenant)
    return Action.objects.create(
        rule=rule, disclaimer=disclaimer, position=0, name="a"
    )


def test_directory_servers_for_uses_explicit_when_set(db, helper):
    action = _make_action_with_tenant_servers(server_count=1)
    explicit = DirectoryServer.objects.create(
        name="explicit", base_dn="dc=other,dc=tld"
    )
    action.directory_servers.add(explicit)

    result = helper._directory_servers_for(action, "alice@acme.com")
    assert [s.name for s in result] == ["explicit"]


def test_directory_servers_for_falls_back_to_tenant(db, helper):
    action = _make_action_with_tenant_servers(server_count=2)
    # No explicit directory_servers attached → tenant fallback kicks in.
    result = helper._directory_servers_for(action, "alice@acme.com")
    assert {s.name for s in result} == {"acme-0", "acme-1"}


def test_directory_servers_for_returns_empty_when_no_tenant_match(db, helper):
    action = _make_action_with_tenant_servers(server_count=1)
    # Sender domain doesn't match any tenant.
    result = helper._directory_servers_for(action, "stranger@nowhere.tld")
    assert result == []


def test_directory_servers_for_skips_disabled_tenant_servers(db, helper):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    TenantDomain.objects.create(tenant=tenant, domain="acme.com")
    DirectoryServer.objects.create(name="enabled", tenant=tenant, base_dn="dc=a")
    DirectoryServer.objects.create(
        name="disabled", tenant=tenant, base_dn="dc=a", enabled=False
    )
    rule = Rule.objects.create(name="r")
    disclaimer = Disclaimer.objects.create(name="d", tenant=tenant)
    action = Action.objects.create(
        rule=rule, disclaimer=disclaimer, position=0, name="a"
    )

    result = helper._directory_servers_for(action, "alice@acme.com")
    assert [s.name for s in result] == ["enabled"]


# ---------------------------------------------------------------------------
# Tenant deletion preserves linked rows (SET_NULL)
# ---------------------------------------------------------------------------


def test_deleting_tenant_nulls_directory_server_link(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    server = DirectoryServer.objects.create(
        name="acme", tenant=tenant, base_dn="dc=a"
    )
    tenant.delete()
    server.refresh_from_db()
    assert server.tenant is None


def test_deleting_tenant_nulls_disclaimer_link(db):
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    disclaimer = Disclaimer.objects.create(name="d", tenant=tenant)
    tenant.delete()
    disclaimer.refresh_from_db()
    assert disclaimer.tenant is None
