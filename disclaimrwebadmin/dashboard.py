"""Data for the admin dashboard (``UNFOLD["DASHBOARD_CALLBACK"]``).

Rendered by ``disclaimrwebadmin/admin/index.html``: a handful of key
figures, a setup checklist while the installation is still empty, quick
links and the operator's own recent changes.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.admin.models import LogEntry
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import (
    DirectoryServer,
    Disclaimer,
    MailLog,
    Rule,
    SignatureImage,
    Tenant,
    TenantDomain,
)

_APP = "disclaimrwebadmin"
_STATS_DAYS = 7


def _admin_url(request: HttpRequest, model: str, view: str) -> str | None:
    """Return the admin URL for ``model``/``view`` if the user may open it."""
    permission = {"changelist": "view", "add": "add"}[view]
    if not request.user.has_perm(f"{_APP}.{permission}_{model}"):
        return None
    return reverse(f"admin:{_APP}_{model}_{view}")


def _mail_stats(request: HttpRequest) -> dict[str, Any] | None:
    """Mail counts of the last days from the mail log; ``None`` unless the user may open the log.

    The log holds personal data and is for superusers only (see ``MailLogAdmin``),
    so the figures follow the same rule — a ``view_maillog`` permission is not enough.
    """
    if not request.user.is_superuser:
        return None
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=_STATS_DAYS - 1
    )
    logs = MailLog.objects.filter(created__gte=start)
    per_day = {
        row["day"]: row
        for row in logs.annotate(day=TruncDate("created"))
        .values("day")
        .annotate(total=Count("id"), signed=Count("id", filter=Q(processed=True)))
    }
    days = []
    for offset in range(_STATS_DAYS):
        day = start.date() + timedelta(days=offset)
        row = per_day.get(day, {})
        days.append({"day": day, "total": row.get("total", 0), "signed": row.get("signed", 0)})
    peak = max(day["total"] for day in days) or 1
    for day in days:
        day["height"] = round(100 * day["total"] / peak)
        day["signed_pct"] = round(100 * day["signed"] / day["total"]) if day["total"] else 0
    total = sum(day["total"] for day in days)
    signed = sum(day["signed"] for day in days)
    return {
        "days": days,
        "total": total,
        "signed": signed,
        "untouched": total - signed,
        # Same text = same combination of rule, action and signature.
        "top": list(
            logs.filter(processed=True)
            .values("applied")
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        ),
        "last": MailLog.objects.values_list("created", flat=True).first(),
        "url": reverse(f"admin:{_APP}_maillog_changelist"),
    }


def dashboard_callback(request: HttpRequest, context: dict[str, Any]) -> dict[str, Any]:
    signatures = Disclaimer.objects.count()
    images = SignatureImage.objects.count()
    rules = Rule.objects.aggregate(
        total=Count("id", distinct=True),
        active=Count("id", filter=Q(action__enabled=True), distinct=True),
    )
    tenants = Tenant.objects.aggregate(
        total=Count("id"), enabled=Count("id", filter=Q(enabled=True))
    )
    domains = TenantDomain.objects.count()
    servers = DirectoryServer.objects.aggregate(
        total=Count("id"), enabled=Count("id", filter=Q(enabled=True))
    )

    cards = [
        {
            "label": _("Signatures"),
            "value": signatures,
            "detail": ngettext("%(count)d image", "%(count)d images", images)
            % {"count": images},
            "icon": "draw",
            "url": _admin_url(request, "disclaimer", "changelist"),
        },
        {
            "label": _("Rules"),
            "value": rules["total"],
            "detail": _("%(count)d active") % {"count": rules["active"]},
            "icon": "rule",
            "url": _admin_url(request, "rule", "changelist"),
        },
        {
            "label": _("Tenants"),
            "value": tenants["total"],
            "detail": ngettext("%(count)d domain", "%(count)d domains", domains)
            % {"count": domains},
            "icon": "groups",
            "url": _admin_url(request, "tenant", "changelist"),
        },
        {
            "label": _("Directory servers"),
            "value": servers["total"],
            "detail": _("%(count)d enabled") % {"count": servers["enabled"]},
            "icon": "dns",
            "url": _admin_url(request, "directoryserver", "changelist"),
        },
    ]

    # Cards without a link are ones the user may not view — don't leak counts.
    cards = [card for card in cards if card["url"]]

    # Same permissions the signature-test view itself asks for.
    may_test = request.user.has_perm(f"{_APP}.view_rule") or request.user.has_perm(
        f"{_APP}.change_rule"
    )
    signature_test_url = reverse(f"{_APP}:signature-test") if may_test else None
    steps = [
        {
            "title": _("Create a signature"),
            "text": _("Plain text and HTML version, with placeholders for name, phone and more."),
            "done": signatures > 0,
            "url": _admin_url(request, "disclaimer", "add"),
        },
        {
            "title": _("Add a rule with an action"),
            "text": _("Decides which mails get which signature."),
            "done": rules["active"] > 0,
            "url": _admin_url(request, "rule", "add"),
        },
        {
            "title": _("Connect a directory server"),
            "text": _("Optional — fills the placeholders from LDAP or Active Directory."),
            "done": servers["total"] > 0,
            "optional": True,
            "url": _admin_url(request, "directoryserver", "add"),
        },
    ]
    setup_done = sum(1 for step in steps if step["done"])
    # The checklist disappears once the required steps are done.
    setup_open = any(not step["done"] and not step.get("optional") for step in steps)

    quick_links = [
        {
            "label": _("New signature"),
            "icon": "edit_note",
            "url": _admin_url(request, "disclaimer", "add"),
        },
        {
            "label": _("New rule"),
            "icon": "rule",
            "url": _admin_url(request, "rule", "add"),
        },
        {
            "label": _("Upload image"),
            "icon": "add_photo_alternate",
            "url": _admin_url(request, "signatureimage", "add"),
        },
        {"label": _("Signature test"), "icon": "science", "url": signature_test_url},
        {
            "label": _("Documentation"),
            "icon": "menu_book",
            "url": reverse(f"{_APP}:docs-index"),
        },
    ]

    recent = (
        LogEntry.objects.filter(user_id=request.user.pk)
        .select_related("content_type")
        .order_by("-action_time")[:6]
    )

    user = request.user
    name = user.get_short_name() or user.get_username()

    context["dashboard"] = {
        "greeting": _("Welcome back, %(name)s") % {"name": name},
        "cards": cards,
        "steps": steps,
        "setup_done": setup_done,
        "setup_total": len(steps),
        "setup_open": setup_open,
        "quick_links": [link for link in quick_links if link["url"]],
        "recent": list(recent),
        "signature_test_url": signature_test_url,
        "mail_stats": _mail_stats(request),
    }
    return context
