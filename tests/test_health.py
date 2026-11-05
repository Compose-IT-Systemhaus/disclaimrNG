"""Container healthcheck endpoint and sidebar permissions."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse


def test_healthz_is_public_and_reports_ok(client, db):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_reports_503_when_the_database_is_down(client, db):
    with patch.object(connection, "cursor", side_effect=RuntimeError("db down")):
        response = client.get("/healthz")
    assert response.status_code == 503


def test_sidebar_only_lists_what_the_user_may_see(db):
    user = get_user_model().objects.create_user(username="plain", password="pw", is_staff=True)
    client = Client()
    client.force_login(user)
    content = client.get(reverse("admin:index")).content.decode()
    assert reverse("admin:disclaimrwebadmin_rule_changelist") not in content
    assert reverse("admin:auth_user_changelist") not in content

    admin = get_user_model().objects.create_superuser(username="root", password="pw")
    client.force_login(admin)
    content = client.get(reverse("admin:index")).content.decode()
    assert reverse("admin:disclaimrwebadmin_rule_changelist") in content
