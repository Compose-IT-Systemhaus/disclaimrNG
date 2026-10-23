"""Helpers to assemble the static milter configuration from the database."""

from __future__ import annotations

import logging
from typing import Any

import netaddr
from django.db.models import Exists, OuterRef

from disclaimrwebadmin import models

syslog = logging.getLogger("disclaimr")


def build_configuration() -> dict[str, list[dict[str, Any]]]:
    """Return the milter bootstrap configuration.

    Currently this consists of the sender-IP requirements that have at least
    one enabled action in their associated rule. The milter uses this to
    short-circuit early on connections it does not care about.
    """

    configuration: dict[str, list[dict[str, Any]]] = {"sender_ip": []}

    # One query instead of one ``action_set.exists()`` round trip per
    # requirement.
    has_enabled_action = models.Action.objects.filter(
        rule_id=OuterRef("rule_id"), enabled=True
    )
    requirements = (
        models.Requirement.objects.filter(enabled=True)
        .filter(Exists(has_enabled_action))
        .only("id", "sender_ip", "sender_ip_cidr")
        .order_by("id")
    )

    for requirement in requirements:
        try:
            network = requirement.get_sender_ip_network()
        except (netaddr.AddrFormatError, ValueError):
            syslog.warning(
                "Requirement %s has an invalid sender IP %s/%s. Skipping.",
                requirement.id,
                requirement.sender_ip,
                requirement.sender_ip_cidr,
            )
            continue

        configuration["sender_ip"].append({"ip": network, "id": requirement.id})

    return configuration
