"""The built-in roles Admins, Editor and Reader and what each of them may do."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from disclaimrwebadmin import models
from disclaimrwebadmin.roles import ADMINS, EDITOR, READER, ensure_default_groups


def _client(client, role: str):
    user = get_user_model().objects.create_user(role.lower(), password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name=role))
    client.force_login(user)
    return client


def _perms(role: str) -> set[str]:
    return {p.codename for p in Group.objects.get(name=role).permissions.all()}


def _status(client, name: str, *args) -> int:
    return client.get(reverse(f"admin:{name}", args=args)).status_code


@pytest.fixture
def content(db):
    rule = models.Rule.objects.create(name="r")
    return {"rule": rule}


def test_roles_exist_after_migrate(db):
    assert set(Group.objects.values_list("name", flat=True)) >= {ADMINS, EDITOR, READER}


def test_permissions_of_the_roles(db):
    reader, editor, admins = _perms(READER), _perms(EDITOR), _perms(ADMINS)
    assert {"view_rule", "view_disclaimer", "view_signatureimage", "view_action"} <= reader
    assert not {p for p in reader if not p.startswith("view_")}
    assert {"add_rule", "change_rule", "add_disclaimer", "change_signatureimage"} <= editor
    assert not {p for p in editor if p.startswith("delete_")}
    assert not {"view_directoryserver", "change_directoryserver", "view_maillog"} & editor
    assert {"delete_rule", "change_directoryserver", "change_tenant", "add_user", "add_group"} <= admins


def test_existing_roles_keep_their_customised_permissions_until_reset(db):
    group = Group.objects.get(name=READER)
    group.permissions.clear()

    assert ensure_default_groups() == []
    assert _perms(READER) == set()

    call_command("sync_roles", "--reset")
    assert "view_rule" in _perms(READER)


def test_reader_may_look_but_not_touch(client, content):
    _client(client, READER)
    rule = content["rule"].pk
    assert _status(client, "disclaimrwebadmin_rule_changelist") == 200
    assert _status(client, "disclaimrwebadmin_rule_change", rule) == 200
    assert _status(client, "disclaimrwebadmin_disclaimer_changelist") == 200
    assert _status(client, "disclaimrwebadmin_signatureimage_changelist") == 200
    assert _status(client, "disclaimrwebadmin_rule_add") == 403
    assert _status(client, "disclaimrwebadmin_disclaimer_add") == 403
    assert _status(client, "disclaimrwebadmin_rule_delete", rule) == 403
    assert client.post(reverse("admin:disclaimrwebadmin_rule_change", args=[rule]), {"name": "x"}).status_code == 403
    assert _status(client, "disclaimrwebadmin_directoryserver_changelist") == 403
    assert _status(client, "disclaimrwebadmin_tenant_changelist") == 403
    assert _status(client, "disclaimrwebadmin_maillog_changelist") == 403
    assert _status(client, "auth_user_changelist") == 403
    assert client.get(reverse("disclaimrwebadmin:signature-test")).status_code == 200


def test_editor_creates_and_changes_but_does_not_delete(client, content):
    _client(client, EDITOR)
    rule = content["rule"].pk
    assert _status(client, "disclaimrwebadmin_rule_add") == 200
    assert _status(client, "disclaimrwebadmin_rule_change", rule) == 200
    assert _status(client, "disclaimrwebadmin_disclaimer_add") == 200
    assert _status(client, "disclaimrwebadmin_signatureimage_add") == 200
    assert _status(client, "disclaimrwebadmin_rule_delete", rule) == 403
    assert _status(client, "disclaimrwebadmin_directoryserver_changelist") == 403
    assert _status(client, "auth_user_changelist") == 403
    answer = client.get(
        reverse("admin:autocomplete"),
        {"term": "", "app_label": "disclaimrwebadmin", "model_name": "rule", "field_name": "tenant"},
    )
    assert answer.status_code == 200


def test_editor_saves_a_rule(client, content):
    _client(client, EDITOR)
    rule = content["rule"]
    data = {
        "name": "renamed", "description": "", "position": "0", "tenant": "",
        "requirement_set-TOTAL_FORMS": "0", "requirement_set-INITIAL_FORMS": "0",
        "action_set-TOTAL_FORMS": "0", "action_set-INITIAL_FORMS": "0",
    }  # fmt: skip
    client.post(reverse("admin:disclaimrwebadmin_rule_change", args=[rule.pk]), data)
    rule.refresh_from_db()
    assert rule.name == "renamed"


def test_admins_may_everything_except_the_mail_log(client, content):
    _client(client, ADMINS)
    rule = content["rule"].pk
    for name in (
        "disclaimrwebadmin_directoryserver_changelist",
        "disclaimrwebadmin_tenant_changelist",
        "auth_user_changelist",
        "auth_group_changelist",
    ):
        assert _status(client, name) == 200
    assert _status(client, "disclaimrwebadmin_rule_delete", rule) == 200
    # The log is superuser-only by design; the SSO sync makes Admins superusers.
    assert _status(client, "disclaimrwebadmin_maillog_changelist") == 403
