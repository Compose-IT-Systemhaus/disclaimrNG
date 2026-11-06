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
    assert workflow["repl_body"].startswith("Note: please read\r\nSecond line")


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
        milter.eob({b"i": b"4F2A1"})

    first, second = (call.args[0] for call in milter.replBody.call_args_list)
    assert isinstance(second, bytes)
    assert b"first mail" in first and b"Signature" in first
    assert b"second mail" in second and b"first mail" not in second

    # Every changed mail leaves one entry for the admin's "Logs" view.
    entries = list(models.MailLog.objects.order_by("id"))
    assert len(entries) == 2
    assert entries[0].queue_id == "4F2A1"
    assert entries[0].sender == "alice@example.com"
    assert entries[0].recipient == "bob@example.org"
    assert entries[0].sender_ip == "10.0.0.1"
    assert entries[0].applied == "r → a → d"
    assert entries[0].processed


def _run_mail(daemon, sender=b"alice@example.com"):
    milter = daemon.DisclaimrMilter()
    milter.replBody = MagicMock()
    milter.addHeader = MagicMock()
    milter.chgHeader = MagicMock()
    milter.connect(b"mx.example.com", b"4", b"10.0.0.1", 25, {})
    milter.mailFrom(b"<" + sender + b">", {b"i": b"9Z", b"mail_addr": sender})
    milter.rcpt(b"<bob@example.org>", {b"i": b"9Z"})
    milter.header(b"Subject", b"Quarterly report", {b"i": b"9Z"})
    milter.eoh({})
    milter.body(b"text", {})
    milter.eob({b"i": b"9Z"})
    return milter


def test_mail_without_matching_rule_is_logged_as_unprocessed(db, daemon):
    _setup_rule()
    models.Requirement.objects.update(sender=r"@other\.com$")
    daemon.refresh_configuration(force=True)

    milter = _run_mail(daemon)

    milter.replBody.assert_not_called()
    (entry,) = models.MailLog.objects.all()
    assert not entry.processed
    assert (entry.sender, entry.recipient, entry.subject, entry.applied) == (
        "alice@example.com",
        "bob@example.org",
        "Quarterly report",
        "",
    )


def test_old_log_entries_are_pruned_by_the_milter(db, daemon, settings):
    _setup_rule()
    old = models.MailLog.objects.create(sender="old@example.com")
    models.MailLog.objects.filter(pk=old.pk).update(created="2020-01-01T00:00:00Z")
    models.MailLog.objects.create(sender="new@example.com")

    settings.MAIL_LOG_RETENTION_DAYS = 0
    daemon.refresh_configuration(force=True)
    assert models.MailLog.objects.count() == 2  # 0 keeps everything

    settings.MAIL_LOG_RETENTION_DAYS = 90
    daemon.refresh_configuration(force=True)
    assert list(models.MailLog.objects.values_list("sender", flat=True)) == ["new@example.com"]


# ---------------------------------------------------------------------------
# Recipient regex: at least one recipient has to match
# ---------------------------------------------------------------------------


def _send_to(recipients, headers=_PLAIN_8BIT):
    helper = _connected_helper()
    helper.mail_from("alice@example.com", {})
    for recipient in recipients:
        helper.rcpt(recipient, {})
    for key, value in headers:
        helper.header(key, value, {})
    helper.eoh({})
    helper.body(b"hello", {})
    return helper, helper.eob({})


def test_requirement_matches_when_any_recipient_matches(db):
    _setup_rule()
    models.Requirement.objects.update(recipient=r"@customer\.com$")

    # The matching recipient is not the first one.
    helper, workflow = _send_to(["colleague@example.com", "bob@customer.com"])

    assert b"Signature" in workflow["repl_body"].encode()
    assert helper.mail_data["envelope_rcpt"] == "bob@customer.com"


def test_requirement_without_any_matching_recipient_is_dropped(db):
    _setup_rule()
    models.Requirement.objects.update(recipient=r"@customer\.com$")

    helper, workflow = _send_to(["a@example.com", "b@example.com"])

    assert workflow is None
    assert not helper.enabled


def test_mail_without_content_transfer_encoding_gets_a_valid_one(db):
    _setup_rule()

    _, workflow = _send_to(["bob@example.org"], headers=[("Content-Type", "text/plain")])

    assert workflow["add_header"]["Content-Transfer-Encoding"] == "7bit"


# ---------------------------------------------------------------------------
# Failures that used to make the MTA defer every mail
# ---------------------------------------------------------------------------


def test_invalid_regex_is_rejected_when_saving(db):
    from django.core.exceptions import ValidationError

    rule = models.Rule.objects.create(name="r")
    with pytest.raises(ValidationError) as exc:
        models.Requirement(rule=rule, name="req", sender="*@example.com").full_clean()
    assert "sender" in exc.value.message_dict

    disclaimer = models.Disclaimer.objects.create(name="d", text="x")
    action = models.Action(
        rule=rule,
        disclaimer=disclaimer,
        position=0,
        name="a",
        action=constants.ACTION_ACTION_REPLACETAG,
        action_parameters="(unclosed",
    )
    with pytest.raises(ValidationError) as exc:
        action.full_clean()
    assert "action_parameters" in exc.value.message_dict


def test_unexpected_ldap_errors_skip_the_server_instead_of_raising():
    import ldap

    server = MagicMock()
    server.auth = constants.DIR_AUTH_NONE
    for failing in ("simple_bind_s", "search_s"):
        conn = MagicMock()
        getattr(conn, failing).side_effect = ldap.OPERATIONS_ERROR({"desc": "bind required"})
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(milter_helper.ldap, "initialize", lambda url, conn=conn: conn)
            assert MilterHelper._search_url(server, MagicMock(url="ldap://x"), "(x)", None) is None


