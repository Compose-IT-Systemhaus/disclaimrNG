"""Signature formatting: default font, text part generated from HTML, editor font list."""

from __future__ import annotations

import email
import json
from email.mime.text import MIMEText

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from disclaimr.milter_helper import MilterHelper
from disclaimrwebadmin import constants, models
from disclaimrwebadmin.admin import DisclaimerAdmin, DisclaimerForm
from disclaimrwebadmin.widgets import TemplateEditorWidget
from tests.test_milter_pipeline import _connected_helper, _send, _setup_rule, _split_mime

CALIBRI = "Calibri, Arial, sans-serif"


def _html_after_signing(disclaimer_kwargs: dict, *, action=constants.ACTION_ACTION_ADD) -> str:
    disclaimer = _setup_rule(text="Alice")
    models.Disclaimer.objects.filter(pk=disclaimer.pk).update(**disclaimer_kwargs)
    models.Action.objects.update(action=action, action_parameters="#SIG#")
    headers, body = _split_mime(MIMEText("<p>Hello #SIG#</p>", "html", "utf-8"))
    workflow = _send(_connected_helper(), headers, [body])
    rebuilt = email.message_from_string(
        "\n".join(f"{k}: {v}" for k, v in headers) + "\n\n" + workflow["repl_body"]
    )
    return MilterHelper.decode_mail(rebuilt)[1]


def test_html_signature_gets_the_default_font(db):
    html = _html_after_signing({"font_family": CALIBRI, "font_size": 10})
    assert '<div style="font-family: Calibri, Arial, sans-serif; font-size: 10pt">' in html
    assert "<br><br>Alice</div>" in html


def test_without_default_font_the_div_has_no_style(db):
    html = _html_after_signing({})
    assert "<div>\n<br><br>Alice</div>" in html


def test_replace_tag_without_default_font_stays_inline(db):
    assert "Hello Alice" in _html_after_signing({}, action=constants.ACTION_ACTION_REPLACETAG)


def test_replace_tag_with_default_font_is_wrapped(db):
    styled = _html_after_signing({"font_size": 12}, action=constants.ACTION_ACTION_REPLACETAG)
    assert 'Hello <div style="font-size: 12pt">Alice</div>' in styled


def test_plain_text_part_is_not_touched_by_the_font(db):
    disclaimer = _setup_rule(text="Alice")
    models.Disclaimer.objects.filter(pk=disclaimer.pk).update(font_family=CALIBRI)
    headers = [("From", "alice@example.com"), ("Content-Type", "text/plain; charset=utf-8")]
    body = _send(_connected_helper(), headers, [b"Hello\n"])["repl_body"]
    assert "Alice" in body and "font-family" not in body


def test_preview_shows_the_default_font_and_ignores_unknown_values(client, db):
    client.force_login(get_user_model().objects.create_superuser("root", "r@x.de", "pw"))
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    page = client.post(
        url, {"content": "<p>Hi</p>", "content_type": "text/html",
              "font_family": CALIBRI, "font_size": "11"},
    ).content.decode()  # fmt: skip
    assert 'style="font-family: Calibri, Arial, sans-serif; font-size: 11pt"' in page
    hostile = client.post(
        url, {"content": "<p>Hi</p>", "content_type": "text/html",
              "font_family": 'x"><script>alert(1)</script>', "font_size": "7"},
    ).content.decode()  # fmt: skip
    assert "<script>" not in hostile and "font-size" not in hostile


def _form(**overrides) -> DisclaimerForm:
    data = {
        "name": "Signature", "description": "", "text": "old text", "text_charset": "utf-8",
        "text_use_template": "on", "html": '<p>{resolver["cn"]}<br>CEO</p>{image["logo"]}',
        "html_charset": "utf-8", "html_use_template": "on", "font_family": "", "font_size": "",
        "text_from_html": "on",
    }  # fmt: skip
    data.update(overrides)
    return DisclaimerForm(data=data)


def test_text_part_is_generated_from_the_html(db):
    form = _form()
    assert form.is_valid(), form.errors
    assert form.save().text == '{resolver["cn"]}\nCEO'


def test_text_part_stays_as_written_without_the_switch(db):
    form = _form(text_from_html="")
    assert form.is_valid(), form.errors
    assert form.save().text == "old text"


def test_html_from_text_and_text_from_html_exclude_each_other(db):
    form = _form(html_use_text="on")
    assert not form.is_valid()
    assert form.non_field_errors()


def test_new_signatures_start_in_the_html_workflow(db):
    model_admin = DisclaimerAdmin(models.Disclaimer, admin.site)
    initial = model_admin.get_changeform_initial_data(RequestFactory().get("/"))
    assert initial["text_from_html"] is True and initial["html_use_text"] is False


def test_editor_gets_the_font_list(db):
    context = TemplateEditorWidget(content_type="text/html").get_context("html", "", {"id": "x"})
    fonts = json.loads(context["widget"]["fonts_json"])
    assert ["Calibri", CALIBRI] in fonts["families"]
    assert fonts["sizes"] == constants.SIGNATURE_FONT_SIZES
