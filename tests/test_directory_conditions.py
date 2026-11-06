"""Directory conditions of a requirement: attribute regexes checked against the sender."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from disclaimr.milter_helper import MilterHelper
from disclaimrwebadmin import constants, models
from tests.test_milter_pipeline import _PLAIN_8BIT, _connected_helper, _send, _setup_rule


@pytest.fixture
def directory(db, monkeypatch):
    """A tenant for example.com with one directory server; ``searches`` lists the queries."""
    tenant = models.Tenant.objects.create(name="Acme", slug="acme")
    models.TenantDomain.objects.create(tenant=tenant, domain="example.com")
    server = models.DirectoryServer.objects.create(
        name="LDAP",
        tenant=tenant,
        base_dn="dc=example,dc=com",
        auth=constants.DIR_AUTH_NONE,
        enable_cache=False,
    )
    models.DirectoryServerURL.objects.create(directory_server=server, url="ldaps://dc", position=0)

    state = {"entry": {"department": [b"Sales"], "title": [b"Head of Sales", b"Mentor"]}}
    searches: list[tuple[str, list[str]]] = []

    def fake_search(directory_server, url, query, attrlist):
        searches.append((query, attrlist))
        entry = state["entry"]
        return None if entry is None else [("CN=Alice", entry)]

    monkeypatch.setattr(MilterHelper, "_search_url", staticmethod(fake_search))
    return type("Directory", (), {"state": state, "searches": searches})


def _requirement(*conditions: tuple[str, str], action=constants.REQ_ACTION_ACCEPT):
    if action == constants.REQ_ACTION_ACCEPT:
        requirement = models.Requirement.objects.get(rule__name="r")
    else:
        requirement = models.Requirement.objects.create(
            rule=models.Rule.objects.get(name="r"), name="deny", action=action
        )
    for attribute, pattern in conditions:
        requirement.conditions.create(attribute=attribute, pattern=pattern)
    return requirement


def _signed(**kwargs) -> bool:
    workflow = _send(_connected_helper(), _PLAIN_8BIT, [b"hello"], **kwargs)
    return workflow is not None and "Signature" in workflow["repl_body"]


def test_matching_condition_applies_the_rule(directory):
    _setup_rule()
    _requirement(("department", "^Sales$"))
    assert _signed()
    assert directory.searches[0][1] == ["department"]


def test_failing_condition_skips_the_rule(directory):
    _setup_rule()
    _requirement(("department", "^Support$"))
    assert not _signed()


def test_all_conditions_have_to_hold(directory):
    _setup_rule()
    _requirement(("department", "Sales"), ("title", "Director"))
    assert not _signed()
    assert directory.searches[0][1] == ["department", "title"]  # one lookup for both


def test_multi_valued_attributes_are_checked_value_by_value(directory):
    _setup_rule()
    _requirement(("Title", "^Mentor$"))
    assert _signed()


def test_unreachable_directory_means_the_condition_does_not_hold(directory, caplog):
    directory.state["entry"] = None
    _setup_rule()
    _requirement(("department", ".*"))
    assert not _signed()
    assert "do not hold" in caplog.text


def test_unknown_sender_domain_does_not_query_anything(directory):
    _setup_rule()
    _requirement(("department", ".*"))
    assert not _signed(sender="alice@other.example")
    assert directory.searches == []


def test_no_conditions_no_lookup(directory):
    _setup_rule()
    assert _signed()
    assert directory.searches == []


def test_deny_requirement_with_condition(directory):
    _setup_rule()
    _requirement(("department", "^Sales$"), action=constants.REQ_ACTION_DENY)
    assert not _signed()

    models.RequirementCondition.objects.update(pattern="^Support$")
    assert _signed()


def test_condition_is_validated():
    for attribute, pattern in (("not valid", "x"), ("department", "(")):
        condition = models.RequirementCondition(attribute=attribute, pattern=pattern)
        with pytest.raises(ValidationError) as caught:
            condition.full_clean(exclude=["requirement"])
        assert caught.value.message_dict


def test_requirement_page_with_conditions_opens(db, client):
    _setup_rule()
    requirement = _requirement(("department", "Sales"))
    client.force_login(
        get_user_model().objects.create_superuser("root", "root@example.com", "pw")
    )
    page = client.get(reverse("admin:disclaimrwebadmin_requirement_change", args=[requirement.pk]))
    assert page.status_code == 200
    assert b"department" in page.content
