"""Sync Tenant rows (and their domains) from environment variables.

Mirrors :mod:`sync_directory_servers` so the multi-tenant layer can be
configured declaratively. Tenants are matched and prune-tracked by their
slug — the env is the source of truth for env-managed rows, manually
created tenants are left alone.

Env schema
----------

TENANTS
    Comma-separated list of *handles*. The handle is lower-cased and used
    as the slug stored on the row. Example: ``acme,globex``.

For each handle ``<HANDLE>`` (uppercased), the following vars are read:

TENANT_<HANDLE>_NAME           (default: handle, title-cased)
TENANT_<HANDLE>_DESCRIPTION    (default: empty)
TENANT_<HANDLE>_DOMAINS        (required, comma-separated sender domains)
TENANT_<HANDLE>_ENABLED        (true/false, default: true)

Env-managed rows are stamped with the same ``[env-managed]`` marker that
:mod:`sync_directory_servers` uses, so prune logic stays consistent.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from disclaimrwebadmin.management.commands.sync_directory_servers import (
    ENV_MANAGED_MARKER,
)
from disclaimrwebadmin.models import Tenant, TenantDomain


def _bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _tenant_var(handle: str, suffix: str) -> str | None:
    return os.environ.get(f"TENANT_{handle.upper()}_{suffix}")


def _build_payload(handle: str) -> dict[str, Any]:
    domains = [d.lower() for d in _split(_tenant_var(handle, "DOMAINS"))]
    name = _tenant_var(handle, "NAME") or handle.replace("_", " ").title()
    extra = _tenant_var(handle, "DESCRIPTION") or ""
    description = ENV_MANAGED_MARKER if not extra else f"{ENV_MANAGED_MARKER} {extra}"
    return {
        "slug": slugify(handle),
        "name": name,
        "description": description,
        "enabled": _bool(_tenant_var(handle, "ENABLED"), True),
        "domains": domains,
    }


class Command(BaseCommand):
    help = "Reconcile Tenant rows with TENANT_* environment variables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Delete env-managed tenants whose handle no longer appears in "
                "TENANTS. Manually-created tenants are never touched."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        handles = _split(os.environ.get("TENANTS"))
        if not handles:
            self.stdout.write(
                "TENANTS not set — nothing to sync. (Manually-created "
                "tenants are unaffected.)"
            )
            return

        payloads = [_build_payload(h) for h in handles]
        dry_run = options["dry_run"]
        prune = options["prune"]

        with transaction.atomic():
            for payload in payloads:
                self._upsert(payload, dry_run=dry_run)

            if prune:
                self._prune({p["slug"] for p in payloads}, dry_run=dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes committed."))

    def _upsert(self, payload: dict[str, Any], *, dry_run: bool) -> None:
        domains: list[str] = payload.pop("domains")
        existing = Tenant.objects.filter(slug=payload["slug"]).first()
        action = "update" if existing else "create"
        self.stdout.write(f"[{action}] {payload['name']} ({payload['slug']})")
        if dry_run:
            return

        if existing is None:
            tenant = Tenant.objects.create(**payload)
        else:
            for field, value in payload.items():
                setattr(existing, field, value)
            existing.save()
            tenant = existing

        # Replace domain set so the env stays authoritative.
        tenant.domains.all().delete()
        for domain in domains:
            TenantDomain.objects.create(tenant=tenant, domain=domain)

    def _prune(self, keep_slugs: set[str], *, dry_run: bool) -> None:
        stale = Tenant.objects.filter(
            description__startswith=ENV_MANAGED_MARKER
        ).exclude(slug__in=keep_slugs)
        for tenant in stale:
            self.stdout.write(self.style.WARNING(f"[delete] {tenant.name}"))
            if not dry_run:
                tenant.delete()
