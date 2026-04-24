"""Tests for the ``sync_directory_servers`` management command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from disclaimrwebadmin import constants
from disclaimrwebadmin.management.commands.sync_directory_servers import (
    ENV_MANAGED_MARKER,
)
from disclaimrwebadmin.models import DirectoryServer


def _run(monkeypatch, env: dict[str, str], *args: str) -> str:
    monkeypatch.delenv("LDAP_SERVERS", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = StringIO()
    call_command("sync_directory_servers", *args, stdout=out)
    return out.getvalue()


def test_no_handles_is_a_noop(db, monkeypatch):
    output = _run(monkeypatch, {})
    assert "nothing to sync" in output
    assert DirectoryServer.objects.count() == 0


def test_creates_server_with_defaults(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=example,dc=com",
        "LDAP_SERVER_PRIMARY_URL": "ldap://ldap.example.com",
    }
    _run(monkeypatch, env)
    srv = DirectoryServer.objects.get()
    assert srv.name == "Primary"
    assert srv.base_dn == "dc=example,dc=com"
    assert srv.flavor == constants.DIR_FLAVOR_LDAP
    assert srv.auth == constants.DIR_AUTH_NONE
    assert srv.search_query == constants.DIR_FLAVOR_DEFAULT_QUERY[
        constants.DIR_FLAVOR_LDAP
    ]
    assert srv.description == ENV_MANAGED_MARKER
    urls = list(srv.directoryserverurl_set.order_by("position"))
    assert [u.url for u in urls] == ["ldap://ldap.example.com"]


def test_simple_bind_when_bind_dn_is_set(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "corp",
        "LDAP_SERVER_CORP_FLAVOR": "ad",
        "LDAP_SERVER_CORP_BASE_DN": "dc=corp,dc=example",
        "LDAP_SERVER_CORP_URL": "ldaps://dc1,ldaps://dc2",
        "LDAP_SERVER_CORP_BIND_DN": "CN=svc,OU=Service,DC=corp,DC=example",
        "LDAP_SERVER_CORP_BIND_PASSWORD": "s3cret",
        "LDAP_SERVER_CORP_NAME": "Corp AD",
        "LDAP_SERVER_CORP_DESCRIPTION": "production",
    }
    _run(monkeypatch, env)
    srv = DirectoryServer.objects.get()
    assert srv.name == "Corp AD"
    assert srv.flavor == constants.DIR_FLAVOR_AD
    assert srv.auth == constants.DIR_AUTH_SIMPLE
    assert srv.userdn.endswith("DC=example")
    assert srv.password == "s3cret"
    assert "production" in srv.description
    assert srv.description.startswith(ENV_MANAGED_MARKER)
    assert [u.url for u in srv.directoryserverurl_set.order_by("position")] == [
        "ldaps://dc1",
        "ldaps://dc2",
    ]


def test_rerun_updates_in_place(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=old,dc=tld",
        "LDAP_SERVER_PRIMARY_URL": "ldap://old",
    }
    _run(monkeypatch, env)
    srv = DirectoryServer.objects.get()
    original_id = srv.id

    env["LDAP_SERVER_PRIMARY_BASE_DN"] = "dc=new,dc=tld"
    env["LDAP_SERVER_PRIMARY_URL"] = "ldap://new1,ldap://new2"
    _run(monkeypatch, env)

    srv = DirectoryServer.objects.get()
    assert srv.id == original_id
    assert srv.base_dn == "dc=new,dc=tld"
    urls = [u.url for u in srv.directoryserverurl_set.order_by("position")]
    assert urls == ["ldap://new1", "ldap://new2"]


def test_prune_removes_env_managed_only(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary,backup",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=p,dc=tld",
        "LDAP_SERVER_PRIMARY_URL": "ldap://p",
        "LDAP_SERVER_BACKUP_BASE_DN": "dc=b,dc=tld",
        "LDAP_SERVER_BACKUP_URL": "ldap://b",
    }
    _run(monkeypatch, env)
    # Manually-created row that prune must NOT touch.
    DirectoryServer.objects.create(
        name="Manual", base_dn="dc=m,dc=tld", description="hand-rolled"
    )
    assert DirectoryServer.objects.count() == 3

    # Drop "backup" from env, run with --prune.
    env["LDAP_SERVERS"] = "primary"
    _run(monkeypatch, env, "--prune")

    names = set(DirectoryServer.objects.values_list("name", flat=True))
    assert names == {"Primary", "Manual"}


def test_missing_required_var_raises(db, monkeypatch):
    monkeypatch.setenv("LDAP_SERVERS", "broken")
    monkeypatch.setenv("LDAP_SERVER_BROKEN_URL", "ldap://x")
    # Missing BASE_DN.
    with pytest.raises(CommandError, match="BASE_DN"):
        call_command("sync_directory_servers", stdout=StringIO())


def test_unknown_flavor_raises(db, monkeypatch):
    monkeypatch.setenv("LDAP_SERVERS", "x")
    monkeypatch.setenv("LDAP_SERVER_X_FLAVOR", "novell")
    monkeypatch.setenv("LDAP_SERVER_X_BASE_DN", "dc=x,dc=y")
    monkeypatch.setenv("LDAP_SERVER_X_URL", "ldap://x")
    with pytest.raises(CommandError, match="Unknown LDAP flavour"):
        call_command("sync_directory_servers", stdout=StringIO())


def test_dry_run_writes_nothing(db, monkeypatch):
    env = {
        "LDAP_SERVERS": "primary",
        "LDAP_SERVER_PRIMARY_BASE_DN": "dc=example,dc=com",
        "LDAP_SERVER_PRIMARY_URL": "ldap://x",
    }
    output = _run(monkeypatch, env, "--dry-run")
    assert "Dry run" in output
    assert DirectoryServer.objects.count() == 0
