"""Data for the admin dashboard (``UNFOLD["DASHBOARD_CALLBACK"]``).

Rendered by ``disclaimrwebadmin/admin/index.html``: a handful of key
figures, a setup checklist while the installation is still empty, quick
links and the operator's own recent changes.
"""

from __future__ import annotations

from typing import Any

from django.contrib.admin.models import LogEntry
from django.db.models import Count, Q
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import DirectoryServer, Disclaimer, Rule, SignatureImage, Tenant, TenantDomain

_APP = "disclaimrwebadmin"


def _admin_url(request: HttpRequest, model: str, view: str) -> str | None:
    """Return the admin URL for ``model``/``view`` if the user may open it."""
    permission = {"changelist": "view", "add": "add"}[view]
    if not request.user.has_perm(f"{_APP}.{permission}_{model}"):
        return None
    return reverse(f"admin:{_APP}_{model}_{view}")


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

    signature_test_url = reverse(f"{_APP}:signature-test")
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
    }
    return context
