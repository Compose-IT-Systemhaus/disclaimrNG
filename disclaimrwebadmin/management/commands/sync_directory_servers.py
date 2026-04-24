"""Sync DirectoryServer rows from environment variables.

Lets ops define LDAP / AD connections without touching the admin UI — useful
for declarative deployments (Compose, Helm, Ansible). The command is
idempotent: running it repeatedly with the same env reaches the same
database state, and entries that disappear from the env are deleted (so the
env stays the source of truth).

Env schema
----------

LDAP_SERVERS
    Comma-separated list of *handles*. A handle is an opaque identifier
    used (a) to namespace the per-server vars, and (b) as the slug stored
    on the row. Example: ``primary,backup``.

For each handle ``<HANDLE>`` (uppercased), the following vars are read:

LDAP_SERVER_<HANDLE>_NAME              (default: handle, title-cased)
LDAP_SERVER_<HANDLE>_DESCRIPTION       (default: empty)
LDAP_SERVER_<HANDLE>_FLAVOR            (ldap | ad | custom, default: ldap)
LDAP_SERVER_<HANDLE>_BASE_DN           (required)
LDAP_SERVER_<HANDLE>_URL               (required, comma-separated for failover)
LDAP_SERVER_<HANDLE>_BIND_DN           (default: empty → anonymous bind)
LDAP_SERVER_<HANDLE>_BIND_PASSWORD     (default: empty)
LDAP_SERVER_<HANDLE>_SEARCH_QUERY      (default: flavour default)
LDAP_SERVER_<HANDLE>_SEARCH_ATTRIBUTES (default: flavour default)
LDAP_SERVER_<HANDLE>_ENABLE_CACHE      (true/false, default: true)
LDAP_SERVER_<HANDLE>_CACHE_TIMEOUT     (seconds, default: 3600)
LDAP_SERVER_<HANDLE>_ENABLED           (true/false, default: true)

Env-managed rows are stamped with a description marker so admins can tell
them apart from manually created ones.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer, DirectoryServerURL

# Stamped on the description of env-managed rows so the admin UI can label
# them and so ``--prune`` knows what is safe to remove.
ENV_MANAGED_MARKER = "[env-managed]"

_FLAVOR_LOOKUP = {
    "ldap": constants.DIR_FLAVOR_LDAP,
    "ad": constants.DIR_FLAVOR_AD,
    "active_directory": constants.DIR_FLAVOR_AD,
    "activedirectory": constants.DIR_FLAVOR_AD,
    "custom": constants.DIR_FLAVOR_CUSTOM,
}

_AUTH_NONE = constants.DIR_AUTH_NONE
_AUTH_SIMPLE = constants.DIR_AUTH_SIMPLE


def _bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _flavor(raw: str | None) -> int:
    if not raw:
        return constants.DIR_FLAVOR_LDAP
    key = raw.strip().lower().replace("-", "_")
    if key not in _FLAVOR_LOOKUP:
        raise CommandError(
            f"Unknown LDAP flavour {raw!r} — expected ldap, ad or custom."
        )
    return _FLAVOR_LOOKUP[key]


def _server_var(handle: str, suffix: str) -> str | None:
    return os.environ.get(f"LDAP_SERVER_{handle.upper()}_{suffix}")


def _build_payload(handle: str) -> dict[str, Any]:
    """Materialise the env vars for ``handle`` into a model-ready dict."""
    base_dn = _server_var(handle, "BASE_DN")
    urls = _split(_server_var(handle, "URL"))

    if not base_dn:
        raise CommandError(
            f"LDAP_SERVER_{handle.upper()}_BASE_DN is required for handle {handle!r}."
        )
    if not urls:
        raise CommandError(
            f"LDAP_SERVER_{handle.upper()}_URL is required for handle {handle!r}."
        )

    bind_dn = _server_var(handle, "BIND_DN") or ""
    bind_pw = _server_var(handle, "BIND_PASSWORD") or ""
    auth = _AUTH_SIMPLE if bind_dn else _AUTH_NONE

    flavor = _flavor(_server_var(handle, "FLAVOR"))
    name = _server_var(handle, "NAME") or handle.replace("_", " ").title()
    extra_description = _server_var(handle, "DESCRIPTION") or ""
    description = ENV_MANAGED_MARKER
    if extra_description:
        description = f"{ENV_MANAGED_MARKER} {extra_description}"

    return {
        "handle": handle,
        "name": name,
        "description": description,
        "enabled": _bool(_server_var(handle, "ENABLED"), True),
        "flavor": flavor,
        "base_dn": base_dn,
        "auth": auth,
        "userdn": bind_dn,
        "password": bind_pw,
        "search_query": _server_var(handle, "SEARCH_QUERY")
            or constants.DIR_FLAVOR_DEFAULT_QUERY[flavor],
        "search_attributes": _server_var(handle, "SEARCH_ATTRIBUTES") or "",
        "enable_cache": _bool(_server_var(handle, "ENABLE_CACHE"), True),
        "cache_timeout": int(_server_var(handle, "CACHE_TIMEOUT") or 3600),
        "urls": urls,
    }


class Command(BaseCommand):
    help = "Reconcile DirectoryServer rows with LDAP_SERVER_* environment variables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Delete env-managed rows whose handle no longer appears in "
                "LDAP_SERVERS. Manually-created rows are never touched."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        handles = _split(os.environ.get("LDAP_SERVERS"))
        if not handles:
            self.stdout.write(
                "LDAP_SERVERS not set — nothing to sync. (Manually-created "
                "directory servers are unaffected.)"
            )
            return

        payloads = [_build_payload(h) for h in handles]
        dry_run = options["dry_run"]
        prune = options["prune"]

        with transaction.atomic():
            for payload in payloads:
                self._upsert(payload, dry_run=dry_run)

            if prune:
                self._prune({p["name"] for p in payloads}, dry_run=dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes committed."))

    def _upsert(self, payload: dict[str, Any], *, dry_run: bool) -> None:
        urls: list[str] = payload.pop("urls")
        handle: str = payload.pop("handle")

        existing = DirectoryServer.objects.filter(name=payload["name"]).first()
        action = "update" if existing else "create"
        self.stdout.write(f"[{action}] {payload['name']} ({handle})")
        if dry_run:
            return

        if existing is None:
            server = DirectoryServer.objects.create(**payload)
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
            existing.save()
            server = existing

        # Replace URL set so the env stays authoritative.
        server.directoryserverurl_set.all().delete()
        for index, url in enumerate(urls):
            DirectoryServerURL.objects.create(
                directory_server=server, url=url, position=index
            )

    def _prune(self, keep_names: set[str], *, dry_run: bool) -> None:
        stale = DirectoryServer.objects.filter(
            description__startswith=ENV_MANAGED_MARKER
        ).exclude(name__in=keep_names)
        for server in stale:
            self.stdout.write(self.style.WARNING(f"[delete] {server.name}"))
            if not dry_run:
                server.delete()
