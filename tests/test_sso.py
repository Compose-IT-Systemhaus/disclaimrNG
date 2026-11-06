"""Single sign-on: first login, group sync, the login page and the routes that stay closed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from allauth.account.middleware import AccountMiddleware
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from disclaimrwebadmin.models import SSOGroupMapping
from disclaimrwebadmin.roles import ADMINS, EDITOR, READER
from disclaimrwebadmin.sso import SocialAccountAdapter, claim_groups, sync_user

User = get_user_model()


def _request():
    request = RequestFactory().get("/accounts/oidc/sso/login/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    return request


def _login(uid="u1", *, username="alice", email="alice@example.com", groups=(), **extra) -> SocialLogin:
    """What allauth hands to the adapter after the provider answered."""
    claims = {"preferred_username": username, "email": email, "groups": list(groups), **extra}
    login = SocialLogin(
        user=User(username=username, email=email, first_name="Alice"),
        account=SocialAccount(provider="sso", uid=uid, extra_data={"id_token": claims}),
    )
    login.state = {"process": "login"}
    return login


def _hook(login: SocialLogin, request=None) -> User:
    login.lookup()  # allauth does this right before the hook
    SocialAccountAdapter().pre_social_login(request or _request(), login)
    return login.user


def _names(user) -> set[str]:
    return set(user.groups.values_list("name", flat=True))


@pytest.fixture
def mappings(db):
    for sso, role in (("sig-admins", ADMINS), ("sig-editors", EDITOR)):
        SSOGroupMapping.objects.create(sso_group=sso, group=Group.objects.get(name=role))


def test_first_login_creates_the_user(mappings):
    user = _hook(_login(groups=["sig-editors", "unrelated"]))

    assert User.objects.filter(username="alice", is_staff=True).exists()
    assert not user.has_usable_password()
    assert not user.is_superuser
    assert _names(user) == {EDITOR}
    assert SocialAccount.objects.filter(provider="sso", uid="u1", user=user).exists()


def test_without_a_mapped_group_the_user_is_a_reader(mappings):
    assert _names(_hook(_login(groups=["something-else"]))) == {READER}
    assert _names(_hook(_login(uid="u2", username="bob", email="b@example.com"))) == {READER}


def test_admins_are_superusers_and_lose_it_with_the_group(mappings):
    user = _hook(_login(groups=["sig-admins"]))
    assert user.is_superuser and user.is_staff and _names(user) == {ADMINS}

    again = _hook(_login(groups=["sig-editors"]))  # same uid: the same user
    again.refresh_from_db()
    assert again.pk == user.pk
    assert _names(again) == {EDITOR}
    assert not again.is_superuser and again.is_staff


def test_groups_assigned_by_hand_stay(mappings):
    user = _hook(_login(groups=["sig-editors"]))
    extra = Group.objects.create(name="Extra")
    user.groups.add(extra)

    _hook(_login(groups=[]))

    assert _names(User.objects.get(pk=user.pk)) == {READER, "Extra"}


def test_a_local_account_is_never_taken_over(mappings):
    local = User.objects.create_user("alice", "alice@example.com", "pw")

    user = _hook(_login(groups=["sig-admins"]))

    assert user.pk != local.pk and user.username != "alice"
    local.refresh_from_db()
    assert local.check_password("pw") and not local.is_superuser and not local.is_staff


def test_disabled_account_is_sent_back_to_the_login(mappings):
    user = _hook(_login(groups=["sig-editors"]))
    User.objects.filter(pk=user.pk).update(is_active=False)

    with pytest.raises(ImmediateHttpResponse) as caught:
        _hook(_login(groups=["sig-admins"]))

    assert caught.value.response.url == reverse("admin:login")
    assert not User.objects.get(pk=user.pk).is_superuser  # not synced


def test_authentication_error_goes_back_to_the_login(db):
    request = _request()
    with pytest.raises(ImmediateHttpResponse) as caught:
        SocialAccountAdapter().on_authentication_error(
            request, SimpleNamespace(name="Authentik"), error="denied"
        )
    assert caught.value.response.url == reverse("admin:login")
    assert "Authentik" in str([m.message for m in request._messages])


def test_claims_come_from_id_token_and_userinfo(settings):
    assert claim_groups({"id_token": {"groups": ["a"]}, "userinfo": {"email": "x"}}) == {"a"}
    assert claim_groups({"userinfo": {"groups": ["b"]}, "id_token": {"groups": ["a"]}}) == {"b"}
    assert claim_groups({"groups": "single"}) == {"single"}  # flat, one value
    assert claim_groups({"id_token": {}}) == set()
    settings.OIDC_GROUPS_CLAIM = "roles"
    assert claim_groups({"id_token": {"roles": ["r"], "groups": ["a"]}}) == {"r"}


def test_sync_user_does_not_need_the_mappings(db):
    user = User.objects.create_user("carol")
    sync_user(user, ["whatever"])
    assert _names(user) == {READER} and user.is_staff


def test_complete_login_signs_the_user_in(mappings):
    request = _request()
    login = _login(groups=["sig-editors"])
    response = AccountMiddleware(lambda r: complete_social_login(r, login))(request)

    assert response.status_code == 302
    assert request.user.is_authenticated and request.user.username == "alice"
    assert request.user.is_staff


# --- the login page and the routes ------------------------------------------------------


def test_login_page_offers_sso(client):
    page = client.get(reverse("admin:login"), {"next": "/disclaimr/x?a=1"})
    html = page.content.decode()
    assert "Sign in with Authentik" in html
    assert "/accounts/oidc/sso/login/?next=%2Fdisclaimr%2Fx%3Fa%3D1" in html


def test_login_page_without_sso_has_no_button(client, settings):
    settings.OIDC_ENABLED = False
    assert "Sign in with" not in client.get(reverse("admin:login")).content.decode()


def test_password_login_still_works(client, db):
    User.objects.create_superuser("root", "r@example.com", "pw")
    answer = client.post(reverse("admin:login"), {"username": "root", "password": "pw", "next": "/"})
    assert answer.status_code == 302


@pytest.mark.parametrize(
    "path",
    ["/accounts/login/", "/accounts/signup/", "/accounts/password/reset/", "/accounts/3rdparty/signup/"],
)
def test_allauths_account_pages_are_not_routed(client, path, db):
    client.force_login(User.objects.create_superuser("root", "r@example.com", "pw"))
    assert client.get(path).status_code == 404  # the admin's catch-all, not allauth


def test_the_provider_urls_are_routed():
    assert reverse("openid_connect_login", kwargs={"provider_id": "sso"}) == "/accounts/oidc/sso/login/"
    assert (
        reverse("openid_connect_callback", kwargs={"provider_id": "sso"})
        == "/accounts/oidc/sso/login/callback/"
    )
