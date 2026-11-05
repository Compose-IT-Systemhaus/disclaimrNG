"""Access control for the admin's own (non-ModelAdmin) views."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied


def staff_with_perm(*codenames: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """``staff_member_required`` plus: the user needs at least one of ``codenames``.

    ``is_staff`` alone only means "may log in to the admin"; these views read
    LDAP data, use stored directory credentials or write files, so they follow
    the model permissions an admin would need for the same job.
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not any(request.user.has_perm(f"disclaimrwebadmin.{c}") for c in codenames):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return staff_member_required(wrapper)

    return decorator
