"""Render the bundled Markdown docs at ``/admin/disclaimr/docs/``.

Sources live under ``docs/<lang>/<slug>.md`` at the repo root. ``<lang>``
is picked from the active Django language code; if there's no
matching ``de/`` file we fall back to ``en/`` so a half-translated
section still serves something readable.
"""

from __future__ import annotations

from pathlib import Path

import markdown
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

# Where the .md sources live.
DOCS_ROOT = Path(settings.BASE_DIR) / "docs"

# Sidebar order + display titles. The slug is the URL fragment AND the
# Markdown filename without ``.md``. Titles are translatable so the
# sidebar matches the active language even before the operator clicks
# through to the page.
TOC: list[tuple[str, "object"]] = [
    ("index", _("Overview")),
    ("installation", _("Installation")),
    ("configuration", _("Configuration")),
    ("tenants", _("Tenants")),
    ("directory-servers", _("Directory servers")),
    ("signatures", _("Signatures & rules")),
    ("walkthrough", _("Walkthrough — domain signature")),
    ("troubleshooting", _("Troubleshooting")),
]

# Markdown extensions for sane rendering: fenced code blocks, tables,
# table of contents anchors, code highlighting, and ``[link](#anchor)``
# resolution.
_MD_EXTENSIONS = [
    "fenced_code",
    "tables",
    "toc",
    "codehilite",
    "sane_lists",
    "admonition",
]


def _resolve_source(slug: str) -> Path:
    """Return the .md file path for ``slug`` in the active language.

    Falls back to ``en/`` if the active language has no translation.
    Raises ``Http404`` if neither exists.
    """
    lang = get_language() or "en"
    primary = lang.split("-", 1)[0].lower()
    candidates = [
        DOCS_ROOT / primary / f"{slug}.md",
        DOCS_ROOT / "en" / f"{slug}.md",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise Http404(f"docs page {slug!r} not found")


@method_decorator(staff_member_required, name="dispatch")
class DocsView(View):
    """Render one Markdown page wrapped in the unfold admin chrome."""

    template_name = "admin/disclaimrwebadmin/docs.html"

    def get(self, request: HttpRequest, slug: str = "index") -> HttpResponse:
        if slug.endswith("/"):
            slug = slug[:-1]
        if not slug:
            slug = "index"
        # Restrict to known slugs so we never read arbitrary filenames
        # from disk via the URL.
        known = {entry[0] for entry in TOC}
        if slug not in known:
            raise Http404(f"unknown docs page {slug!r}")

        source = _resolve_source(slug)
        md = markdown.Markdown(extensions=_MD_EXTENSIONS, output_format="html5")
        body_html = md.convert(source.read_text(encoding="utf-8"))

        # Build the sidebar: each entry knows its URL + whether it's
        # the active page so the template can apply an ``is-active``
        # class without doing the lookup itself.
        from django.urls import reverse

        active_slug = slug
        sidebar = [
            {
                "slug": entry_slug,
                "title": str(title),
                "url": reverse(
                    "disclaimrwebadmin:docs-page",
                    kwargs={"slug": entry_slug},
                ),
                "is_active": entry_slug == active_slug,
            }
            for entry_slug, title in TOC
        ]

        active_title = next(
            (str(t) for s, t in TOC if s == active_slug),
            slug,
        )

        context = admin.site.each_context(request)
        context.update(
            {
                "docs_body": body_html,
                "docs_sidebar": sidebar,
                "docs_active_slug": active_slug,
                "docs_active_title": active_title,
                "docs_toc_html": getattr(md, "toc", ""),
            }
        )
        return render(request, self.template_name, context)
