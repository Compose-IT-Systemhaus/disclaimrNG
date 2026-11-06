"""Create the built-in roles Admins, Editor and Reader (also done after every migrate).

``--reset`` gives the three groups their default permissions back, discarding changes made
in the admin.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from disclaimrwebadmin.roles import ensure_default_groups


class Command(BaseCommand):
    help = "Create the roles Admins, Editor and Reader; --reset restores their permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Restore the default permissions of the three roles.",
        )

    def handle(self, *args, **options):
        filled = ensure_default_groups(reset=options["reset"])
        self.stdout.write(
            f"[sync_roles] permissions set for: {', '.join(filled)}"
            if filled
            else "[sync_roles] roles exist — nothing to do (use --reset to restore)."
        )
