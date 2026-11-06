"""The three built-in roles (groups): Admins, Editor, Reader.

They are plain Django groups with model permissions, so everything that already asks for
permissions (admin, sidebar, our own views) follows them. :func:`ensure_default_groups`
creates them after every ``migrate``; permissions are only written when a group is created
(or with ``reset``), so changes made in the admin stay.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission

ADMINS = "Admins"
EDITOR = "Editor"
READER = "Reader"

# Signatures and rules, with everything a rule or signature form contains.
_CONTENT_MODELS = (
    "disclaimer",
    "rule",
    "requirement",
    "requirementcondition",
    "action",
    "signatureimage",
)


def _codenames(prefixes: tuple[str, ...], models: tuple[str, ...]) -> list[str]:
    return [f"{prefix}_{model}" for prefix in prefixes for model in models]


def role_permissions(role: str) -> list[Permission]:
    """The permissions a role starts with."""
    if role == ADMINS:
        return list(
            Permission.objects.filter(
                content_type__app_label__in=("disclaimrwebadmin", "auth")
            )
        )
    prefixes = ("view",) if role == READER else ("view", "add", "change")
    codenames = _codenames(prefixes, _CONTENT_MODELS)
    if role == EDITOR:
        codenames.append("view_tenant")  # the tenant autocomplete of the rule/signature forms
    return list(
        Permission.objects.filter(content_type__app_label="disclaimrwebadmin", codename__in=codenames)
    )


def ensure_default_groups(*, reset: bool = False) -> list[str]:
    """Create the roles that are missing (all permissions again with ``reset``).

    Returns the names of the groups that were (re)filled.
    """
    filled = []
    for role in (ADMINS, EDITOR, READER):
        group, created = Group.objects.get_or_create(name=role)
        if created or reset:
            group.permissions.set(role_permissions(role))
            filled.append(role)
    return filled
