"""Logging helpers for the disclaimr milter.

Logs to syslog (LOG_MAIL facility) when ``/dev/log`` is available, otherwise
falls back to stderr. The :class:`queueFilter` annotates each record with the
current MTA queue id so messages can be correlated across the milter pipeline.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import SysLogHandler


class queueFilter(logging.Filter):
    """Append the MTA queue id to each log record."""

    def __init__(self, queue_id: str = "") -> None:
        super().__init__()
        self.queue = ""
        self.set_queue_id(queue_id)

    def set_queue_id(self, queue_id: str) -> None:
        self.queue = f"{queue_id}: " if queue_id else ""

    def filter(self, record: logging.LogRecord) -> bool:
        record.queueid = self.queue
        return True


syslog = logging.getLogger("disclaimr")
syslog.propagate = False

# One filter for the lifetime of the process; the milter only swaps the
# queue id when a new mail starts (instead of stacking a new filter onto the
# logger for every header line).
_queue_filter = queueFilter()
syslog.addFilter(_queue_filter)


def set_queue_id(queue_id: str) -> None:
    """Tag all following ``disclaimr`` log records with ``queue_id``."""
    _queue_filter.set_queue_id(queue_id)


formatter = logging.Formatter("%(name)s[%(process)d]: %(queueid)s%(message)s")

if os.path.exists("/dev/log"):
    handler: logging.Handler = SysLogHandler(
        address="/dev/log", facility=SysLogHandler.LOG_MAIL
    )
else:
    handler = logging.StreamHandler()

handler.setFormatter(formatter)
syslog.addHandler(handler)
