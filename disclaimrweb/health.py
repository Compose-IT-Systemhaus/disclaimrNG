"""Liveness endpoint for the container healthcheck (``/healthz``)."""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    """200 when the web app can reach its database, 503 otherwise."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 — any DB failure means "not healthy"
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})
