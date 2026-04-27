"""Tests for the ``bootstrap_admin`` management command."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command


def _run(*args: str) -> str:
    out = StringIO()
    call_command("bootstrap_admin", *args, stdout=out)
    return out.getvalue()


def test_creates_admin_when_none_exists(db):
    output = _run()
    user = get_user_model().objects.get(username="admin")
    assert user.is_superuser
    assert user.is_staff
    assert "one-time password" in output


def test_password_appears_in_log_output(db):
    output = _run()
    # Banner format: '[bootstrap_admin] one-time password: <pw>'
    line = next(l for l in output.splitlines() if "one-time password" in l)
    password = line.split("one-time password:")[1].strip()
    assert len(password) >= 16
    user = get_user_model().objects.get(username="admin")
    assert user.check_password(password)


def test_skips_when_superuser_exists(db):
    User = get_user_model()
    User.objects.create_superuser(username="root", password="existing", email="")
    output = _run()
    assert "skipping" in output.lower()
    assert not User.objects.filter(username="admin").exists()


def test_reset_flag_recreates_password(db):
    _run()
    user = get_user_model().objects.get(username="admin")
    first_pw_hash = user.password

    output = _run("--reset")
    user.refresh_from_db()
    assert user.password != first_pw_hash
    assert "one-time password" in output


def test_reset_creates_admin_even_when_other_superuser_exists(db):
    User = get_user_model()
    User.objects.create_superuser(username="root", password="existing", email="")
    _run("--reset")
    assert User.objects.filter(username="admin", is_superuser=True).exists()
