"""Tests for :class:`disclaimrwebadmin.views.preview.DisclaimerPreviewView`."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="alice", password="pw", is_staff=True
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def anon_client() -> Client:
    return Client()


def test_anonymous_request_is_redirected(anon_client):
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    response = anon_client.post(url, data={"content": "hi", "content_type": "text/html"})
    # staff_member_required redirects to admin login.
    assert response.status_code in (302, 403)


def test_html_preview_substitutes_resolver_tags(staff_client):
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    body = '<p>Hello {resolver["cn"]}, sender={sender}</p>'
    response = staff_client.post(
        url,
        data={"content": body, "content_type": "text/html"},
    )
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "Alice Example" in text
    assert "alice@example.com" in text
    # Make sure the unresolved template marker is gone.
    assert '{resolver["cn"]}' not in text


def test_plaintext_preview_is_html_escaped(staff_client):
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    body = "Hello <world> {sender}"
    response = staff_client.post(
        url,
        data={"content": body, "content_type": "text/plain"},
    )
    text = response.content.decode("utf-8")
    assert "&lt;world&gt;" in text
    assert "alice@example.com" in text


def test_unknown_tag_becomes_empty_string(staff_client):
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    response = staff_client.post(
        url,
        data={"content": "before {nope} after", "content_type": "text/html"},
    )
    text = response.content.decode("utf-8")
    assert "before  after" in text
