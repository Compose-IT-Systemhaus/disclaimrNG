"""disclaimrNG — milter daemon entry point."""

from __future__ import annotations

__version__ = "v2.0.0.dev0"

import argparse
import logging
import os
import signal
import sys
import time
import traceback

import django
import ldap
import libmilter as lm

from disclaimr.query_cache import QueryCache  # noqa: F401  -- re-exported

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "disclaimrweb.settings")
django.setup()

from django.db import connections  # noqa: E402  -- after django.setup()

from disclaimr.configuration_helper import build_configuration  # noqa: E402
from disclaimr.logging_helper import set_queue_id  # noqa: E402
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


# How long (seconds) the sender-IP prefilter is reused before it is rebuilt
# from the database, so new or changed requirements apply without a restart.
CONFIG_TTL = float(os.environ.get("MILTER_CONFIG_TTL", "60"))

configuration: dict = {}
_configuration_built_at = 0.0
options: argparse.Namespace


def refresh_configuration(force: bool = False) -> None:
    """(Re)build the sender-IP prefilter once :data:`CONFIG_TTL` has expired.

    Runs in the accepting parent process. Its database connection is closed
    right afterwards: the per-connection children are forked from this
    process and must not share (and corrupt) the parent's socket — each child
    opens a connection of its own on first use.
    """
    global configuration, _configuration_built_at

    now = time.monotonic()
    if not force and now - _configuration_built_at < CONFIG_TTL:
        return

    try:
        configuration = build_configuration()
    except Exception:
        if force:
            raise
        syslog.exception("Cannot refresh the configuration, keeping the previous one")
    finally:
        _configuration_built_at = now
        connections.close_all()


# python-libmilter hands every protocol value (addresses, header names and
# values, body chunks, macro names) over as bytes and expects bytes back.


def _text(value: bytes | str | None) -> str:
    """Decode a protocol value received from libmilter."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _raw(value: bytes | str) -> bytes:
    """Encode a value for libmilter's reply methods."""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8", errors="surrogateescape")


def _macros(cmd_dict: dict | None) -> dict[str, str]:
    """Return the MTA macros (``i``, ``mail_addr``, …) with str keys and values."""
    return {_text(key): _text(value) for key, value in (cmd_dict or {}).items()}


def _address(value: bytes | str, macros: dict[str, str], macro: str) -> str:
    """Return the bare envelope address of a MAIL FROM / RCPT TO command.

    Prefers the MTA's parsed ``{mail_addr}`` / ``{rcpt_addr}`` macro; the raw
    command argument carries angle brackets and possibly ESMTP parameters.
    """
    if macros.get(macro):
        return macros[macro]
    address = _text(value).split("\0", 1)[0].strip()
    if address.startswith("<") and address.endswith(">"):
        address = address[1:-1]
    return address


class DisclaimrMilter(lm.ForkMixin, lm.MilterProtocol):
    """Per-connection milter instance.

    Delegates the actual heavy lifting to :class:`MilterHelper` and short-circuits
    callbacks once the helper has decided no rule applies.
    """

    def __init__(self, opts: int = 0, protos: int = 0) -> None:
        lm.MilterProtocol.__init__(self, opts, protos)
        lm.ForkMixin.__init__(self)

        # Instantiated in the accepting parent right before the fork.
        refresh_configuration()
        self.helper = MilterHelper(configuration)
        logging.debug("Initialising Milter Fork")

    def _track_queue_id(self, macros: dict[str, str]) -> None:
        if macros.get("i"):
            set_queue_id(macros["i"])

    @lm.noReply
    def connect(self, hostname, family, ip, port, cmd_dict):
        hostname, ip = _text(hostname), _text(ip)
        logging.debug("CONNECT: %s, %s, %s, %s", hostname, family, ip, port)
        self.helper.connect(hostname, family, ip, port, _macros(cmd_dict))
        return lm.CONTINUE

    @lm.noReply
    def helo(self, heloname):
        if not self.helper.enabled:
            logging.debug("Ignoring HELO since CONNECT didn't match...")
            return lm.CONTINUE
        logging.debug("HELO: %s", _text(heloname))
        return lm.CONTINUE

    @lm.noReply
    def mailFrom(self, addr, cmd_dict):
        # A new mail starts — possibly not the first one on this connection.
        self.helper.reset()
        macros = _macros(cmd_dict)
        set_queue_id(macros.get("i", ""))

        if not self.helper.enabled:
            logging.debug("Ignoring MAIL-FROM since a previous rule didn't match...")
            return lm.CONTINUE
        addr = _address(addr, macros, "mail_addr")
        logging.debug("MAILFROM: %s", addr)
        self.helper.mail_from(addr, macros)
        return lm.CONTINUE

    @lm.noReply
    def rcpt(self, recip, cmd_dict):
        if self.helper.rcptmatch:
            logging.debug(
                "We already have a positive recipient match, skipping further RCPT checks."
            )
            return lm.CONTINUE
        macros = _macros(cmd_dict)
        self._track_queue_id(macros)
        recip = _address(recip, macros, "rcpt_addr")
        logging.debug("RCPT: %s", recip)
        self.helper.rcpt(recip, macros)
        return lm.CONTINUE

    @lm.noReply
    def header(self, key, val, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring HEADER since a previous rule didn't match...")
            return lm.CONTINUE
        macros = _macros(cmd_dict)
        self._track_queue_id(macros)
        key, val = _text(key), _text(val)
        logging.debug("HEADER: %s: %s", key, val)
        self.helper.header(key, val, macros)
        return lm.CONTINUE

    @lm.noReply
    def eoh(self, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring END-OF-HEADER since a previous rule didn't match...")
            return lm.CONTINUE
        macros = _macros(cmd_dict)
        self._track_queue_id(macros)
        self.helper.eoh(macros)
        return lm.CONTINUE

    @lm.noReply
    def body(self, chunk, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring BODY since a previous rule didn't match...")
            return lm.CONTINUE
        logging.debug("BODY: chunk of %d bytes", len(chunk))
        self.helper.body(chunk, cmd_dict)
        return lm.CONTINUE

    def eob(self, cmd_dict):
        if not self.helper.enabled:
            logging.debug("Ignoring END-OF-BODY since a previous rule didn't match...")
            self._qid = None
            return lm.CONTINUE

        logging.debug("ENDOFBODY: Processing actions...")
        macros = _macros(cmd_dict)
        self._track_queue_id(macros)
        tasks = self.helper.eob(macros) or {}

        if "repl_body" in tasks:
            self.replBody(_raw(tasks["repl_body"]))

        for header, value in tasks.get("add_header", {}).items():
            self.addHeader(_raw(header), _raw(value))

        for header, value in tasks.get("change_header", {}).items():
            self.chgHeader(_raw(header), _raw(value))

        for header in tasks.get("delete_header", []):
            self.chgHeader(_raw(header), b"")

        # Done with this mail — close() only reports mails that got stuck.
        self._qid = None
        return lm.CONTINUE

    def abort(self):
        logging.debug("ABORT: resetting the mail state")
        self.helper.reset()

    def close(self):
        logging.debug("Close called. QID: %s", self._qid)
        if self._qid:
            syslog.error(
                "Message %s could not be processed! If you found a bug, please "
                "report it at https://github.com/Compose-IT-Systemhaus/disclaimrNG",
                _text(self._qid),
            )
        connections.close_all()


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
    global options

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
    refresh_configuration(force=True)

    run_disclaimr_milter()


if __name__ == "__main__":
    main()
