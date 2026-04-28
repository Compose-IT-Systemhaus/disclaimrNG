"""Smoke tests for the in-admin documentation view."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse


@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="reader", password="pw", is_staff=True
    )
    client = Client()
    client.force_login(user)
    return client


def test_docs_index_renders(staff_client):
    response = staff_client.get(reverse("disclaimrwebadmin:docs-index"))
    assert response.status_code == 200
    assert b"Documentation" in response.content


def test_docs_walkthrough_page_renders(staff_client):
    response = staff_client.get(
        reverse("disclaimrwebadmin:docs-page", kwargs={"slug": "walkthrough"})
    )
    assert response.status_code == 200
    # The walkthrough mentions "@example.com" prominently.
    assert b"example.com" in response.content


def test_unknown_docs_slug_404s(staff_client):
    response = staff_client.get(
        reverse("disclaimrwebadmin:docs-page", kwargs={"slug": "doesnotexist"})
    )
    assert response.status_code == 404


def test_anonymous_request_is_redirected(client):
    response = client.get(reverse("disclaimrwebadmin:docs-index"))
    assert response.status_code in (302, 403)
