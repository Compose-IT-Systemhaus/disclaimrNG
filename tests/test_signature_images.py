"""Tests for the SignatureImage substitution paths.

Covers both the milter-side renderer (``disclaimr.milter_helper`` —
``_build_image_replacements``) and the admin-side preview renderer
(``disclaimrwebadmin.views.preview`` — ``_build_image_table`` and the full
``DisclaimerPreviewView`` round-trip), plus the vocabulary endpoint that
feeds the template-editor autocomplete.
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image

from disclaimr.milter_helper import _build_image_replacements
from disclaimrwebadmin.models import SignatureImage
from disclaimrwebadmin.views.preview import _build_image_table


def _png_bytes(color: str = "red") -> bytes:
    """Return a 1×1 PNG as bytes — the smallest valid Pillow can produce."""
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _make_image(slug: str, **kwargs) -> SignatureImage:
    defaults = {
        "name": slug.title(),
        "image": SimpleUploadedFile(
            f"{slug}.png", _png_bytes(), content_type="image/png"
        ),
    }
    defaults.update(kwargs)
    return SignatureImage.objects.create(slug=slug, **defaults)


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path, settings):
    """Redirect MEDIA_ROOT to a per-test tmp dir so uploaded files don't
    leak into the working tree across runs."""
    settings.MEDIA_ROOT = str(tmp_path)


# ---------------------------------------------------------------------------
# milter-side: _build_image_replacements
# ---------------------------------------------------------------------------


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_milter_html_renders_img_tag(db):
    _make_image("logo", alt_text="Acme Logo", width=120, height=40)
    rendered = _build_image_replacements(
        'Hello <p>{image["logo"]}</p>', "text/html"
    )
    fragment = rendered["logo"]
    assert fragment.startswith("<img ")
    assert 'src="https://signatures.example.com/signatures/logo/' in fragment
    assert 'alt="Acme Logo"' in fragment
    assert 'width="120"' in fragment
    assert 'height="40"' in fragment


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_milter_plaintext_renders_bare_url(db):
    _make_image("logo")
    rendered = _build_image_replacements('see {image["logo"]}', "text/plain")
    assert rendered["logo"].startswith("https://signatures.example.com/signatures/logo/")
    assert "<img" not in rendered["logo"]


def test_milter_returns_empty_when_no_tags(db):
    _make_image("logo")
    assert _build_image_replacements("plain text, no tags here", "text/html") == {}


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_milter_omits_unknown_slugs(db):
    _make_image("logo")
    rendered = _build_image_replacements(
        '{image["logo"]} and {image["missing"]}', "text/html"
    )
    assert "logo" in rendered
    assert "missing" not in rendered


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_milter_alt_falls_back_to_name(db):
    _make_image("logo", name="Brand Mark", alt_text="")
    rendered = _build_image_replacements('{image["logo"]}', "text/html")
    assert 'alt="Brand Mark"' in rendered["logo"]


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_milter_handles_multiple_images(db):
    _make_image("logo", name="Logo")
    _make_image("badge", name="Badge")
    rendered = _build_image_replacements(
        'one {image["logo"]} two {image["badge"]}', "text/plain"
    )
    assert set(rendered) == {"logo", "badge"}


# ---------------------------------------------------------------------------
# preview view: _build_image_table + the full HTTP round-trip
# ---------------------------------------------------------------------------


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_preview_table_html(db):
    _make_image("logo", alt_text="Logo", width=80)
    table = _build_image_table('{image["logo"]}', "text/html")
    fragment = table["logo"]
    assert fragment.startswith("<img ")
    assert 'width="80"' in fragment
    assert "https://signatures.example.com/signatures/logo/" in fragment


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_preview_table_plaintext(db):
    _make_image("logo")
    table = _build_image_table('{image["logo"]}', "text/plain")
    assert table["logo"].startswith("https://signatures.example.com/")
    assert "<img" not in table["logo"]


def test_preview_table_empty_without_tags(db):
    _make_image("logo")
    assert _build_image_table("nothing to see", "text/html") == {}


@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="img-admin", password="pw", is_staff=True
    )
    client = Client()
    client.force_login(user)
    return client


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_preview_view_substitutes_html_image(staff_client):
    _make_image("logo", name="Acme", alt_text="Acme")
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    response = staff_client.post(
        url,
        data={
            "content": '<p>Hi {resolver["cn"]} {image["logo"]}</p>',
            "content_type": "text/html",
        },
    )
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "<img " in text
    assert "https://signatures.example.com/signatures/logo/" in text
    # The {image[...]} marker must be gone after substitution.
    assert '{image["logo"]}' not in text


@override_settings(MEDIA_BASE_URL="https://signatures.example.com")
def test_preview_view_substitutes_plaintext_image(staff_client):
    _make_image("logo")
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    response = staff_client.post(
        url,
        data={"content": 'see {image["logo"]}', "content_type": "text/plain"},
    )
    text = response.content.decode("utf-8")
    # Plaintext renders inside <pre> with HTML-escaping; the URL itself must
    # appear verbatim and there must NOT be an <img> tag inserted.
    assert "https://signatures.example.com/signatures/logo/" in text
    assert "&lt;img" not in text


def test_preview_view_unknown_image_becomes_empty(staff_client):
    url = reverse("disclaimrwebadmin:disclaimer-preview")
    response = staff_client.post(
        url,
        data={
            "content": "before {image[\"ghost\"]} after",
            "content_type": "text/html",
        },
    )
    text = response.content.decode("utf-8")
    assert "before  after" in text


# ---------------------------------------------------------------------------
# vocabulary endpoint: images list feeds the template-editor autocomplete
# ---------------------------------------------------------------------------


def test_vocabulary_endpoint_lists_images(staff_client):
    _make_image("logo", name="Acme Logo")
    _make_image("badge", name="Trust Badge")
    url = reverse("disclaimrwebadmin:directoryserver-vocabulary")
    response = staff_client.get(url)
    assert response.status_code == 200
    payload = response.json()
    slugs = {img["slug"] for img in payload["images"]}
    assert slugs == {"logo", "badge"}
    names = {img["name"] for img in payload["images"]}
    assert names == {"Acme Logo", "Trust Badge"}
