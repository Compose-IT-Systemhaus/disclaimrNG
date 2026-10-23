"""Admin dashboard and login page."""

from __future__ import annotations

import pytest
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from disclaimrwebadmin.models import Action, Disclaimer, Rule


@pytest.fixture
def admin_user(db):
    return get_user_model().objects.create_superuser(
        username="op", password="pw", email="op@example.com", first_name="Olga"
    )


@pytest.fixture
def admin_client(admin_user) -> Client:
    client = Client()
    client.force_login(admin_user)
    return client


def test_dashboard_shows_setup_checklist_on_empty_install(admin_client):
    response = admin_client.get(reverse("admin:index"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Welcome back, Olga" in content
    assert "Getting started" in content
    assert reverse("admin:disclaimrwebadmin_disclaimer_add") in content


def test_dashboard_hides_checklist_once_required_steps_are_done(admin_client):
    disclaimer = Disclaimer.objects.create(name="Default")
    rule = Rule.objects.create(name="All mail")
    Action.objects.create(rule=rule, disclaimer=disclaimer, position=0, name="Add")

    content = admin_client.get(reverse("admin:index")).content.decode()
    assert "Getting started" not in content
    assert "1 active" in content


def test_dashboard_lists_own_recent_changes(admin_client, admin_user):
    rule = Rule.objects.create(name="Outgoing mail")
    LogEntry.objects.create(
        user=admin_user,
        content_type=ContentType.objects.get_for_model(Rule),
        object_id=str(rule.pk),
        object_repr=str(rule),
        action_flag=ADDITION,
    )

    content = admin_client.get(reverse("admin:index")).content.decode()
    assert "Outgoing mail" in content
    assert reverse("admin:disclaimrwebadmin_rule_change", args=[rule.pk]) in content


def test_dashboard_renders_for_staff_without_model_permissions(db):
    user = get_user_model().objects.create_user(username="viewer", password="pw", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    assert reverse("admin:disclaimrwebadmin_disclaimer_add") not in response.content.decode()


def test_login_page_keeps_redirect_target(client, db):
    response = client.get(reverse("admin:login"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Sign in" in content
    assert 'name="next" value="/"' in content
