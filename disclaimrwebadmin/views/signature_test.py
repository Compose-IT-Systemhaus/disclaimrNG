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

import base64
import binascii
import email
import logging
import re
from dataclasses import dataclass

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import View

from disclaimr.configuration_helper import build_configuration
from disclaimr.milter_helper import MilterHelper

logger = logging.getLogger(__name__)


@dataclass
class _MatchedRule:
    """Lightweight projection of a Rule that survived the pipeline."""

    name: str
    description: str
    pk: int


@dataclass
class _TestOutcome:
    """Everything the result template needs to render — no Django models."""

    matched: bool
    summary: str
    rendered_body: str
    rendered_content_type: str
    rendered_full_mail: str
    add_headers: dict[str, str]
    change_headers: dict[str, str]
    delete_headers: list[str]
    matched_rules: list[_MatchedRule]
    error: str = ""

    @property
    def html_preview_data_url(self) -> str:
        """Return ``rendered_body`` as a ``data:`` URL for an ``<iframe src=>``.

        Avoids the double-escaping you get with ``<iframe srcdoc=...>``:
        Django auto-escapes ``&`` to ``&amp;`` for attribute safety, the
        browser then de-escapes once when reading the attribute, and the
        iframe sees text like ``&#252;`` as literal characters instead of
        a ü entity. Encoding the whole HTML body as base64 in a data URL
        sidesteps the attribute layer.
        """
        try:
            body_bytes = self.rendered_body.encode("utf-8", errors="replace")
            return (
                "data:text/html;charset=utf-8;base64,"
                + base64.b64encode(body_bytes).decode("ascii")
            )
        except Exception:  # noqa: BLE001 — never break the result template
            logger.exception("html_preview_data_url encoding failed")
            return "about:blank"


