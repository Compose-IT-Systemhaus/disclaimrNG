"""Time-limited actions and the mail statistics on the dashboard."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from disclaimrwebadmin import constants
from disclaimrwebadmin.dashboard import dashboard_callback
from disclaimrwebadmin.models import Action, Disclaimer, MailLog, Rule
from tests.test_milter_pipeline import _PLAIN_8BIT, _connected_helper, _send, _setup_rule

HOUR = timedelta(hours=1)


def _action(rule, disclaimer, name, **kwargs):
    return Action.objects.create(
        rule=rule, disclaimer=disclaimer, position=0, name=name,
        action=constants.ACTION_ACTION_ADD, **kwargs,
    )  # fmt: skip


def test_active_respects_enabled_and_the_validity_window(db):
    rule = Rule.objects.create(name="r")
    disclaimer = Disclaimer.objects.create(name="d", text="x")
    now = timezone.now()
    _action(rule, disclaimer, "open")
    _action(rule, disclaimer, "running", valid_from=now - HOUR, valid_until=now + HOUR)
    _action(rule, disclaimer, "from-only", valid_from=now - HOUR)
    _action(rule, disclaimer, "until-only", valid_until=now + HOUR)
    _action(rule, disclaimer, "future", valid_from=now + HOUR)
    _action(rule, disclaimer, "expired", valid_until=now - HOUR)
    _action(rule, disclaimer, "disabled", enabled=False)

    names = set(Action.objects.active().values_list("name", flat=True))
    assert names == {"open", "running", "from-only", "until-only"}
    # The window is judged at the given moment: tomorrow the future one runs, the others expired.
    later = set(Action.objects.active(at=now + 3 * HOUR).values_list("name", flat=True))
    assert later == {"open", "from-only", "future"}


def test_milter_applies_an_action_only_inside_its_window(db):
    _setup_rule()
    action = Action.objects.get()
    now = timezone.now()

    Action.objects.filter(pk=action.pk).update(valid_until=now - HOUR)
    expired = _connected_helper()
    _send(expired, _PLAIN_8BIT, [b"hello"])
    assert expired.applied == []

    Action.objects.filter(pk=action.pk).update(valid_from=now - HOUR, valid_until=now + HOUR)
    running = _connected_helper()
    workflow = _send(running, _PLAIN_8BIT, [b"hello"])
    assert len(running.applied) == 1
    assert "Signature" in workflow["repl_body"]


def test_valid_until_has_to_follow_valid_from(db):
    now = timezone.now()
    action = Action(valid_from=now, valid_until=now - HOUR)
    with pytest.raises(ValidationError) as exc:
        action.clean()
    assert "valid_until" in exc.value.message_dict


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw")


def _log(age: timedelta, *, processed: bool, applied: str = "") -> None:
    entry = MailLog.objects.create(sender="a@example.com", processed=processed, applied=applied)
    MailLog.objects.filter(pk=entry.pk).update(created=timezone.now() - age)


def _stats(user):
    request = RequestFactory().get("/")
    request.user = user
    return dashboard_callback(request, {})["dashboard"]["mail_stats"]


def test_mail_stats_count_the_last_seven_days(superuser):
    sig = "Rule → Add → Default"
    _log(timedelta(minutes=5), processed=True, applied=sig)
    _log(timedelta(minutes=6), processed=True, applied=sig)
    _log(timedelta(minutes=7), processed=False)
    _log(timedelta(days=1), processed=True, applied="Rule → Add → Other")
    _log(timedelta(days=30), processed=True, applied=sig)  # too old

    stats = _stats(superuser)

    assert (stats["total"], stats["signed"], stats["untouched"]) == (4, 3, 1)
    assert len(stats["days"]) == 7
    assert max(day["height"] for day in stats["days"]) == 100
    assert stats["top"][0] == {"applied": sig, "n": 2}
    assert stats["last"] is not None


def test_mail_stats_are_for_superusers_only_like_the_log(db):
    user = get_user_model().objects.create_user(username="plain", password="pw", is_staff=True)
    assert _stats(user) is None
    user.user_permissions.add(Permission.objects.get(codename="view_maillog"))
    user = get_user_model().objects.get(pk=user.pk)  # drop the cached permissions
    assert _stats(user) is None


def test_dashboard_renders_the_stats_card(superuser):
    client = Client()
    client.force_login(superuser)
    url = reverse("admin:index")

    assert "No mail seen yet." in client.get(url).content.decode()

    _log(timedelta(minutes=1), processed=True, applied="Rule → Add → Default")
    html = client.get(url).content.decode()
    assert "Mails of the last 7 days" in html
    assert "Rule → Add → Default" in html
