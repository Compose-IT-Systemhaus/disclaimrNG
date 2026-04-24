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
        if queue_id:
            queue_id = f"{queue_id}: "
        self.queue = queue_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.queueid = self.queue
        return True


syslog = logging.getLogger("disclaimr")
syslog.propagate = False
syslog.addFilter(queueFilter())

formatter = logging.Formatter("%(name)s[%(process)d]: %(queueid)s%(message)s")

if os.path.exists("/dev/log"):
    handler: logging.Handler = SysLogHandler(
        address="/dev/log", facility=SysLogHandler.LOG_MAIL
    )
else:
    handler = logging.StreamHandler()

handler.setFormatter(formatter)
syslog.addHandler(handler)
