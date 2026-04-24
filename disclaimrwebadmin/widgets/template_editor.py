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

from django import forms
from django.urls import reverse_lazy


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
        return context
