"""TLS choice and CA certificate of a directory server."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import ldap
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from disclaimr import ldap_helper
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer, DirectoryServerURL, validate_pem_certificate

# Throw-away self-signed certificate, only used to exercise the PEM handling.
PEM = """-----BEGIN CERTIFICATE-----
MIIDHzCCAgegAwIBAgIUPZgG37ggZOuuWXc0pS+CGmKc6JIwDQYJKoZIhvcNAQEL
BQAwHjEcMBoGA1UEAwwTZGlzY2xhaW1yTkcgVGVzdCBDQTAgFw0yNjExMDYxMTM1
MzBaGA8yMTI2MTAxMzExMzUzMFowHjEcMBoGA1UEAwwTZGlzY2xhaW1yTkcgVGVz
dCBDQTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAOyYjVAbdRtuUch/
hDh4mWNUK7KmFdrAJVryiy29NCT5qGvXuBm3MDst8IbYHpFwKenKQW9SWc9JYUps
jjhpD0uk5hqNC+i+2LgbYrEiQP/osjfzwek68vn9Cn6dI6jEZ+RCITlysYwJ95yv
HIdBaIuyXO7CJG+qnvqSvxyiwFC8jKmcUup6yGU3NcFuuKcfMMp1OEm7+de22jmI
adn6W2u42HnPeWPHZlg8dDIDc7A7BGxNHbE5lKDBOJJh3OtXM3b8YQXo1MdP4FGf
dE9X9Lk9v2vI8LCd8o5UFhR1cq6tz+CJrqc7XL7J8V/hElBOM+YA7ol3SoXXxH7x
K4AJDP8CAwEAAaNTMFEwHQYDVR0OBBYEFO+Hghzn/EMES3q70oYkR88u00GvMB8G
A1UdIwQYMBaAFO+Hghzn/EMES3q70oYkR88u00GvMA8GA1UdEwEB/wQFMAMBAf8w
DQYJKoZIhvcNAQELBQADggEBAJRUVKaqqVMnqvi3dypAzX0sVn4nnn3oRo5RzO2n
lKCsXqKAHoc1H7eSOxADXhcL+jbVR9jymlj3YJ7feGiyLepQDhHAYr3pye1LyZCz
d0y3l7WY0P8UEaYTDHZ+o1LkSRtb6yh8Oi/dY41xgQ2yPtnbRDC8EGKpI8bWalHa
I3nBuO9Mh8CzxO4A2CG5TB25FHX4oZVOBGzfqIbI26cWBOdvWoy9asojJpoepO9Y
MKxmdFXi6nkmhorXR4ZEPY4q+Ji29SzymKsN1mkOHJHZ7dHs6/OL5X3WjhZCbDq6
ZvtvuXSInZs65G9fVrM4SSy/cqqm+VFN040JvMark4DFPe4=
-----END CERTIFICATE-----
"""


@pytest.fixture
def admin_client(db) -> Client:
    user = get_user_model().objects.create_superuser(username="root", password="pw")
    client = Client()
    client.force_login(user)
    return client


def _post(client, *, hosts, use_tls=True, extra=None, server=None):
    data = {
        "name": "AD",
        "description": "",
        "enabled": "on",
        "flavor": constants.DIR_FLAVOR_AD,
        "base_dn": "dc=example,dc=com",
        "auth": constants.DIR_AUTH_NONE,
        "userdn": "",
        "password": "",
        "ca_certificate": "",
        "search_query": "mail=%s",
        "search_attributes": "",
        "enable_cache": "on",
        "cache_timeout": 3600,
        "hosts": hosts,
        "_save": "Save",
        **(extra or {}),
    }
    if use_tls:
        data["use_tls"] = "on"
    if server is None:
        return client.post(reverse("admin:disclaimrwebadmin_directoryserver_add"), data)
    return client.post(
        reverse("admin:disclaimrwebadmin_directoryserver_change", args=[server.pk]), data
    )


def _urls() -> list[str]:
    return list(DirectoryServerURL.objects.order_by("position").values_list("url", flat=True))


def test_pem_validator_accepts_a_certificate_and_rejects_garbage():
    validate_pem_certificate("")
    validate_pem_certificate(PEM)
    with pytest.raises(ValidationError):
        validate_pem_certificate("this is not a certificate")


def test_uploaded_ca_is_stored_on_the_server(admin_client):
    upload = SimpleUploadedFile("ca.pem", PEM.encode(), content_type="application/x-pem-file")
    response = _post(admin_client, hosts="dc1", extra={"ca_certificate_file": upload})
    assert response.status_code == 302, response.content.decode()[:500]
    server = DirectoryServer.objects.get()
    assert server.use_tls
    assert server.ca_certificate.strip() == PEM.strip()


def test_upload_that_is_no_certificate_is_rejected(admin_client):
    upload = SimpleUploadedFile("ca.pem", b"hello", content_type="text/plain")
    response = _post(admin_client, hosts="dc1", extra={"ca_certificate_file": upload})
    assert response.status_code == 200
    assert not DirectoryServer.objects.exists()


@pytest.mark.parametrize(
    ("use_tls", "hosts", "urls"),
    [
        (True, "dc1.example.com\n\n10.0.0.2:3269", ["ldaps://dc1.example.com", "ldaps://10.0.0.2:3269"]),
        (False, "dc1", ["ldap://dc1"]),
        (True, "ldap://dc1:636/", ["ldaps://dc1:636"]),  # a pasted URL: TLS decides the scheme
        (False, "[2001:db8::1]:389", ["ldap://[2001:db8::1]:389"]),
    ],
)
def test_hosts_become_urls_with_the_scheme_of_the_tls_switch(admin_client, use_tls, hosts, urls):
    response = _post(admin_client, hosts=hosts, use_tls=use_tls)
    assert response.status_code == 302, response.content.decode()[:500]
    assert DirectoryServer.objects.get().use_tls == use_tls
    assert _urls() == urls


@pytest.mark.parametrize("hosts", ["", "dc1 dc2", "dc1:port", "ldaps://dc1/dc=example"])
def test_bad_hosts_are_rejected(admin_client, hosts):
    assert _post(admin_client, hosts=hosts).status_code == 200
    assert not DirectoryServer.objects.exists()


def test_editing_shows_the_hosts_and_replaces_the_urls(admin_client):
    _post(admin_client, hosts="dc1\ndc2:3269")
    server = DirectoryServer.objects.get()
    page = admin_client.get(reverse("admin:disclaimrwebadmin_directoryserver_change", args=[server.pk]))
    assert "dc1\ndc2:3269" in page.content.decode().replace("\r\n", "\n")

    assert _post(admin_client, hosts="dc3", use_tls=False, server=server).status_code == 302
    assert _urls() == ["ldap://dc3"]


def test_connection_uses_the_servers_ca_for_ldaps_only(db):
    server = DirectoryServer(name="s", base_dn="dc=x", ca_certificate=PEM)
    conn = MagicMock()
    with patch.object(ldap, "initialize", return_value=conn) as init:
        ldap_helper.open_connection("ldaps://dc1", server)
        calls = [c.args for c in conn.set_option.call_args_list]
        assert calls[-1] == (ldap.OPT_X_TLS_NEWCTX, 0)  # must be the last TLS option
        cafile = dict(calls)[ldap.OPT_X_TLS_CACERTFILE]
        assert open(cafile).read().strip() == PEM.strip()
        assert dict(calls)[ldap.OPT_X_TLS_REQUIRE_CERT] == ldap.OPT_X_TLS_DEMAND

        conn.reset_mock()
        ldap_helper.open_connection("ldap://dc1", server)  # no TLS, no CA options
        assert all(c.args[0] != ldap.OPT_X_TLS_CACERTFILE for c in conn.set_option.call_args_list)
    assert init.call_count == 2


def test_connection_without_ca_leaves_tls_to_the_container_store(db):
    conn = MagicMock()
    with patch.object(ldap, "initialize", return_value=conn):
        ldap_helper.open_connection("ldaps://dc1", DirectoryServer(name="s", base_dn="dc=x"))
    assert all(c.args[0] != ldap.OPT_X_TLS_CACERTFILE for c in conn.set_option.call_args_list)


def test_env_sync_derives_tls_from_the_urls_and_keeps_an_uploaded_ca(db, monkeypatch):
    for key, value in {
        "LDAP_SERVERS": "corp",
        "LDAP_SERVER_CORP_BASE_DN": "dc=corp",
        "LDAP_SERVER_CORP_URL": "ldaps://dc1",
    }.items():
        monkeypatch.setenv(key, value)
    call_command("sync_directory_servers", stdout=StringIO())
    server = DirectoryServer.objects.get()
    assert server.use_tls
    server.ca_certificate = PEM
    server.save()

    monkeypatch.setenv("LDAP_SERVER_CORP_URL", "ldap://dc1")
    call_command("sync_directory_servers", stdout=StringIO())
    server.refresh_from_db()
    assert not server.use_tls
    assert server.ca_certificate == PEM
