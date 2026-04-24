"""Server-rendered preview for the template editor.

Receives a disclaimer snippet via POST and returns it with sample resolver
values substituted. Bound under the ``disclaimrwebadmin:disclaimer-preview``
URL name and called via ``fetch()`` from ``template_editor.js``.

Sample data is intentionally hard-coded for now — a follow-up issue will let
admins pick a real :class:`DirectoryServer` to source live attribute names.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import View

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

_TAG_RE = re.compile(r'\{((?!rt|/rt)[^}]*)\}')
_SUBKEY_RE = re.compile(r'^([^\[]*)\["([^"]*)"\]$')


def _render(content: str) -> str:
    """Substitute ``{key}`` and ``{key["subkey"]}`` tags with sample values."""

    def repl(match: re.Match[str]) -> str:
        token = match.group(1)
        sub = _SUBKEY_RE.match(token)
        if sub:
            key, subkey = sub.group(1).lower(), sub.group(2).lower()
            value = _SAMPLE_DATA.get(key, {})
            if isinstance(value, dict):
                return value.get(subkey, "")
            return ""
        value = _SAMPLE_DATA.get(token.lower(), "")
        if isinstance(value, dict):
            return ""
        return value

    return _TAG_RE.sub(repl, content)


@method_decorator(staff_member_required, name="dispatch")
class DisclaimerPreviewView(View):
    """Render a disclaimer with sample data and return it as HTML."""

    def post(self, request: HttpRequest) -> HttpResponse:
        content = request.POST.get("content", "")
        content_type = request.POST.get("content_type", "text/html")

        rendered = _render(content)

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
