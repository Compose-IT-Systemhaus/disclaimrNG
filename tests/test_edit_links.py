"""Every list in the admin has a pencil column that opens the object."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from disclaimrwebadmin import models


def _objects():
    tenant = models.Tenant.objects.create(name="Acme", slug="acme")
    return {
        "disclaimrwebadmin_tenant": tenant,
        "disclaimrwebadmin_rule": models.Rule.objects.create(name="r"),
        "disclaimrwebadmin_disclaimer": models.Disclaimer.objects.create(name="d"),
        "disclaimrwebadmin_directoryserver": models.DirectoryServer.objects.create(
            name="AD", base_dn="dc=x"
        ),
        "disclaimrwebadmin_ssogroupmapping": models.SSOGroupMapping.objects.create(
            sso_group="g", group=Group.objects.get(name="Reader")
        ),
        "auth_group": Group.objects.get(name="Reader"),
    }


@pytest.mark.parametrize(
    "admin_name",
    [
        "disclaimrwebadmin_tenant",
        "disclaimrwebadmin_rule",
        "disclaimrwebadmin_disclaimer",
        "disclaimrwebadmin_directoryserver",
        "disclaimrwebadmin_ssogroupmapping",
        "auth_group",
        "auth_user",
    ],
)
def test_list_has_an_edit_link(client, db, admin_name):
    root = get_user_model().objects.create_superuser("root", "r@example.com", "pw")
    client.force_login(root)
    obj = _objects().get(admin_name, root)

    page = client.get(reverse(f"admin:{admin_name}_changelist"))

    change = reverse(f"admin:{admin_name}_change", args=[obj.pk])
    html = page.content.decode()
    assert page.status_code == 200
    assert f'href="{change}" title="Edit"' in html
