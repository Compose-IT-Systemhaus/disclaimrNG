"""Regression tests for the milter pipeline (helper + libmilter boundary)."""

from __future__ import annotations

import email
import importlib.util
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from disclaimr import milter_helper
from disclaimr.configuration_helper import build_configuration
from disclaimr.milter_helper import MilterHelper, escape_html_value, render_template
from disclaimrwebadmin import constants, models

BASE_DIR = Path(__file__).resolve().parent.parent


def _setup_rule(
    *,
    text: str = "Signature",
    html: str = "",
    html_use_text: bool = True,
    template_fail: bool = False,
) -> models.Disclaimer:
    disclaimer = models.Disclaimer.objects.create(
        name="d",
        text=text,
        html=html,
        html_use_text=html_use_text,
        template_fail=template_fail,
    )
    rule = models.Rule.objects.create(name="r")
    models.Action.objects.create(
        rule=rule,
        disclaimer=disclaimer,
        position=0,
        name="a",
        action=constants.ACTION_ACTION_ADD,
    )
    models.Requirement.objects.create(rule=rule, name="req")
    return disclaimer


def _send(helper: MilterHelper, headers, body_chunks, *, sender="alice@example.com"):
    helper.mail_from(sender, {})
    helper.rcpt("bob@example.org", {})
    for key, value in headers:
        helper.header(key, value, {})
    helper.eoh({})
    for chunk in body_chunks:
        helper.body(chunk, {})
    return helper.eob({})


def _connected_helper() -> MilterHelper:
    helper = MilterHelper(build_configuration())
    helper.connect("mx.example.com", "4", "10.0.0.1", 25, {})
    assert helper.enabled
    return helper


def _split_mime(message: email.message.Message):
    raw = message.as_string()  # picks the multipart boundary first
    return list(message.items()), raw.split("\n\n", 1)[1]


_PLAIN_8BIT = [
    ("From", "alice@example.com"),
    ("Content-Type", "text/plain; charset=utf-8"),
    ("Content-Transfer-Encoding", "8bit"),
]


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------


def test_missing_subkey_renders_empty_instead_of_looping():
    assert render_template('Hi {header["x-missing"]}there', {"header": {}}) == "Hi there"


def test_substituted_values_are_not_expanded_again():
    replacements = {"header": {"subject": '{header["subject"]} {sender}'}, "sender": "x"}
    assert render_template('{header["subject"]}', replacements) == '{header["subject"]} {sender}'


def test_template_fail_returns_none():
    assert render_template("{missing}", {}, template_fail=True) is None


def test_rt_blocks_are_kept_or_dropped_with_their_line_break():
    template = (
        'Name: {resolver["cn"]}\n'
        '{rt}Phone: {resolver["phone"]}{/rt}\n'
        '{rt}Mobile: {resolver["mobile"]}{/rt}'
    )
    replacements = {"resolver": {"cn": "Alice", "mobile": "+49 1"}}
    assert render_template(template, replacements) == "Name: Alice\nMobile: +49 1"


def test_two_rt_blocks_on_one_line_are_independent():
    template = '{rt}Tel: {resolver["tel"]}{/rt} {rt}Fax: {resolver["fax"]}{/rt}'
    assert render_template(template, {"resolver": {"tel": "1"}}) == "Tel: 1 "


def test_values_are_escaped_but_images_inserted_verbatim():
    replacements = {
        "header": {"from": "Alice <alice@example.com>"},
        "image": {"logo": '<img src="https://x/logo.png" />'},
    }
    rendered = render_template(
        '{header["from"]} {image["logo"]}', replacements, escape=escape_html_value
    )
    assert rendered == 'Alice &lt;alice@example.com&gt; <img src="https://x/logo.png" />'


# ---------------------------------------------------------------------------
# MilterHelper
# ---------------------------------------------------------------------------


def test_body_chunk_boundary_inside_multibyte_character(db):
    _setup_rule()
    raw = "Grüße aus Berlin".encode()
    workflow = _send(_connected_helper(), _PLAIN_8BIT, [raw[:3], raw[3:]])
    assert "Grüße aus Berlin" in workflow["repl_body"]
    assert "�" not in workflow["repl_body"]


def test_first_body_line_that_looks_like_a_header_is_kept(db):
    _setup_rule()
    workflow = _send(_connected_helper(), _PLAIN_8BIT, [b"Note: please read\nSecond line"])
    assert workflow["repl_body"].startswith("Note: please read\nSecond line")


