"""Tests for the DirectoryServer admin endpoints and model conveniences."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from disclaimr.ldap_helper import AttributeDiscoveryResult, TestResult, URLProbe
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer, DirectoryServerURL

# The change form as the browser sends it to the test button's endpoint.
_FORM = {
    "name": "Form AD",
    "description": "",
    "enabled": "on",
    "flavor": constants.DIR_FLAVOR_AD,
    "hosts": "dc9.example.com:3269\n10.0.0.9",
    "use_tls": "on",
    "base_dn": "dc=example,dc=com",
    "auth": constants.DIR_AUTH_SIMPLE,
    "userdn": "cn=new,dc=example,dc=com",
    "password": "secret",
    "ca_certificate": "",
    "search_query": "mail=%s",
    "search_attributes": "",
    "enable_cache": "on",
    "cache_timeout": 3600,
}

@pytest.fixture
def staff_client(db) -> Client:
    user = get_user_model().objects.create_superuser(username="bob", password="pw")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def directory_server(db) -> DirectoryServer:
    server = DirectoryServer.objects.create(
        name="Test AD",
        flavor=constants.DIR_FLAVOR_AD,
        base_dn="dc=example,dc=com",
        auth=constants.DIR_AUTH_NONE,
    )
    DirectoryServerURL.objects.create(
        directory_server=server, url="ldap://ldap.example.com", position=0
    )
    return server


def test_attribute_vocabulary_falls_back_to_flavor_default(directory_server):
    vocab = directory_server.get_attribute_vocabulary()
    assert "userPrincipalName" in vocab  # AD-only default
    assert "mail" in vocab


def test_attribute_vocabulary_uses_custom_when_set(directory_server):
    directory_server.search_attributes = "givenName, sn\nmail"
    directory_server.save()
    vocab = directory_server.get_attribute_vocabulary()
    assert vocab == ["givenName", "sn", "mail"]


def test_test_endpoint_returns_probe_results(staff_client, directory_server):
    fake = TestResult(
        ok=True,
        probes=[URLProbe(url="ldap://ldap.example.com", ok=True, detail="bind ok")],
        summary="1/1 URL(s) reachable.",
    )
    url = reverse("disclaimrwebadmin:directoryserver-test")
    with patch(
        "disclaimrwebadmin.views.directory_server.test_connection", return_value=fake
    ) as tested:
        response = staff_client.post(url, {**_FORM, "_object_id": directory_server.pk})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["probes"][0]["url"] == "ldap://ldap.example.com"
    assert payload["summary"].startswith("1/1")
    # The values of the form are tested, not the saved ones, and nothing is saved.
    server, urls = tested.call_args.args
    assert urls == ["ldaps://dc9.example.com:3269", "ldaps://10.0.0.9"]
    assert server.pk == directory_server.pk and server.userdn == "cn=new,dc=example,dc=com"
    directory_server.refresh_from_db()
    assert directory_server.userdn != "cn=new,dc=example,dc=com"
    assert not directory_server.directoryserverurl_set.filter(url__contains="dc9").exists()


def test_test_endpoint_works_for_a_server_that_is_not_saved_yet(staff_client):
    with patch(
        "disclaimrwebadmin.views.directory_server.test_connection",
        return_value=TestResult(ok=False, summary="0/1 URL(s) reachable."),
    ) as tested:
        response = staff_client.post(reverse("disclaimrwebadmin:directoryserver-test"), _FORM)
    assert response.json()["ok"] is False
    assert tested.call_args.args[0].pk is None
    assert not DirectoryServer.objects.filter(name="Form AD").exists()


def test_test_endpoint_reports_form_errors(staff_client):
    with patch("disclaimrwebadmin.views.directory_server.test_connection") as tested:
        response = staff_client.post(
            reverse("disclaimrwebadmin:directoryserver-test"), {**_FORM, "hosts": "not a host"}
        )
    payload = response.json()
    assert payload["ok"] is False and "Hosts" in payload["summary"]
    assert not tested.called


def test_list_has_an_edit_link(staff_client, directory_server):
    page = staff_client.get(reverse("admin:disclaimrwebadmin_directoryserver_changelist"))
    change = reverse("admin:disclaimrwebadmin_directoryserver_change", args=[directory_server.pk])
    assert page.content.decode().count(f'href="{change}"') >= 2  # the name and the pencil


def test_attributes_endpoint_returns_discovered_attrs(staff_client, directory_server):
    fake = AttributeDiscoveryResult(
        ok=True,
        attributes=["cn", "mail", "telephoneNumber"],
        sample_dn="cn=alice,dc=example,dc=com",
    )
    url = reverse(
        "disclaimrwebadmin:directoryserver-attributes", args=[directory_server.pk]
    )
    with patch(
        "disclaimrwebadmin.views.directory_server.discover_attributes",
        return_value=fake,
    ):
        response = staff_client.post(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "cn" in payload["attributes"]
    assert payload["sample_dn"].startswith("cn=alice")


def test_vocabulary_endpoint_unions_per_server(staff_client, directory_server):
    DirectoryServer.objects.create(
        name="Plain LDAP",
        flavor=constants.DIR_FLAVOR_LDAP,
        base_dn="dc=other,dc=tld",
        search_attributes="ou, l",
    )
    url = reverse("disclaimrwebadmin:directoryserver-vocabulary")
    response = staff_client.get(url)
    assert response.status_code == 200
    payload = response.json()
    assert "userPrincipalName" in payload["attributes"]  # from AD default
    assert "ou" in payload["attributes"]                  # from custom override
    assert {srv["name"] for srv in payload["servers"]} == {"Test AD", "Plain LDAP"}


def test_disabled_servers_are_excluded_from_vocabulary(staff_client, directory_server):
    directory_server.enabled = False
    directory_server.save()
    url = reverse("disclaimrwebadmin:directoryserver-vocabulary")
    response = staff_client.get(url)
    payload = response.json()
    assert payload["servers"] == []
    assert payload["attributes"] == []


def test_test_endpoint_requires_staff(client, directory_server):
    url = reverse("disclaimrwebadmin:directoryserver-test")
    response = client.post(url, _FORM)
    assert response.status_code in (302, 403)