@method_decorator(staff_member_required, name="dispatch")
class SignatureTestView(View):
    """Render the test form on GET, run the pipeline on POST."""

    template_name = "admin/disclaimrwebadmin/signature_test.html"

    def _admin_context(self, request: HttpRequest) -> dict:
        """Seed the template with everything unfold's chrome needs.

        ``admin.site.each_context`` populates ``site_header``,
        ``available_apps`` (drives the sidebar) and — crucially —
        unfold's ``colors`` dict that gets rendered into the inline
        ``<style id="unfold-theme-colors">`` block. Without it, the
        custom view runs but loses the sidebar AND every CSS variable
        we use for borders / button colours / dark-mode contrast.
        """
        return admin.site.each_context(request)

    def get(self, request: HttpRequest) -> HttpResponse:
        context = self._admin_context(request)
        context["defaults"] = _defaults()
        return render(request, self.template_name, context)

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

        context = self._admin_context(request)
        context.update(
            {
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
        )
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
    """Drive ``MilterHelper`` through every stage and return the outcome.

    The pipeline calls ``re.search`` against admin-supplied regex patterns
    on every stage, so a malformed pattern in any active ``Requirement``
    will raise ``re.error`` and bring the whole run down. We catch every
    exception here and surface it as a UI hint instead of a 500 — the
    operator can then jump to the offending Rule and fix the pattern.
    """
    headers = [
        ("From", sender),
        ("To", recipient),
        ("Subject", subject),
        ("Content-Type", f"{content_type}; charset=utf-8"),
        ("Content-Transfer-Encoding", "8bit"),
    ]
    raw_input = "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + body

    try:
        helper = MilterHelper(build_configuration())
        helper.connect("test-host", 0, sender_ip, 0, {})

        if not helper.enabled:
            return (
                _passthrough_outcome(
                    body,
                    content_type,
                    raw_input,
                    summary=(
                        "Sender-IP traf auf keine Requirement zu — "
                        "die Milter-Pipeline würde diese Mail unverändert "
                        "durchlassen."
                    ),
                ),
                f"<no MIME — sender_ip {sender_ip} did not match>",
            )

        helper.mail_from(sender, {})
        helper.rcpt(recipient, {})

        for key, value in headers:
            helper.header(key, value, {})
        helper.eoh({})

        helper.body(body, {})
        workflow = helper.eob({})
    except re.error as exc:
        return (
            _error_outcome(
                body,
                content_type,
                raw_input,
                error=(
                    "Eine konfigurierte Requirement enthält ein ungültiges "
                    f"Regex-Muster: {exc}. Bitte das Regex-Feld der "
                    "betroffenen Requirement (Sender / Empfänger / Header / "
                    "Body) korrigieren — typischer Fehler: ein nacktes "
                    "``*`` statt ``.*``."
                ),
            ),
            raw_input,
        )
    except Exception as exc:  # noqa: BLE001 — last-ditch UI safety net
        return (
            _error_outcome(
                body,
                content_type,
                raw_input,
                error=f"{type(exc).__name__}: {exc}",
            ),
            raw_input,
        )

    if workflow is None:
        return (
            _passthrough_outcome(
                body,
                content_type,
                raw_input,
                summary=(
                    "Die Mail traf auf keine aktive Regel — "
                    "die Pipeline würde sie unverändert durchlassen."
                ),
            ),
            raw_input,
        )

    try:
        matched_rules = _matched_rules(helper)
    except Exception:  # noqa: BLE001 — never block the result panel
        logger.exception("matched_rules lookup failed")
        matched_rules = []

    try:
        rendered_body, rendered_content_type, rendered_full_mail = (
            _decode_result(
                original_headers=headers,
                workflow=workflow,
                fallback_body=body,
                fallback_content_type=content_type,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("decoding the post-pipeline body failed")
        rendered_body = workflow.get("repl_body", body)
        rendered_content_type = content_type
        rendered_full_mail = repr(workflow)

    if matched_rules:
        rule_word = "Regel" if len(matched_rules) == 1 else "Regeln"
        summary = (
            f"{len(matched_rules)} {rule_word} hat gegriffen — die Mail würde "
            "wie unten gezeigt verändert werden."
            if len(matched_rules) == 1
            else
            f"{len(matched_rules)} {rule_word} haben gegriffen — die Mail würde "
            "wie unten gezeigt verändert werden."
        )
    else:
        summary = (
            "Die Pipeline hat die Mail verändert, aber keine Regel "
            "konnte eindeutig zugeordnet werden."
        )

    return (
        _TestOutcome(
            matched=True,
            summary=summary,
            rendered_body=rendered_body,
            rendered_content_type=rendered_content_type,
            rendered_full_mail=rendered_full_mail,
            add_headers=workflow.get("add_header", {}),
            change_headers=workflow.get("change_header", {}),
            delete_headers=workflow.get("delete_header", []),
            matched_rules=matched_rules,
        ),
        raw_input,
    )


def _passthrough_outcome(
    body: str, content_type: str, raw_input: str, *, summary: str
) -> _TestOutcome:
    return _TestOutcome(
        matched=False,
        summary=summary,
        rendered_body=body,
        rendered_content_type=content_type,
        rendered_full_mail=raw_input,
        add_headers={},
        change_headers={},
        delete_headers=[],
        matched_rules=[],
    )


def _error_outcome(
    body: str, content_type: str, raw_input: str, *, error: str
) -> _TestOutcome:
    return _TestOutcome(
        matched=False,
        summary="",
        rendered_body=body,
        rendered_content_type=content_type,
        rendered_full_mail=raw_input,
        add_headers={},
        change_headers={},
        delete_headers=[],
        matched_rules=[],
        error=error,
    )


def _matched_rules(helper: MilterHelper) -> list[_MatchedRule]:
    """Return the rules whose requirements survived the pipeline.

    After ``eob()`` ``helper.requirements`` is the list of Requirement IDs
    that matched every check. The rule that owns at least one such
    requirement is the one whose actions just ran.
    """
    # Lazy import — avoids a circular dependency at module load time
    # (this view module is reached via disclaimrwebadmin.urls, which is
    # included before all models have finished loading on a cold start).
    from disclaimrwebadmin.models import Requirement, Rule

    if not helper.requirements:
        return []
    rule_ids = (
        Requirement.objects.filter(id__in=helper.requirements)
        .values_list("rule_id", flat=True)
        .distinct()
    )
    return [
        _MatchedRule(
            name=rule.name or f"Regel #{rule.pk}",
            description=rule.description or "",
            pk=rule.pk,
        )
        for rule in Rule.objects.filter(id__in=list(rule_ids))
    ]


def _decode_result(
    *,
    original_headers: list[tuple[str, str]],
    workflow: dict,
    fallback_body: str,
    fallback_content_type: str,
) -> tuple[str, str, str]:
    """Reconstruct the post-pipeline mail and decode it for display.

    ``workflow["repl_body"]`` is the *encoded* body Python's email
    machinery wrote out — for an 8-bit text body that often comes back
    as base64, which is unreadable in a UI. We rebuild the full mail
    (headers + body, with the workflow's add/change/delete applied),
    parse it back into a Message, and surface the *decoded* payload of
    the first text/plain or text/html part.

    Returns ``(decoded_body, content_type, full_rfc822_mail)``.
    """
    final_headers = dict(original_headers)
    for key in workflow.get("delete_header", []):
        final_headers.pop(key, None)
    for key, value in workflow.get("change_header", {}).items():
        final_headers[key] = value
    for key, value in workflow.get("add_header", {}).items():
        final_headers[key] = value

    repl_body = workflow.get("repl_body", fallback_body)
    full_mail_str = (
        "\n".join(f"{k}: {v}" for k, v in final_headers.items())
        + "\n\n"
        + repl_body
    )

    try:
        parsed = email.message_from_string(full_mail_str)
    except Exception:  # noqa: BLE001 — best-effort UI hint
        return fallback_body, fallback_content_type, full_mail_str

    decoded_body, decoded_content_type = _extract_text_part(
        parsed, fallback_content_type
    )
    return decoded_body or fallback_body, decoded_content_type, full_mail_str


def _extract_text_part(
    message: email.message.Message, fallback_content_type: str
) -> tuple[str, str]:
    """Walk ``message`` and return the first text/* part as decoded str.

    Python's email library returns wildly different payload types
    depending on the Content-Transfer-Encoding header:

    * For ``base64`` / ``quoted-printable`` ``get_payload(decode=True)``
      returns the *decoded* bytes — we then have to decode those bytes
      using the part's charset.
    * For ``7bit`` / ``8bit`` / ``binary`` (or no header at all) the
      payload was never actually re-encoded, so ``get_payload(decode=True)``
      effectively round-trips through latin-1 — which mangles every
      non-ASCII character. We must instead use ``get_payload(decode=False)``,
      which returns the original ``str`` untouched.
    """
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        # ``walk()`` yields multipart containers too; their payload is a
        # list of sub-Messages, never a string. Skip them — we want a
        # leaf text part.
        if part.is_multipart():
            continue

        charset = part.get_content_charset() or "utf-8"
        cte = (part.get("Content-Transfer-Encoding") or "").strip().lower()

        try:
            if cte in ("quoted-printable", "base64"):
                payload = part.get_payload(decode=True)
            else:
                # 7bit / 8bit / binary / no CTE header — payload was
                # never encoded; return it as the original string.
                payload = part.get_payload(decode=False)
        except Exception:  # noqa: BLE001 — defensive against email-lib quirks
            logger.exception("get_payload failed for part with ctype=%s", ctype)
            continue

        if payload is None:
            continue
        if isinstance(payload, bytes):
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")
        elif isinstance(payload, str):
            text = payload
        else:
            # ``list`` (nested multipart), or anything else exotic — skip.
            logger.warning(
                "Unexpected payload type %s for part with ctype=%s",
                type(payload).__name__, ctype,
            )
            continue

        return _maybe_unbase64(text, charset), ctype
    return "", fallback_content_type


def _maybe_unbase64(text: str, charset: str) -> str:
    """Decode ``text`` if it actually is base64 even though the header lied.

    Belt-and-braces against an old build of the milter (or any future
    regression where ``Content-Transfer-Encoding`` says one thing and
    the body is encoded as another). If the input is short enough not
    to look like base64 — or doesn't decode — we return it unchanged.
    """
    cleaned = "".join(text.split())
    if len(cleaned) < 8 or len(cleaned) % 4 != 0:
        return text
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
        return text
    try:
        decoded_bytes = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError):
        return text
    try:
        decoded = decoded_bytes.decode(charset, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return text
    # Sanity gate: if the decoded result is mostly non-printable noise it
    # was almost certainly *not* base64 to begin with — fall back to raw.
    if "\x00" in decoded:
        return text
    return decoded
