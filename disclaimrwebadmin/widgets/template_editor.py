"""Tabbed Code / WYSIWYG / Preview editor widget for disclaimer templates.

Renders a single ``<textarea>`` (the canonical storage) plus three tabs:

* **Code** — Monaco editor with HTML / plaintext syntax highlighting and
  autocomplete for the ``{resolver["…"]}`` placeholder syntax.
* **Visual** — TinyMCE WYSIWYG, only enabled when ``content_type`` is
  ``text/html``.
* **Preview** — server-rendered preview iframe pointing at the
  :class:`disclaimrwebadmin.views.preview.DisclaimerPreviewView`.

Tabs sync their content to/from the underlying textarea on switch so the user
never loses edits.
"""

from __future__ import annotations

import json

from django import forms
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

# Common, human-named placeholder chips. Each entry maps a *display label*
# (translatable) to the actual ``{resolver["..."]}`` token that should be
# inserted. The labels here are what an operator naturally reaches for
# when writing a signature; the underlying LDAP attribute names (cn,
# mail, telephoneNumber, …) are an implementation detail they shouldn't
# have to remember.
_COMMON_FIELDS = [
    (_("Name"), 'resolver["cn"]'),
    (_("Phone"), 'resolver["telephoneNumber"]'),
    (_("Email"), 'resolver["mail"]'),
    (_("Address"), 'resolver["streetAddress"]'),
]


class TemplateEditorWidget(forms.Textarea):
    """Editor widget rendered as Code/Visual/Preview tabs."""

    template_name = "disclaimrwebadmin/widgets/template_editor.html"

    class Media:
        # Vendored assets are fetched at Docker build time; in dev they live
        # under STATICFILES via collectstatic. CDN fallback for local dev is
        # handled in the template.
        css = {
            "all": [
                "disclaimrwebadmin/template_editor/template_editor.css",
            ],
        }
        js = [
            "disclaimrwebadmin/template_editor/template_editor.js",
        ]

    def __init__(self, content_type: str = "text/html", attrs=None) -> None:
        super().__init__(attrs)
        self.content_type = content_type

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["content_type"] = self.content_type
        context["widget"]["preview_url"] = str(
            reverse_lazy("disclaimrwebadmin:disclaimer-preview")
        )
        context["widget"]["vocabulary_url"] = str(
            reverse_lazy("disclaimrwebadmin:directoryserver-vocabulary")
        )
        context["widget"]["upload_url"] = str(
            reverse_lazy("disclaimrwebadmin:signatureimage-quick-upload")
        )
        # Pre-translated common field chips, JSON-encoded for the JS to
        # render without having to bother with django.js i18n. Resolved
        # at request time via ``str(label)`` so gettext_lazy hands us
        # the active language.
        context["widget"]["common_fields_json"] = json.dumps(
            [{"label": str(label), "token": token} for label, token in _COMMON_FIELDS]
        )
        return context
