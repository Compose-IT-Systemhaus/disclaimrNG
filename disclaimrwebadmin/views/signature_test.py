"""Admin-side end-to-end test of the milter rule pipeline.

The user enters a sender, recipient, and a sample mail body — the view
runs the same pipeline the milter uses (connect → mail_from → rcpt →
header → eoh → body → eob), then renders the resulting body so the
operator can check what would actually be appended in production.

This is a *real* run of :class:`disclaimr.milter_helper.MilterHelper`
against the live ``Requirement``/``Rule``/``Action`` rows — no mocks.
LDAP resolution against an actual directory server *will* happen if a
matching action is configured, so the view runs from a synchronous
admin context where blocking that briefly is acceptable.
"""

from __future__ import annotations

import email
from dataclasses import dataclass

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import View

from disclaimr.configuration_helper import build_configuration
from disclaimr.milter_helper import MilterHelper


@dataclass
class _TestOutcome:
    """Everything the result template needs to render — no Django models."""

    matched: bool
    summary: str
    rendered_body: str
    rendered_content_type: str
    add_headers: dict[str, str]
    change_headers: dict[str, str]
    delete_headers: list[str]


@method_decorator(staff_member_required, name="dispatch")
class SignatureTestView(View):
    """Render the test form on GET, run the pipeline on POST."""

    template_name = "admin/disclaimrwebadmin/signature_test.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, self.template_name, {"defaults": _defaults()})

    def post(self, request: HttpRequest) -> HttpResponse:
        sender = request.POST.get("sender", "").strip()
        recipient = request.POST.get("recipient", "").strip()
        subject = request.POST.get("subject", "").strip() or "(no subject)"
        body = request.POST.get("body", "")
        content_type = request.POST.get("content_type", "text/plain")
        sender_ip = request.POST.get("sender_ip", "").strip() or "127.0.0.1"

        # Build the same MIME message the MTA would hand off to the milter,
        # then run it through the helper stage-by-stage.
        outcome, raw_input = _run_pipeline(
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            content_type=content_type,
            sender_ip=sender_ip,
        )

        context = {
            "defaults": {
                "sender": sender,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "content_type": content_type,
                "sender_ip": sender_ip,
            },
            "outcome": outcome,
            "raw_input": raw_input,
        }
        return render(request, self.template_name, context)


def _defaults() -> dict[str, str]:
    return {
        "sender": "alice@example.com",
        "recipient": "bob@external.tld",
        "subject": "Test mail",
        "body": "Hallo,\n\ndies ist eine Testmail.\n\nViele Grüße",
        "content_type": "text/plain",
        "sender_ip": "127.0.0.1",
    }


def _run_pipeline(
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    content_type: str,
    sender_ip: str,
) -> tuple[_TestOutcome, str]:
    """Drive ``MilterHelper`` through every stage and return the outcome."""
    helper = MilterHelper(build_configuration())
    helper.connect("test-host", 0, sender_ip, 0, {})

    if not helper.enabled:
        return (
            _TestOutcome(
                matched=False,
                summary=(
                    "Sender-IP traf auf keine Requirement zu — "
                    "die Milter-Pipeline würde diese Mail unverändert durchlassen."
                ),
                rendered_body=body,
                rendered_content_type=content_type,
                add_headers={},
                change_headers={},
                delete_headers=[],
            ),
            f"<no MIME — sender_ip {sender_ip} did not match>",
        )

    helper.mail_from(sender, {})
    helper.rcpt(recipient, {})

    headers = [
        ("From", sender),
        ("To", recipient),
        ("Subject", subject),
        ("Content-Type", f"{content_type}; charset=utf-8"),
        ("Content-Transfer-Encoding", "8bit"),
    ]
    for key, value in headers:
        helper.header(key, value, {})
    helper.eoh({})

    raw_input = (
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + body
    )

    helper.body(body, {})
    workflow = helper.eob({})

    if workflow is None:
        return (
            _TestOutcome(
                matched=False,
                summary=(
                    "Die Mail traf auf keine aktive Regel — "
                    "die Pipeline würde sie unverändert durchlassen."
                ),
                rendered_body=body,
                rendered_content_type=content_type,
                add_headers={},
                change_headers={},
                delete_headers=[],
            ),
            raw_input,
        )

    rendered_body = workflow.get("repl_body", body)
    # Try to detect whether the milter wrapped the mail in multipart;
    # if so, surface the first text/html or text/plain part to the
    # template so the rendered preview makes sense to a human.
    rendered_content_type = content_type
    try:
        parsed = email.message_from_string(raw_input.split("\n\n", 1)[0] + "\n\n" + rendered_body)
        if parsed.is_multipart():
            for part in parsed.walk():
                ctype = part.get_content_type()
                if ctype in ("text/plain", "text/html"):
                    rendered_body = part.get_payload(decode=False)
                    rendered_content_type = ctype
                    break
    except Exception:  # noqa: BLE001 — best-effort UI hint
        pass

    summary = "Eine oder mehrere Regeln haben gegriffen — "
    summary += "die Mail würde wie unten gezeigt verändert werden."
    return (
        _TestOutcome(
            matched=True,
            summary=summary,
            rendered_body=rendered_body,
            rendered_content_type=rendered_content_type,
            add_headers=workflow.get("add_header", {}),
            change_headers=workflow.get("change_header", {}),
            delete_headers=workflow.get("delete_header", []),
        ),
        raw_input,
    )
