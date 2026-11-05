"""The admin's own views follow model permissions, not just ``is_staff``."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer


@pytest.fixture
def plain_staff_client(db) -> Client:
    user = get_user_model().objects.create_user(username="plain", password="pw", is_staff=True)
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    ("name", "method", "uses_pk"),
    [
        ("directoryserver-test", "post", True),
        ("directoryserver-attributes", "post", True),
        ("directoryserver-vocabulary", "get", False),
        ("disclaimer-preview", "post", False),
        ("signature-test", "get", False),
    ],
)
def test_staff_without_model_permissions_is_forbidden(plain_staff_client, name, method, uses_pk):
    args = []
    if uses_pk:
        args = [DirectoryServer.objects.create(name="s", base_dn="dc=x", auth=constants.DIR_AUTH_NONE).pk]
    response = getattr(plain_staff_client, method)(reverse(f"disclaimrwebadmin:{name}", args=args))
    assert response.status_code == 403


def test_dashboard_hides_signature_test_without_permission(plain_staff_client):
    content = plain_staff_client.get(reverse("admin:index")).content.decode()
    assert "Run signature test" not in content
