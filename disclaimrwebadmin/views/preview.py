"""Server-rendered preview for the template editor.

Receives a disclaimer snippet via POST and returns it with sample resolver
values substituted. Bound under the ``disclaimrwebadmin:disclaimer-preview``
URL name and called via ``fetch()`` from ``template_editor.js``.

The substitution itself is the milter's :func:`~disclaimr.milter_helper.render_template`,
so ``{rt}…{/rt}`` blocks and escaping behave exactly like in production.

Sample data is intentionally hard-coded for now — a follow-up issue will let
admins pick a real :class:`DirectoryServer` to source live attribute names.
"""

from __future__ import annotations

from html import escape
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import View

from disclaimr.milter_helper import (
    _build_image_replacements,
    escape_html_value,
    render_template,
)

_SAMPLE_DATA: dict[str, Any] = {
    "sender": "alice@example.com",
    "recipient": "bob@external.tld",
    "resolver": {
        "cn": "Alice Example",
        "displayname": "Alice Example",
        "title": "Senior Software Engineer",
        "telephonenumber": "+49 30 12345678",
        "mobile": "+49 170 1234567",
        "mail": "alice@example.com",
        "company": "Example GmbH",
        "department": "Engineering",
    },
    "header": {
        "subject": "Hello there",
        "from": "Alice Example <alice@example.com>",
        "to": "bob@external.tld",
    },
}


def _build_image_table(content: str, content_type: str) -> dict[str, str]:
    """Render ``image["slug"]`` references against the SignatureImage table."""
    return _build_image_replacements(content, content_type)


def _render(content: str, content_type: str) -> str:
    """Substitute ``{key}`` and ``{key["subkey"]}`` tags with sample values."""
    replacements = {**_SAMPLE_DATA, "image": _build_image_table(content, content_type)}
    rendered = render_template(
        content,
        replacements,
        escape=escape_html_value if content_type == "text/html" else str,
    )
    return rendered or ""


@method_decorator(staff_member_required, name="dispatch")
class DisclaimerPreviewView(View):
    """Render a disclaimer with sample data and return it as HTML."""

    def post(self, request: HttpRequest) -> HttpResponse:
        content = request.POST.get("content", "")
        content_type = request.POST.get("content_type", "text/html")

        rendered = _render(content, content_type)

        if content_type == "text/plain":
            body = (
                f"<pre style='font-family: ui-monospace, monospace; white-space: pre-wrap'>"
                f"{escape(rendered)}</pre>"
            )
        else:
            body = rendered

        document = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>body{font-family:system-ui,sans-serif;padding:1rem;color:#111}</style>"
            f"</head><body>{body}</body></html>"
        )
        return HttpResponse(document, content_type="text/html; charset=utf-8")
