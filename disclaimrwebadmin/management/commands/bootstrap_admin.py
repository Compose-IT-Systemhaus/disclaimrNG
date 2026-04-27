"""Create an initial ``admin`` superuser on first boot.

Idempotent: if any superuser already exists this is a no-op so restarts
don't reset the password. The generated password is printed inside a
visually distinct block so it's easy to grep out of ``docker logs`` —
operators are expected to copy it once and rotate from the admin UI.

Pass ``--reset`` to forcibly recreate the ``admin`` account (handy when
someone forgot to copy the password on first boot).
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

ADMIN_USERNAME = "admin"
PASSWORD_BYTES = 18  # ~24 url-safe chars


def _generate_password() -> str:
    return secrets.token_urlsafe(PASSWORD_BYTES)


class Command(BaseCommand):
    help = "Create the initial 'admin' superuser if no superuser exists yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Recreate the admin user even if one exists, generating a "
                "fresh password."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()
        reset = options["reset"]

        if not reset and User.objects.filter(is_superuser=True).exists():
            self.stdout.write("[bootstrap_admin] superuser exists — skipping.")
            return

        password = _generate_password()
        user, created = User.objects.update_or_create(
            username=ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        user.set_password(password)
        user.save(update_fields=["password"])

        verb = "created" if created else "reset"
        self._announce(verb, password)

    def _announce(self, verb: str, password: str) -> None:
        banner = "=" * 72
        self.stdout.write(banner)
        self.stdout.write(f"[bootstrap_admin] superuser '{ADMIN_USERNAME}' {verb}.")
        self.stdout.write(f"[bootstrap_admin] one-time password: {password}")
        self.stdout.write(
            "[bootstrap_admin] log in and change it at /admin/password_change/"
        )
        self.stdout.write(banner)
