"""The "Logs" view lists milter activity and is for administrators only."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from disclaimrwebadmin.models import MailLog

URL = "admin:disclaimrwebadmin_maillog_changelist"


def _client(**kwargs) -> Client:
    user = get_user_model().objects.create_user(username="u", password="pw", **kwargs)
    client = Client()
    client.force_login(user)
    return client


def test_superuser_sees_logged_mails_and_sidebar_entry(db):
    MailLog.objects.create(
        sender="alice@example.com", subject="Hello", applied="Rule → Action → Footer"
    )
    client = _client(is_staff=True, is_superuser=True)

    response = client.get(reverse(URL))

    assert response.status_code == 200
    content = response.content.decode()
    assert "alice@example.com" in content
    assert "Rule → Action → Footer" in content
    assert reverse(URL) in client.get(reverse("admin:index")).content.decode()


def test_unprocessed_mails_are_listed_but_can_be_filtered_out(db):
    MailLog.objects.create(sender="signed@example.com", processed=True, applied="R → A → S")
    MailLog.objects.create(sender="plain@example.com")
    client = _client(is_staff=True, is_superuser=True)

    everything = client.get(reverse(URL)).content.decode()
    only_signed = client.get(reverse(URL), {"processed__exact": "1"}).content.decode()

    assert "signed@example.com" in everything and "plain@example.com" in everything
    assert "signed@example.com" in only_signed and "plain@example.com" not in only_signed


def test_staff_with_view_permission_is_still_locked_out(db):
    client = _client(is_staff=True)
    get_user_model().objects.get(username="u").user_permissions.add(
        Permission.objects.get(codename="view_maillog")
    )

    assert client.get(reverse(URL)).status_code == 403
    assert reverse(URL) not in client.get(reverse("admin:index")).content.decode()


def test_logs_cannot_be_added_or_edited(db):
    entry = MailLog.objects.create(sender="a@example.com")
    client = _client(is_staff=True, is_superuser=True)

    assert client.get(reverse("admin:disclaimrwebadmin_maillog_add")).status_code == 403
    # The detail page is read-only: no form fields to post.
    assert b'name="sender"' not in client.get(
        reverse("admin:disclaimrwebadmin_maillog_change", args=[entry.pk])
    ).content
