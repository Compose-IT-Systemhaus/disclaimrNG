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


def test_every_toc_page_exists_in_english():
    from disclaimrwebadmin.views.docs import DOCS_ROOT, TOC

    missing = [slug for slug, _title in TOC if not (DOCS_ROOT / "en" / f"{slug}.md").is_file()]
    assert not missing


@pytest.mark.parametrize("language", ["en", "de"])
def test_stalwart_runbook_renders_with_working_anchors(staff_client, language):
    import re

    staff_client.cookies["django_language"] = language
    response = staff_client.get(
        reverse("disclaimrwebadmin:docs-page", kwargs={"slug": "stalwart-active-directory"})
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "disclaimrng-milter" in html
    assert ("Schritt 8" if language == "de" else "Step 8") in html  # the right language was served
    # Every in-page link (#step-…) must point at a heading id.
    ids = set(re.findall(r'id="([^"]+)"', html))
    links = set(re.findall(r'href="#([^"]+)"', html))
    assert links <= ids, links - ids
