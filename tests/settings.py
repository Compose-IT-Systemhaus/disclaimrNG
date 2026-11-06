"""Settings of the test suite: the project's own, with the environment defaults and SSO on.

The settings are imported before any ``conftest.py`` runs, so the defaults the suite needs
have to be set here (CI exports the same values; ``setdefault`` leaves them alone).
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "ci-only-not-for-production")
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "*")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
# The SSO routes only exist when these are set.
os.environ.setdefault("OIDC_SERVER_URL", "https://idp.example.com/application/o/disclaimr/")
os.environ.setdefault("OIDC_CLIENT_ID", "disclaimr")
os.environ.setdefault("OIDC_CLIENT_SECRET", "secret")
os.environ.setdefault("OIDC_NAME", "Authentik")

from disclaimrweb.settings import *  # noqa: E402, F403
