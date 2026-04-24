"""Admin-only JSON endpoints for the DirectoryServer detail page.

Provides two actions exposed as buttons in the change form:

- ``test/<id>/`` — bind to every configured URL and report the outcome.
- ``attributes/<id>/`` — sample directory entries and return the union of
  attribute names. Drives the template-editor autocomplete vocabulary.

Both endpoints are POST-only (CSRF-protected) and require staff access.
"""

from __future__ import annotations

from dataclasses import asdict

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import View

from disclaimr.ldap_helper import discover_attributes, test_connection

from ..models import DirectoryServer, SignatureImage


@method_decorator(staff_member_required, name="dispatch")
class DirectoryServerTestView(View):
    """Bind to every configured URL and return per-URL status."""

    def post(self, request: HttpRequest, pk: int) -> JsonResponse:
        directory_server = get_object_or_404(DirectoryServer, pk=pk)
        result = test_connection(directory_server)
        return JsonResponse(
            {
                "ok": result.ok,
                "summary": result.summary,
                "probes": [asdict(p) for p in result.probes],
            }
        )


@method_decorator(staff_member_required, name="dispatch")
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


@method_decorator(staff_member_required, name="dispatch")
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
            {"slug": img.slug, "name": img.name}
            for img in SignatureImage.objects.all()
        ]
        return JsonResponse(
            {
                "attributes": sorted(vocab, key=str.lower),
                "servers": per_server,
                "images": images,
            }
        )
