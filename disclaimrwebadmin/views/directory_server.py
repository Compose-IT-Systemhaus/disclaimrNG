"""Admin-only JSON endpoints for the DirectoryServer detail page.

Provides two actions exposed as buttons in the change form:

- ``test/`` — bind with the values of the (unsaved) form and report the outcome.
- ``attributes/<id>/`` — sample directory entries and return the union of
  attribute names. Drives the template-editor autocomplete vocabulary.

Both endpoints are POST-only (CSRF-protected) and require staff access.
"""

from __future__ import annotations

from dataclasses import asdict

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import View

from disclaimr.ldap_helper import discover_attributes, search_dns, test_connection

from ..models import DirectoryServer, Requirement, SignatureImage
from .permissions import staff_with_perm


@method_decorator(
    staff_with_perm("add_directoryserver", "change_directoryserver"), name="dispatch"
)
class DirectoryServerTestView(View):
    """Bind with what is in the form right now (nothing is saved) and report per URL."""

    def post(self, request: HttpRequest) -> JsonResponse:
        from ..admin import DirectoryServerForm  # the admin module imports the views' models

        pk = request.POST.get("_object_id")
        instance = get_object_or_404(DirectoryServer, pk=pk) if pk else DirectoryServer()
        form = DirectoryServerForm(request.POST, request.FILES, instance=instance)
        if not form.is_valid():
            problems = "; ".join(
                f"{form.fields[f].label if f in form.fields else f}: {' '.join(e)}"
                for f, e in form.errors.items()
            )
            return JsonResponse(
                {"ok": False, "summary": _("Correct the form first — %s") % problems, "probes": []}
            )
        result = test_connection(form.save(commit=False), form.urls())
        return JsonResponse(
            {
                "ok": result.ok,
                "summary": result.summary,
                "probes": [asdict(p) for p in result.probes],
            }
        )


@method_decorator(staff_with_perm("change_directoryserver"), name="dispatch")
class DirectoryServerAttributesView(View):
    """Discover available attributes from a directory server."""

    def post(self, request: HttpRequest, pk: int) -> JsonResponse:
        directory_server = get_object_or_404(DirectoryServer, pk=pk)
        result = discover_attributes(directory_server)
        return JsonResponse(
            {
                "ok": result.ok,
                "detail": result.detail,
                "sample_dn": result.sample_dn,
                "attributes": result.attributes,
            }
        )


@method_decorator(staff_with_perm("add_disclaimer", "change_disclaimer"), name="dispatch")
class DirectoryServerVocabularyView(View):
    """Return the curated autocomplete vocabulary for all enabled servers.

    Used by the template-editor autocomplete: one GET, all the keys an admin
    can reasonably expect to substitute via ``{resolver["…"]}``.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        servers = DirectoryServer.objects.filter(enabled=True)
        vocab: set[str] = set()
        per_server: list[dict[str, object]] = []
        for srv in servers:
            attrs = srv.get_attribute_vocabulary()
            vocab.update(attrs)
            per_server.append(
                {"id": srv.id, "name": srv.name, "attributes": attrs}
            )
        images = [
            {
                "slug": img.slug,
                "name": img.name,
                "url": img.image.url if img.image else "",
                "alt_text": img.alt_text,
            }
            for img in SignatureImage.objects.all()
        ]
        return JsonResponse(
            {
                "attributes": sorted(vocab, key=str.lower),
                "servers": per_server,
                "images": images,
            }
        )


@method_decorator(staff_with_perm("add_requirement", "change_requirement"), name="dispatch")
class DirectoryDNSearchView(View):
    """OUs or groups for the DN field of a directory condition.

    Asks the directory servers of the requirement's tenant (all enabled servers when the
    rule has none). Returns DNs and names only, so editors without
    ``view_directoryserver`` may use it.
    """

    def get(self, request: HttpRequest) -> JsonResponse:
        kind = request.GET.get("kind", "")
        text = request.GET.get("q", "").strip()
        if kind not in ("ou", "group") or len(text) < 2:
            return JsonResponse({"results": [], "error": ""})
        servers = DirectoryServer.objects.filter(enabled=True)
        pk = request.GET.get("requirement", "")
        tenant = (
            Requirement.objects.filter(pk=pk).values_list("rule__tenant", flat=True).first()
            if pk.isdigit()
            else None
        )
        if tenant:
            servers = servers.filter(tenant=tenant)
        results, error = search_dns(list(servers), kind, text)
        return JsonResponse({"results": results, "error": error})
