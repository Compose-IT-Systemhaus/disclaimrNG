"""Tests for the SignatureImageQuickUploadView endpoint."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image

from disclaimrwebadmin.models import SignatureImage


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color="blue").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="up", password="pw", is_staff=True
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)


def test_upload_creates_signature_image(staff_client):
    upload = SimpleUploadedFile("acme-logo.png", _png_bytes(), content_type="image/png")
    response = staff_client.post(
        reverse("disclaimrwebadmin:signatureimage-quick-upload"),
        data={"image": upload},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["slug"] == "acme-logo"
    assert payload["url"].endswith(".png")
    assert SignatureImage.objects.filter(slug="acme-logo").exists()


def test_upload_collision_gets_unique_slug(staff_client):
    SignatureImage.objects.create(
        slug="logo",
        name="Existing",
        image=SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png"),
    )
    upload = SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png")
    response = staff_client.post(
        reverse("disclaimrwebadmin:signatureimage-quick-upload"),
        data={"image": upload},
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "logo-2"


def test_upload_without_file_returns_400(staff_client):
    response = staff_client.post(
        reverse("disclaimrwebadmin:signatureimage-quick-upload"),
        data={},
    )
    assert response.status_code == 400
    assert "image" in response.json()["error"].lower()


def test_anonymous_upload_is_rejected(client):
    response = client.post(
        reverse("disclaimrwebadmin:signatureimage-quick-upload"),
        data={},
    )
    assert response.status_code in (302, 403)


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_vocabulary_endpoint_includes_image_url(staff_client):
    SignatureImage.objects.create(
        slug="hero",
        name="Hero",
        image=SimpleUploadedFile("hero.png", _png_bytes(), content_type="image/png"),
    )
    response = staff_client.get(
        reverse("disclaimrwebadmin:directoryserver-vocabulary")
    )
    images = response.json()["images"]
    assert images[0]["slug"] == "hero"
    assert "url" in images[0] and images[0]["url"]
