"""Pytest configuration shared across the disclaimrNG test suite.

Sets up minimal env vars expected by ``disclaimrweb.settings`` so the suite
can run without a populated ``.env`` (CI, fresh checkouts).
"""

from __future__ import annotations

import os

# These need to be in place before Django settings get imported. pytest-django
# loads settings on first DB access, so setting them at module import time is
# enough.
os.environ.setdefault("DJANGO_SECRET_KEY", "ci-only-not-for-production")
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "*")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
