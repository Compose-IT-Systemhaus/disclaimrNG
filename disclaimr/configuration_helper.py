"""Helpers to assemble the static milter configuration from the database."""

from __future__ import annotations

from typing import Any

from disclaimrwebadmin import models


def build_configuration() -> dict[str, list[dict[str, Any]]]:
    """Return the milter bootstrap configuration.

    Currently this consists of the sender-IP requirements that have at least
    one enabled action in their associated rule. The milter uses this to
    short-circuit early on connections it does not care about.
    """

    configuration: dict[str, list[dict[str, Any]]] = {"sender_ip": []}

    for requirement in models.Requirement.objects.filter(enabled=True):
        if not requirement.rule.action_set.filter(enabled=True).exists():
            continue

        configuration["sender_ip"].append(
            {
                "ip": requirement.get_sender_ip_network(),
                "id": requirement.id,
            }
        )

    return configuration
