"""Smoke tests for the SignatureTestView admin tool."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="op", password="pw", is_staff=True
    )
    client = Client()
    client.force_login(user)
    return client


def test_get_renders_form_with_defaults(staff_client):
    response = staff_client.get(reverse("disclaimrwebadmin:signature-test"))
    assert response.status_code == 200
    # Page title appears in the <title> element regardless of language.
    assert b"Signature test" in response.content
    assert b"alice@example.com" in response.content


def test_post_with_no_rules_falls_through(staff_client):
    response = staff_client.post(
        reverse("disclaimrwebadmin:signature-test"),
        data={
            "sender": "alice@example.com",
            "recipient": "bob@external.tld",
            "subject": "Hi",
            "body": "Hallo Welt",
            "content_type": "text/plain",
            "sender_ip": "127.0.0.1",
        },
    )
    assert response.status_code == 200
    # No requirements configured → pipeline passes the mail through.
    # Source strings (English) are what we get back when the test runs
    # under the default ``en-us`` locale; the actual text comes from
    # _passthrough_outcome's ``summary``.
    assert (
        b"did not match any requirement" in response.content
        or b"No active rule matched" in response.content
    )


def test_anonymous_request_is_redirected(client):
    response = client.get(reverse("disclaimrwebadmin:signature-test"))
    assert response.status_code in (302, 403)