def test_skipped_parts_stay_in_a_multipart_mail(db):
    _setup_rule(text="{FAIL}", template_fail=True)
    message = MIMEMultipart("alternative")
    message.attach(MIMEText("Plain body", "plain", "utf-8"))
    message.attach(MIMEText("<p>HTML body</p>", "html", "utf-8"))
    headers, body = _split_mime(message)

    workflow = _send(_connected_helper(), headers, [body])

    rebuilt = email.message_from_string(
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + workflow["repl_body"]
    )
    parts = rebuilt.get_payload()
    assert len(parts) == 2
    assert MilterHelper.decode_mail(parts[0])[1] == "Plain body"
    assert MilterHelper.decode_mail(parts[1])[1] == "<p>HTML body</p>"


def test_text_disclaimer_renders_images_as_markup_in_html_parts(db, monkeypatch):
    monkeypatch.setattr(
        milter_helper,
        "_build_image_replacements",
        lambda text, content_type: {"logo": '<img src="https://x/logo.png" />'},
    )
    _setup_rule(text='Regards\n{image["logo"]}')
    headers, body = _split_mime(MIMEText("<p>Hello</p>", "html", "utf-8"))

    workflow = _send(_connected_helper(), headers, [body])

    rebuilt = email.message_from_string(
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + workflow["repl_body"]
    )
    html = MilterHelper.decode_mail(rebuilt)[1]
    assert '<img src="https://x/logo.png"' in html
    assert "&lt;img" not in html


def test_html_disclaimer_escapes_header_values(db):
    _setup_rule(html='<p>{header["x-name"]}</p>', html_use_text=False)
    headers, body = _split_mime(MIMEText("<p>Hello</p>", "html", "utf-8"))
    headers.append(("X-Name", "Bob <b>"))

    workflow = _send(_connected_helper(), headers, [body])

    rebuilt = email.message_from_string(
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + workflow["repl_body"]
    )
    html = MilterHelper.decode_mail(rebuilt)[1]
    assert "Bob &lt;b&gt;" in html


def test_second_mail_on_the_same_connection_starts_clean(db):
    _setup_rule()
    helper = _connected_helper()
    _send(helper, _PLAIN_8BIT, [b"first mail"])

    helper.reset()
    workflow = _send(helper, _PLAIN_8BIT, [b"second mail"])

    assert "second mail" in workflow["repl_body"]
    assert "first mail" not in workflow["repl_body"]
    assert len(helper.mail_data["headers"]) == len(_PLAIN_8BIT)


# ---------------------------------------------------------------------------
# build_configuration
# ---------------------------------------------------------------------------


def test_configuration_skips_rules_without_enabled_actions(db):
    _setup_rule()
    idle_rule = models.Rule.objects.create(name="idle")
    models.Requirement.objects.create(rule=idle_rule, name="idle-req")

    ids = [entry["id"] for entry in build_configuration()["sender_ip"]]
    assert ids == list(
        models.Requirement.objects.exclude(rule=idle_rule).values_list("id", flat=True)
    )


def test_configuration_skips_invalid_networks(db):
    _setup_rule()
    rule = models.Rule.objects.get()
    models.Requirement.objects.create(
        rule=rule, name="bad", sender_ip="10.0.0.1", sender_ip_cidr="99"
    )
    assert len(build_configuration()["sender_ip"]) == 1


# ---------------------------------------------------------------------------
# disclaimr.py — python-libmilter speaks bytes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def daemon():
    # ``import disclaimr`` resolves to the package, so load the script by path.
    spec = importlib.util.spec_from_file_location("disclaimr_daemon", BASE_DIR / "disclaimr.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_address_strips_brackets_and_esmtp_parameters(daemon):
    assert daemon._address(b"<alice@example.com>\x00SIZE=1024", {}, "mail_addr") == (
        "alice@example.com"
    )
    assert daemon._address(b"<x@y>", {"rcpt_addr": "bob@example.org"}, "rcpt_addr") == (
        "bob@example.org"
    )


def test_milter_round_trip_with_bytes(db, daemon):
    _setup_rule()
    daemon.refresh_configuration(force=True)
    milter = daemon.DisclaimrMilter()
    milter.replBody = MagicMock()
    milter.addHeader = MagicMock()
    milter.chgHeader = MagicMock()

    milter.connect(b"mx.example.com", b"4", b"10.0.0.1", 25, {})

    for text in (b"first mail", b"second mail"):
        milter.mailFrom(b"<alice@example.com>", {b"i": b"4F2A1", b"mail_addr": b"alice@example.com"})
        milter.rcpt(b"<bob@example.org>", {b"i": b"4F2A1"})
        for key, value in _PLAIN_8BIT:
            milter.header(key.encode(), value.encode(), {b"i": b"4F2A1"})
        milter.eoh({})
        milter.body(text, {})
        milter.eob({})

    first, second = (call.args[0] for call in milter.replBody.call_args_list)
    assert isinstance(second, bytes)
    assert b"first mail" in first and b"Signature" in first
    assert b"second mail" in second and b"first mail" not in second
