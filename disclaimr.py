"""disclaimrNG — milter daemon entry point."""

from __future__ import annotations

__version__ = "v2.0.0.dev0"

import argparse
import logging
import os
import signal
import sys
import traceback

import django
import ldap
import libmilter as lm

from disclaimr.query_cache import QueryCache  # noqa: F401  -- re-exported

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "disclaimrweb.settings")
django.setup()

from django.db import connection  # noqa: E402  -- after django.setup()

from disclaimr.configuration_helper import build_configuration  # noqa: E402
from disclaimr.logging_helper import queueFilter  # noqa: E402
from disclaimr.milter_helper import MilterHelper  # noqa: E402

syslog = logging.getLogger("disclaimr")

try:
    import systemd.daemon

    HAS_SYSTEMD_PYTHON = True
except ImportError:
    syslog.warning(
        "Missing module systemd.daemon, systemd support not available! "
        "Consider installing systemd-python"
    )
    HAS_SYSTEMD_PYTHON = False


configuration: dict = {}
options: argparse.Namespace


class DisclaimrMilter(lm.ForkMixin, lm.MilterProtocol):
    """Per-connection milter instance.

    Delegates the actual heavy lifting to :class:`MilterHelper` and short-circuits
    callbacks once the helper has decided no rule applies.
    """

    def __init__(self, opts: int = 0, protos: int = 0) -> None:
        lm.MilterProtocol.__init__(self, opts, protos)
        lm.ForkMixin.__init__(self)

        self.helper = MilterHelper(configuration)
        logging.debug("Initialising Milter Fork")

        # Recycle stale Django DB connections (each fork inherits one).
        if connection.connection and not connection.is_usable():
            logging.debug("Found dead database connection, closing it now...")
            connection.close()

    @lm.noReply
    def connect(self, hostname, family, ip, port, cmd_dict):
        logging.debug("CONNECT: %s, %s, %s, %s", hostname, family, ip, port)
        self.helper.connect(hostname, family, ip, port, cmd_dict)
        return lm.CONTINUE

    @lm.noReply
    def helo(self, heloname):
        if not self.helper.enabled:
            logging.debug("Ignoring HELO since CONNECT didn't match...")
            return lm.CONTINUE
        logging.debug("HELO: %s", heloname)
        return lm.CONTINUE

    @lm.noReply
    def mailFrom(self, addr, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring MAIL-FROM since a previous rule didn't match...")
            return lm.CONTINUE
        logging.debug("MAILFROM: %s", addr)
        self.helper.mail_from(addr, cmd_dict)
        return lm.CONTINUE

    @lm.noReply
    def rcpt(self, recip, cmd_dict):
        if self.helper.rcptmatch:
            logging.debug(
                "We already have a positive recipient match, skipping further RCPT checks."
            )
            return lm.CONTINUE
        logging.debug("RCPT: %s", recip)
        self.helper.rcpt(recip, cmd_dict)
        return lm.CONTINUE

    @lm.noReply
    def header(self, key, val, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring HEADER since a previous rule didn't match...")
            return lm.CONTINUE
        logging.debug("HEADER: %s: %s", key, val)
        syslog.addFilter(queueFilter(cmd_dict["i"]))
        self.helper.header(key, val, cmd_dict)
        return lm.CONTINUE

    @lm.noReply
    def eoh(self, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring END-OF-HEADER since a previous rule didn't match...")
            return lm.CONTINUE
        self.helper.eoh(cmd_dict)
        return lm.CONTINUE

    @lm.noReply
    def body(self, chunk, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring BODY since a previous rule didn't match...")
            return lm.CONTINUE
        logging.debug("BODY: (chunk) %s", chunk)
        self.helper.body(chunk, cmd_dict)
        return lm.CONTINUE

    def eob(self, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring END-OF-BODY since a previous rule didn't match...")
            return lm.CONTINUE

        logging.debug("ENDOFBODY: Processing actions...")
        tasks = self.helper.eob(cmd_dict) or {}

        if "repl_body" in tasks:
            self.replBody(tasks["repl_body"])

        for header, value in tasks.get("add_header", {}).items():
            self.addHeader(header, value)

        for header, value in tasks.get("change_header", {}).items():
            self.chgHeader(header, value)

        for header in tasks.get("delete_header", []):
            self.chgHeader(header, "")

        return lm.CONTINUE

    def close(self):
        logging.debug("Close called. QID: %s", self._qid)
        if self._qid:
            syslog.error(
                "Message could not be processed! Traceback follows... If you found a "
                "bug, please report it at "
                "https://github.com/Compose-IT-Systemhaus/disclaimrNG"
            )
            traceback.print_exc()


def run_disclaimr_milter() -> None:
    """Start the multi-forking milter daemon."""

    opts = lm.SMFIF_CHGBODY | lm.SMFIF_ADDHDRS | lm.SMFIF_CHGHDRS
    factory = lm.ForkFactory(options.socket, DisclaimrMilter, opts)

    def signal_handler(num, frame):
        logging.debug("Received signal %s", num)
        syslog.info("Stopping disclaimr %s listening on %s", __version__, options.socket)
        factory.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    syslog.info("Starting disclaimr %s listening on %s", __version__, options.socket)

    try:
        logging.debug("HAS_SYSTEMD_PYTHON: %s", HAS_SYSTEMD_PYTHON)
        if HAS_SYSTEMD_PYTHON and systemd.daemon.booted():
            logging.debug("Reporting to systemd that we are ready...")
            systemd.daemon.notify("READY=1")

        factory.run()

    except Exception as exc:
        factory.close()
        print(f"EXCEPTION OCCURED: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(3)


def main() -> None:
    global options, configuration

    parser = argparse.ArgumentParser(
        description=(
            "disclaimrNG — mail signature server. Starts a milter daemon that adds "
            "dynamic disclaimers to outgoing messages."
        )
    )
    parser.add_argument(
        "-s",
        "--socket",
        dest="socket",
        default=os.environ.get("MILTER_SOCKET", "inet:127.0.0.1:5000"),
        help=(
            "Socket to open. IP-Sockets need to be in the form inet:<ip>:<port> "
            "[inet:127.0.0.1:5000]. Can also be set via MILTER_SOCKET env var."
        ),
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Be quiet doing things",
    )
    parser.add_argument(
        "-d",
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "-i",
        "--ignore-cert",
        dest="ignore_cert",
        action="store_true",
        help="Ignore certificates when connecting to TLS-enabled directory servers",
    )

    options = parser.parse_args()

    if options.quiet and options.debug:
        parser.error("Cannot specify --debug and --quiet at the same time.")

    if options.quiet:
        logging.basicConfig(level=logging.ERROR)
    elif options.debug:
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(message)s"
        )
    else:
        logging.basicConfig(level=logging.INFO)

    if options.ignore_cert:
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

    logging.debug("Generating basic configuration")
    configuration = build_configuration()

    run_disclaimr_milter()


if __name__ == "__main__":
    main()
