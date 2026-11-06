"""Single sign-on over OpenID Connect (django-allauth): first login and group sync.

A user who signs in through the identity provider is created on the spot (no sign-up form,
no automatic link to an existing local account), and at every login the groups the provider
reports are mapped onto local groups (:class:`~disclaimrwebadmin.models.SSOGroupMapping`).
Local accounts that never used SSO are not touched.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import SSOGroupMapping
from .roles import ADMINS, READER, ensure_default_groups

logger = logging.getLogger("disclaimr")

PROVIDER_ID = "sso"


def claim_groups(extra_data: dict[str, Any]) -> set[str]:
    """The group names the provider reported (ID token and userinfo are merged)."""
    claims = {**(extra_data.get("id_token") or {}), **(extra_data.get("userinfo") or {})}
    value = (claims or extra_data).get(settings.OIDC_GROUPS_CLAIM) or []
    return {value} if isinstance(value, str) else {str(group) for group in value}


def sync_user(user, sso_groups: Iterable[str]) -> None:
    """Give ``user`` the local groups mapped from ``sso_groups`` (default: Reader).

    Only groups that appear in a mapping, and Reader, are managed here; other groups
    assigned by hand stay. Admins are superusers, everybody else is not; SSO users are
    always staff.
    """
    ensure_default_groups()  # an administrator may have deleted a role
    sso_groups = set(sso_groups)
    reader = Group.objects.get(name=READER)
    mappings = list(SSOGroupMapping.objects.all())
    managed = {m.group_id for m in mappings} | {reader.pk}
    wanted = {m.group_id for m in mappings if m.sso_group in sso_groups} or {reader.pk}
    current = set(user.groups.values_list("pk", flat=True))
    user.groups.add(*(wanted - current))
    user.groups.remove(*((managed - wanted) & current))
    user.is_staff = True
    user.is_superuser = user.groups.filter(name=ADMINS).exists()
    user.save(update_fields=["is_staff", "is_superuser"])


def _back_to_login(request, message: str):
    messages.error(request, message)
    return ImmediateHttpResponse(HttpResponseRedirect(reverse("admin:login")))


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin) -> None:
        user = sociallogin.user
        if sociallogin.is_existing:
            if not user.is_active:
                raise _back_to_login(request, _("This account is disabled."))
        else:
            # Create the account here instead of through allauth's sign-up flow, which would
            # ask for a form (or link by e-mail) in cases we do not want.
            user.is_staff = True
            user.set_unusable_password()
            # The suggested name may be taken (by "admin", say): never reuse a local account.
            user.username = get_account_adapter(request).generate_unique_username(
                [user.username, user.email.partition("@")[0], sociallogin.account.uid]
            )
            sociallogin.save(request, connect=True)
            logger.info("Created the user %s from the first SSO login.", user.username)
        sync_user(user, claim_groups(sociallogin.account.extra_data))

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ) -> None:
        logger.warning("SSO login failed: %s %s", error, exception or "")
        raise _back_to_login(
            request, _("Sign-in with %(name)s failed.") % {"name": provider.name}
        )


def sso_context(request) -> dict[str, Any]:
    """Template context for the login page: the SSO button, if SSO is configured."""
    if not settings.OIDC_ENABLED:
        return {}
    return {
        "sso_login": {
            "name": settings.OIDC_NAME,
            "url": reverse("openid_connect_login", kwargs={"provider_id": PROVIDER_ID}),
        }
    }
