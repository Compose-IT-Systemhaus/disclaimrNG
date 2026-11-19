"""The signature goes above the quoted mail in replies and forwards."""

from __future__ import annotations

import email
from email.mime.text import MIMEText

import pytest

from disclaimr.milter_helper import MilterHelper
from disclaimrwebadmin import models
from tests.test_milter_pipeline import _connected_helper, _send, _setup_rule, _split_mime


def _signed(body: str, subtype: str, *, above: bool = True) -> str:
    _setup_rule(text="SIGNATURE")
    models.Action.objects.update(insert_above_quote=above)
    headers, raw = _split_mime(MIMEText(body, subtype, "utf-8"))
    workflow = _send(_connected_helper(), headers, [raw])
    rebuilt = email.message_from_string(
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + workflow["repl_body"]
    )
    return MilterHelper.decode_mail(rebuilt)[1]


BULWARK = (
    "<p>Sure.</p><p data-reply-quote-start=\"true\">On Monday, Bob wrote:</p>"
    "<div data-quoted-html=\"\"><p>Can you?</p></div>"
)
THUNDERBIRD = (
    "<p>Sure.</p><div class=\"moz-cite-prefix\">Am 19.11.26 um 10:00 schrieb Bob:<br></div>"
    "<blockquote type=\"cite\"><p>Can you?</p></blockquote>"
)
APPLE = "<div>Sure.</div><div>On 19 Nov 2026, at 10:00, Bob wrote:</div><blockquote type=\"cite\"><div>Can you?</div></blockquote>"
FORWARD = (
    "<p>FYI</p><div class=\"moz-forward-container\">-------- Weitergeleitete Nachricht"
    " --------<p>Can you?</p></div>"
)


@pytest.mark.parametrize(
    ("body", "quote"),
    [(BULWARK, "On Monday"), (THUNDERBIRD, "Am 19.11.26"), (APPLE, "On 19 Nov"), (FORWARD, "--------")],
)
def test_html_signature_goes_above_the_quote(db, body, quote):
    html = _signed(body, "html")
    assert html.count("SIGNATURE") == 1
    assert html.index("Sure" if "Sure" in body else "FYI") < html.index("SIGNATURE") < html.index(quote)
    assert html.index(quote) < html.index("Can you?")


def test_html_without_quote_or_with_the_option_off_appends_at_the_end(db):
    assert _signed("<p>Hello</p>", "html").rstrip().endswith("</html>")
    html = _signed(THUNDERBIRD, "html", above=False)
    assert html.index("Can you?") < html.index("SIGNATURE")
    html = _signed("<p>Hello</p>", "html")
    assert html.index("Hello") < html.index("SIGNATURE")


@pytest.mark.parametrize(
    "quote",
    [
        "Am 19.11.26 um 10:00 schrieb Bob:\n> Can you?\n",
        "-------- Weitergeleitete Nachricht --------\nBetreff: x\n\nCan you?\n",
        "---------- Forwarded message ----------\nFrom: Bob\n\nCan you?\n",
        "> Can you?\n",
    ],
)
def test_text_signature_goes_above_the_quote(db, quote):
    text = _signed("Sure.\n\n" + quote, "plain").replace("\r\n", "\n")
    assert text.startswith("Sure.\n\n\nSIGNATURE")
    assert text.index("SIGNATURE") < text.index(quote.split("\n")[0]) < text.index("Can you?")


def test_text_without_quote_or_with_the_option_off_appends_at_the_end(db):
    assert _signed("Hello\n", "plain").replace("\r\n", "\n").rstrip().endswith("SIGNATURE")
    text = _signed("Sure.\n\n> Can you?\n", "plain", above=False)
    assert text.index("Can you?") < text.index("SIGNATURE")