def test_empty_html_part_is_left_alone(db):
    _setup_rule(html="<p>Signature</p>", html_use_text=False)
    headers = [("Content-Type", "text/html; charset=utf-8"), ("Content-Transfer-Encoding", "8bit")]
    workflow = _send(_connected_helper(), headers, [b"  \n"])
    assert workflow["repl_body"].strip() == ""


def test_callback_errors_are_logged_with_a_traceback(db, daemon, caplog):
    milter = daemon.DisclaimrMilter()
    boom = MagicMock(side_effect=RuntimeError("boom"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(daemon.lm.MilterProtocol, "dataReceived", boom)
        with pytest.raises(RuntimeError):
            milter.dataReceived(b"")
    assert "Unhandled error" in caplog.text and "RuntimeError: boom" in caplog.text


# ---------------------------------------------------------------------------
# Stalwart as the MTA: one connection per mail, no queue-id macro
# ---------------------------------------------------------------------------


def test_milter_session_as_stalwart_sends_it(db, daemon, caplog):
    """Stalwart replays connect, EHLO, MAIL, RCPT, DATA, headers and body in one
    connection and sends no ``i`` (queue id) macro at the DATA stage."""
    _setup_rule()
    daemon.refresh_configuration(force=True)
    milter = daemon.DisclaimrMilter()
    milter.replBody = MagicMock()
    milter.addHeader = MagicMock()
    milter.chgHeader = MagicMock()

    milter.connect(b"client.example.com", b"4", b"192.0.2.10", 51234, {b"{client_addr}": b"192.0.2.10"})
    milter.helo(b"client.example.com")
    milter.mailFrom(
        b"<alice@example.com>",
        {b"{mail_addr}": b"alice@example.com", b"{auth_authen}": b"alice@example.com"},
    )
    milter.rcpt(b"<bob@example.org>", {b"{rcpt_addr}": b"bob@example.org"})
    for key, value in _PLAIN_8BIT:
        milter.header(key.encode(), value.encode(), {})
    milter.eoh({})
    milter.body(b"Hello\r\nworld\r\n", {})
    milter.eob({})
    milter.close()

    body = milter.replBody.call_args.args[0]
    assert b"Hello" in body and b"Signature" in body
    assert "could not be processed" not in caplog.text


def test_active_directory_default_query_has_two_placeholders_and_still_resolves(db):
    """``(|(mail=%s)(userPrincipalName=%s))`` used to raise "not enough arguments"."""
    server = models.DirectoryServer.objects.create(
        name="AD",
        flavor=constants.DIR_FLAVOR_AD,
        base_dn="dc=example,dc=com",
        search_query=constants.DIR_FLAVOR_DEFAULT_QUERY[constants.DIR_FLAVOR_AD],
        auth=constants.DIR_AUTH_NONE,
        enable_cache=False,
    )
    models.DirectoryServerURL.objects.create(directory_server=server, url="ldaps://dc1", position=0)
    _setup_rule(text='{resolver["displayname"]}')
    action = models.Action.objects.get()
    action.directory_servers.add(server)
    action.resolve_sender = True
    action.save()

    helper = _connected_helper()
    helper.mail_from("alice@example.com", {})
    seen = []

    def fake_search(directory_server, url, query, attrlist):
        seen.append(query)
        return [("CN=Alice", {"displayName": [b"Alice Example"]})]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(MilterHelper, "_search_url", staticmethod(fake_search))
        resolved, attributes = helper._lookup_sender(action)

    assert resolved
    assert attributes["displayname"] == "Alice Example"
    assert seen == ["(|(mail=alice@example.com)(userPrincipalName=alice@example.com))"]


def test_replacement_body_uses_crlf_only(db):
    """Stalwart writes the replacement body as it is: no bare LF may reach it."""
    _setup_rule()
    workflow = _send(_connected_helper(), _PLAIN_8BIT, [b"first line\nsecond line\r\nthird"])
    body = workflow["repl_body"]
    assert "Signature" in body and "\r\n" in body
    assert "\n" not in body.replace("\r\n", "")


def test_database_connection_is_released_after_every_mail(db, daemon):
    _setup_rule()
    daemon.refresh_configuration(force=True)
    milter = daemon.DisclaimrMilter()
    milter.replBody = MagicMock()
    milter.addHeader = MagicMock()
    milter.chgHeader = MagicMock()
    milter.connect(b"mx", b"4", b"10.0.0.1", 25, {})
    milter.mailFrom(b"<alice@example.com>", {})
    milter.rcpt(b"<bob@example.org>", {})
    for key, value in _PLAIN_8BIT:
        milter.header(key.encode(), value.encode(), {})
    milter.eoh({})
    milter.body(b"hello", {})

    with pytest.MonkeyPatch.context() as patch:
        closed = MagicMock()
        patch.setattr(daemon.connections, "close_all", closed)
        milter.eob({})
    assert closed.called


def test_milter_does_not_shadow_libmilter_internals(daemon):
    """python-libmilter dispatches through private methods (``_eob``, ``_rcpt``, ...);
    a method of the same name in our subclass breaks every real mail while the unit
    tests, which call ``eob()`` directly, stay green."""
    internals = {n for n in dir(daemon.lm.MilterProtocol) if n.startswith("_") and not n.startswith("__")}
    ours = {n for n in vars(daemon.DisclaimrMilter) if n.startswith("_") and not n.startswith("__")}
    assert not internals & ours, internals & ours
