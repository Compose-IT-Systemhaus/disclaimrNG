"""Milter helper used by the disclaimrNG milter daemon.

The :class:`MilterHelper` is invoked stage-by-stage by the milter as a mail is
received. It narrows the set of matching :class:`~disclaimrwebadmin.models.Requirement`
records as more envelope/header/body data becomes known. Once all chunks have
arrived, :meth:`MilterHelper.eob` carries out the matching actions and returns a
workflow dictionary that the milter applies back to the MTA.
"""

from __future__ import annotations

import base64
import copy
import email
import email.encoders
import email.message
import email.mime.message
import email.mime.multipart
import email.mime.text
import html
import logging
import quopri
import re
from collections.abc import Callable
from typing import Any

import ldap
import ldap.filter
import netaddr
from django.db.models import Prefetch
from lxml import etree

from disclaimr.query_cache import QueryCache
from disclaimrwebadmin import constants, models

syslog = logging.getLogger("disclaimr")

# Tag like {key} but not the {rt}/{/rt} wrapper itself.
_TEMPLATE_TAG_RE = re.compile(r"\{((?!rt|/rt)[^}]*)\}")
# Subkey form: key["subkey"].
_SUBKEY_TAG_RE = re.compile(r'^([^\[]*)\["([^"]*)"\]$')
# ``{rt}…{/rt}`` wraps a part of a line that only makes sense when its tags
# have values (``{rt}Phone: {resolver["telephonenumber"]}{/rt}``). The block
# is dropped — together with the line break before or after it — as soon as
# one of its tags comes out empty.
_RT_BLOCK_RE = re.compile(r"(\n)?\{rt\}(.*?)\{/rt\}(\r|<br />)?")
# ``resolver["attr"]`` references — only these attributes are fetched from LDAP.
_RESOLVER_REF_RE = re.compile(r'resolver\["([^"]+)"\]', re.IGNORECASE)

_HTML_ESCAPE_TABLE = str.maketrans(
    {"&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;"}
)

# Bound, network-level timeouts so an unreachable LDAP server can never hang
# the milter (or the synchronous signature-test admin view) for more than a
# few seconds. python-ldap's defaults are effectively infinite, which used to
# take down gunicorn workers.
_LDAP_TIMEOUT = 5


def _to_str(value: Any, charset: str = "utf-8") -> str:
    """Decode bytes (LDAP attribute values, body chunks) to str."""
    if isinstance(value, bytes):
        try:
            return value.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return value.decode("utf-8", errors="replace")
    return value


def _identity(text: str) -> str:
    return text


def escape_html_value(value: str) -> str:
    """Escape a substituted value for an HTML disclaimer (text and attributes)."""
    return html.escape(value, quote=True)


# Matches an image reference of the form ``image["slug"]`` (case-insensitive
# on the key, case-sensitive on the slug since slugs *are* case-sensitive).
_IMAGE_REF_RE = re.compile(r'image\["([^"]+)"\]', re.IGNORECASE)


def _media_base_url() -> str:
    """Return the absolute base URL prepended to image src attributes."""
    from django.conf import settings

    return getattr(settings, "MEDIA_BASE_URL", "") or settings.MEDIA_URL.rstrip("/")


def _build_image_replacements(
    disclaimer_text: str, content_type: str
) -> dict[str, str]:
    """Resolve ``image["slug"]`` references against the SignatureImage table.

    Returns a slug → rendered-fragment dict. For HTML disclaimers the
    fragment is an ``<img>`` tag with the absolute URL; for plaintext it is
    just the URL. Slugs that don't resolve are omitted — the caller's
    template_fail logic decides whether to skip the action.
    """
    slugs = {m.lower() for m in _IMAGE_REF_RE.findall(disclaimer_text)}
    if not slugs:
        return {}

    base = _media_base_url()
    rendered: dict[str, str] = {}
    for image in models.SignatureImage.objects.filter(slug__in=slugs):
        if not image.image:
            continue
        absolute_url = f"{base}/{image.image.name}"
        if content_type == "text/html":
            alt = image.alt_text or image.name
            attrs = [f'src="{html.escape(absolute_url)}"', f'alt="{html.escape(alt)}"']
            if image.width:
                attrs.append(f'width="{image.width}"')
            if image.height:
                attrs.append(f'height="{image.height}"')
            rendered[image.slug.lower()] = f"<img {' '.join(attrs)} />"
        else:
            rendered[image.slug.lower()] = absolute_url
    return rendered


def _lookup_tag(token: str, replacements: dict[str, Any]) -> tuple[str, str | None]:
    """Resolve a tag body (``sender``, ``resolver["cn"]``) against ``replacements``.

    Returns ``(group, value)`` where ``group`` is the lower-cased top-level
    key and ``value`` is ``None`` if the tag cannot be resolved.
    """
    key = token.lower()
    subkey_match = _SUBKEY_TAG_RE.match(key)
    if subkey_match:
        group, subkey = subkey_match.groups()
        table = replacements.get(group)
        if isinstance(table, dict) and subkey in table:
            return group, str(table[subkey])
        return group, None

    value = replacements.get(key)
    if value is None or isinstance(value, dict):
        return key, None
    return key, str(value)


def render_template(
    template: str,
    replacements: dict[str, Any],
    *,
    template_fail: bool = False,
    literal: Callable[[str], str] = _identity,
    escape: Callable[[str], str] = _identity,
) -> str | None:
    """Replace ``{key}`` and ``{key["subkey"]}`` tags in ``template``.

    The template is rendered in a single pass: substituted values are never
    scanned for tags again, so a value that looks like a tag itself (say a
    subject line of ``{header["subject"]}``) can neither expand recursively
    nor loop forever.

    ``literal`` is applied to the template text between the tags, ``escape``
    to every substituted value except ``image`` tags, which are inserted
    verbatim (they already are rendered markup or a URL).

    Returns ``None`` when ``template_fail`` is set and a tag cannot be
    resolved; otherwise unresolvable tags render as an empty string.
    """

    def render(segment: str) -> tuple[str, bool] | None:
        """Render ``segment``; returns ``(text, had_empty_value)``."""
        pieces: list[str] = []
        had_empty = False
        pos = 0
        for match in _TEMPLATE_TAG_RE.finditer(segment):
            pieces.append(literal(segment[pos : match.start()]))
            pos = match.end()

            group, value = _lookup_tag(match.group(1), replacements)
            if value is None:
                if template_fail:
                    syslog.warning("Cannot resolve key %s. Skipping", group)
                    return None
                logging.debug(
                    "Cannot resolve '%s' for '%s'",
                    match.group(1),
                    replacements.get("sender", ""),
                )
                value = ""

            if not value:
                had_empty = True
            else:
                pieces.append(value if group == "image" else escape(value))

        pieces.append(literal(segment[pos:]))
        return "".join(pieces), had_empty

    output: list[str] = []
    pos = 0
    for block in _RT_BLOCK_RE.finditer(template):
        rendered = render(template[pos : block.start()])
        if rendered is None:
            return None
        output.append(rendered[0])
        pos = block.end()

        inner = render(block.group(2))
        if inner is None:
            return None
        if inner[1]:
            logging.debug("Removing tag...")
            continue
        output.append(literal(block.group(1) or "") + inner[0] + literal(block.group(3) or ""))

    rendered = render(template[pos:])
    if rendered is None:
        return None
    output.append(rendered[0])
    return "".join(output)


class MilterHelper:
    """Stateful helper that processes mails of one MTA connection.

    The MTA may send several mails over the same connection; :meth:`reset`
    (called by the milter at every ``MAIL FROM``) clears the per-mail state
    while keeping what :meth:`connect` learned about the client.
    """

    def __init__(self, configuration: dict[str, Any]) -> None:
        self.configuration = configuration
        self.mail_data: dict[str, Any] = {
            "headers": [],
            "headers_dict": {},
            "body": "",
        }
        self.enabled = True
        self.rcptmatch = False
        self.requirements: list[int] = []
        self.actions: list[Any] = []
        self.charsetsmatch = True

        # Requirement ids matched by the client IP — the starting point of
        # every mail on this connection.
        self._connection_requirements: list[int] = []
        # Raw body chunks; joined and decoded once in eob().
        self._body_chunks: list[bytes] = []
        # Requirement rows of the current mail, fetched once on first use.
        self._requirement_rows: dict[int, models.Requirement] | None = None
        # Per-mail memos so multipart mails don't repeat LDAP / DB lookups
        # for every text part.
        self._resolver_cache: dict[int, tuple[bool, dict[str, str]]] = {}
        self._image_cache: dict[tuple[str, str], dict[str, str]] = {}

    def reset(self) -> None:
        """Forget everything about the previous mail on this connection."""
        sender_ip = self.mail_data.get("sender_ip")
        self.mail_data = {"headers": [], "headers_dict": {}, "body": ""}
        if sender_ip is not None:
            self.mail_data["sender_ip"] = sender_ip
        self.requirements = list(self._connection_requirements)
        self.enabled = bool(self.requirements)
        self.rcptmatch = False
        self.charsetsmatch = True
        self._body_chunks = []
        self._requirement_rows = None
        self._resolver_cache = {}
        self._image_cache = {}

    def connect(self, hostname: str, family: Any, ip: str, port: int, cmd_dict: dict) -> None:
        """Called when a client connects to the milter."""
        self.mail_data["sender_ip"] = ip

        try:
            address: netaddr.IPAddress | None = netaddr.IPAddress(ip)
        except (netaddr.AddrFormatError, TypeError, ValueError):
            logging.debug("Cannot parse client address %r.", ip)
            address = None

        if address is not None:
            for sender_ip in self.configuration["sender_ip"]:
                if address in sender_ip["ip"] and sender_ip["id"] not in self.requirements:
                    logging.debug("Found IP in a requirement.")
                    self.requirements.append(sender_ip["id"])

        self._connection_requirements = list(self.requirements)

        if not self.requirements:
            logging.debug("Couldn't find the IP in any requirement. Skipping.")
            self.enabled = False

    def _active_requirements(self) -> list[models.Requirement]:
        """Return the Requirement rows still in play for the current mail.

        The rows (with their rule) are loaded once, the first time a stage
        needs them; the following stages only filter that list instead of
        querying the database again for every envelope/header/body check.
        """
        if self._requirement_rows is None:
            self._requirement_rows = {
                req.id: req
                for req in models.Requirement.objects.filter(
                    id__in=self.requirements, enabled=True
                ).select_related("rule")
            }
            self.requirements = [r for r in self.requirements if r in self._requirement_rows]
        return [self._requirement_rows[r] for r in self.requirements]

    def _drop_requirements(self, rejected: set[int]) -> None:
        if rejected:
            self.requirements = [r for r in self.requirements if r not in rejected]

    def mail_from(self, addr: str, cmd_dict: dict) -> None:
        """Called when the MAIL FROM envelope value has been received."""
        self._drop_requirements(
            {req.id for req in self._active_requirements() if not re.search(req.sender, addr)}
        )

        if not self.requirements:
            logging.debug("Couldn't match sender address in any requirement. Skipping.")
            self.enabled = False

        self.mail_data["envelope_from"] = addr

    def rcpt(self, recip: str, cmd_dict: dict) -> None:
        """Called when an RCPT TO envelope value has been received."""
        for req in self._active_requirements():
            if not re.search(req.recipient, recip):
                self._drop_requirements({req.id})
                if not self.requirements:
                    logging.debug(
                        "Couldn't match recipient address in any requirement. Skipping."
                    )
                    self.enabled = False
            else:
                logging.debug("Recipient address matches regex.")
                self.rcptmatch = True
                self.enabled = True

        self.mail_data["envelope_rcpt"] = recip

    def header(self, key: str, val: str, cmd_dict: dict) -> None:
        """Called for each header line."""
        self.mail_data["headers_dict"][key.lower()] = val
        self.mail_data["headers"].append(f"{key}: {val}")

    def eoh(self, cmd_dict: dict) -> None:
        """Called once all headers have been received."""
        joined = "\n".join(self.mail_data["headers"])
        self._drop_requirements(
            {req.id for req in self._active_requirements() if not re.search(req.header, joined)}
        )

        if not self.requirements:
            logging.debug("Couldn't match header in any requirement. Skipping.")
            self.enabled = False

    def body(self, chunk: bytes | str, cmd_dict: dict) -> None:
        """Called for each body chunk.

        Chunks are only collected here and decoded once in :meth:`eob`:
        decoding chunk by chunk mangles multi-byte characters that straddle
        a chunk boundary, and growing one string per chunk is quadratic in
        the size of the mail.
        """
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        self._body_chunks.append(chunk)

    def eob(self, cmd_dict: dict) -> dict[str, Any] | None:
        """Called once the entire body has been received.

        Returns the workflow dictionary that the milter applies to the mail
        (replace body, add/change/delete headers).
        """
        body = b"".join(self._body_chunks).decode("utf-8", errors="replace")
        self._body_chunks = []
        self.mail_data["body"] = body

        self._drop_requirements(
            {req.id for req in self._active_requirements() if not re.search(req.body, body)}
        )

        if not self.requirements:
            logging.debug("Couldn't match body in any requirement. Skipping.")
            self.enabled = False
            return None

        rules_blacklist: set[int] = set()
        rules: list[int] = []
        for req in self._active_requirements():
            if req.action == constants.REQ_ACTION_DENY:
                rules_blacklist.add(req.rule_id)
            if req.rule_id not in rules_blacklist and req.rule_id not in rules:
                rules.append(req.rule_id)

        rules = [r for r in rules if r not in rules_blacklist]

        if not rules:
            self.enabled = False
            return None

        # Headers and body arrive separately from the MTA; the blank line
        # between them has to be put back, otherwise a first body line that
        # looks like a header ("Note: …") is swallowed into the header block.
        raw_headers = "\n".join(self.mail_data["headers"])
        mail = email.message_from_string(
            f"{raw_headers}\n\n{body}" if raw_headers else f"\n{body}"
        )
        # do_action() works on copies, so this stays the unmodified original.
        orig_mail = mail

        actions = (
            models.Action.objects.filter(enabled=True)
            .select_related("disclaimer")
            .prefetch_related("directory_servers")
        )
        for rule in models.Rule.objects.filter(id__in=rules).prefetch_related(
            Prefetch("action_set", queryset=actions)
        ):
            for action in rule.action_set.all():
                syslog.info(
                    "Adding Disclaimer (Action: %s | Rule: %s | Disclaimer: %s)",
                    action.name,
                    rule.name,
                    action.disclaimer.name,
                )
                returned_mail = self.do_action(mail, action)
                if returned_mail is not None:
                    mail = returned_mail

            if not rule.continue_rules:
                break

        workflow: dict[str, Any] = {}

        for header in mail.keys():
            if header not in orig_mail:
                workflow.setdefault("add_header", {})[header] = mail[header]
            elif mail[header] != orig_mail[header]:
                workflow.setdefault("change_header", {})[header] = mail[header]

        for header in orig_mail.keys():
            if header not in mail:
                workflow.setdefault("delete_header", []).append(header)

        # Strip headers from the rebuilt mail before sending it back to the
        # MTA — the milter only replaces the body. We keep everything after the
        # first blank line (whatever line ending it uses).
        new_body = mail.as_string()
        strip_place_rn = new_body.find("\r\n\r\n")
        strip_place_n = new_body.find("\n\n")

        if strip_place_n == -1:
            strip_place = strip_place_rn + 2 if strip_place_rn != -1 else 0
        elif strip_place_rn == -1:
            strip_place = strip_place_n + 2
        elif strip_place_rn < strip_place_n:
            strip_place = strip_place_rn + 2
        elif strip_place_n < strip_place_rn:
            strip_place = strip_place_n + 2
        else:
            strip_place = 0

        new_body = new_body[strip_place:]

        if mail.is_multipart():
            logging.debug("Stripping trailing line feeds from multi-part payload")
            new_body = new_body.rstrip()

        workflow["repl_body"] = new_body
        return workflow

    @staticmethod
    def make_html(text: str) -> str:
        """Escape ``text`` to HTML and convert newlines into ``<br />``."""
        return text.replace("\r\n", "\n").translate(_HTML_ESCAPE_TABLE).replace("\n", "<br />")

    @staticmethod
    def decode_mail(mail: email.message.Message) -> tuple[str, str]:
        """Return ``(content_transfer_encoding, decoded_payload)`` for ``mail``.

        The payload is always returned as ``str``. The Python 3 email
        machinery happily flips between ``str`` and ``bytes`` for the
        underlying payload depending on whether ``set_payload`` was last
        called with bytes — callers (and tests) should not have to care.
        """
        mail_text = mail.get_payload()

        if "Content-Transfer-Encoding" in mail:
            encoding = mail["Content-Transfer-Encoding"].lower()
            logging.debug("Pre Content-Transfer-Encoding: %s", encoding)

            if encoding == "quoted-printable":
                mail_text = quopri.decodestring(mail_text)
            elif encoding == "base64":
                mail_text = base64.b64decode(mail_text)
        else:
            syslog.warning(
                "Missing Content-Transfer-Encoding header, this violates RFC! "
                "Falling back to 78bit"
            )
            encoding = "78bit"

        charset = mail.get_content_charset() or "utf-8"
        return encoding, _to_str(mail_text, charset)

    def _directory_servers_for(
        self, action: models.Action, envelope_from: str
    ) -> list[models.DirectoryServer]:
        """Return the directory servers to query for ``action``.

        Resolution order:

        1. ``action.directory_servers`` if any are linked — explicit wins.
        2. Otherwise, look up the tenant that owns the sender's domain and
           use its directory servers — this is the multi-tenant path.

        Disabled servers are filtered out at this layer so the inner loop
        in :meth:`_resolve_sender` only sees what's actually queryable.
        """
        explicit = list(action.directory_servers.all())
        if explicit:
            return explicit

        tenant = models.Tenant.match_sender(envelope_from)
        if tenant is None:
            return []
        return list(tenant.directory_servers.filter(enabled=True))

    @staticmethod
    def _requested_attributes(action: models.Action) -> list[str] | None:
        """Return the LDAP attributes the action's disclaimer references.

        Asking for just these keeps bulky attributes (``thumbnailPhoto``,
        long ``memberOf`` lists, …) off the wire. ``None`` requests all
        attributes — used when the disclaimer references none, so the lookup
        only decides whether the sender resolves at all.
        """
        disclaimer = action.disclaimer
        names = {
            name.lower()
            for name in _RESOLVER_REF_RE.findall(f"{disclaimer.text}\n{disclaimer.html}")
        }
        return sorted(names) or None

    def _resolve_sender(
        self, action: models.Action, replacements: dict[str, Any]
    ) -> bool:
        """Populate ``replacements['resolver']`` from configured directory servers.

        The directory lookup runs once per action and mail; the result is
        reused for every further MIME part the action is applied to.

        Returns whether at least one directory server delivered a result.
        """
        cached = self._resolver_cache.get(action.pk)
        if cached is None:
            cached = self._lookup_sender(action)
            self._resolver_cache[action.pk] = cached

        resolved_successfully, attributes = cached
        replacements["resolver"].update(attributes)
        return resolved_successfully

    def _lookup_sender(self, action: models.Action) -> tuple[bool, dict[str, str]]:
        """Query the directory servers for the envelope sender.

        Returns ``(resolved_successfully, attributes)`` with lower-cased
        attribute names.
        """
        resolved_successfully = False
        attributes: dict[str, str] = {}
        envelope_from = self.mail_data["envelope_from"]
        attrlist = self._requested_attributes(action)

        for directory_server in self._directory_servers_for(action, envelope_from):
            if not directory_server.enabled:
                logging.debug(
                    "Directory server %s is disabled. Skipping.", directory_server.name
                )
                continue

            logging.debug("Connecting to directory server %s", directory_server.name)
            query = directory_server.search_query % (
                ldap.filter.escape_filter_chars(envelope_from),
            )
            cache_key = f"{query}|{','.join(attrlist) if attrlist else '*'}"
            result = None

            if directory_server.enable_cache:
                result = QueryCache.get(directory_server, cache_key)
                if result is not None:
                    resolved_successfully = True

            if result is None:
                for url in directory_server.directoryserverurl_set.all():
                    logging.debug("Trying url %s", url.url)
                    outcome = self._search_url(directory_server, url, query, attrlist)
                    if outcome is None:
                        continue
                    result = outcome

                    if not result:
                        if action.resolve_sender_fail:
                            syslog.warning(
                                "Cannot resolve email %s. Skipping", envelope_from
                            )
                            return False, attributes
                        syslog.warning("Cannot resolve email %s", envelope_from)
                        continue

                    if len(result) > 1:
                        syslog.warning(
                            "Multiple results found for email %s.", envelope_from
                        )
                        if action.resolve_sender_fail:
                            syslog.warning(
                                "Cannot reliably resolve email %s. Skipping",
                                envelope_from,
                            )
                            return False, attributes

                    logging.debug("Found entry %s", result[0][0])

                    if directory_server.enable_cache:
                        QueryCache.set(directory_server, cache_key, result)

                    resolved_successfully = True
                    break

            if result is not None and len(result) == 1:
                # Flatten the LDAP result into the replacement dict. python-ldap
                # returns attribute values as bytes; decode them before use.
                for key, raw_values in result[0][1].items():
                    try:
                        attributes[key.lower()] = ",".join(_to_str(v) for v in raw_values)
                    except UnicodeDecodeError:
                        # Binary attribute (e.g. thumbnailPhoto) — base64-encode it.
                        attributes[key.lower()] = base64.b64encode(
                            b"".join(raw_values)
                        ).decode("ascii")

        return resolved_successfully, attributes

    @staticmethod
    def _search_url(
        directory_server: models.DirectoryServer,
        url: models.DirectoryServerURL,
        query: str,
        attrlist: list[str] | None,
    ) -> list | None:
        """Bind to ``url`` and run ``query``; ``None`` if the server is unusable."""
        conn = ldap.initialize(url.url)
        conn.set_option(ldap.OPT_NETWORK_TIMEOUT, _LDAP_TIMEOUT)
        conn.set_option(ldap.OPT_TIMEOUT, _LDAP_TIMEOUT)
        # Active Directory answers subtree searches on the domain root with
        # referrals; chasing them (anonymously) only costs time.
        conn.set_option(ldap.OPT_REFERRALS, 0)

        ldap_user = ""
        ldap_password = ""
        if directory_server.auth == constants.DIR_AUTH_SIMPLE:
            ldap_user = directory_server.userdn
            ldap_password = directory_server.password

        try:
            try:
                conn.simple_bind_s(ldap_user, ldap_password)
            except ldap.SERVER_DOWN:
                syslog.warning("Cannot reach server %s. Skipping.", url)
                return None
            except ldap.TIMEOUT:
                syslog.warning("Timeout binding to server %s. Skipping.", url)
                return None
            except (ldap.INVALID_CREDENTIALS, ldap.INVALID_DN_SYNTAX):
                syslog.warning(
                    "Cannot authenticate to directory server %s with dn %s. Skipping.",
                    url,
                    directory_server.userdn,
                )
                return None

            try:
                return conn.search_s(
                    directory_server.base_dn, ldap.SCOPE_SUBTREE, query, attrlist
                )
            except ldap.SERVER_DOWN:
                syslog.warning("Cannot reach server %s. Skipping.", url)
            except ldap.TIMEOUT:
                syslog.warning("Timeout searching server %s. Skipping.", url)
            except (ldap.INVALID_CREDENTIALS, ldap.NO_SUCH_OBJECT):
                syslog.warning(
                    "Cannot authenticate to directory server %s as guest or "
                    "cannot query. Skipping.",
                    url,
                )
            return None
        finally:
            try:
                conn.unbind_s()
            except ldap.LDAPError:
                pass

    def _image_replacements(self, disclaimer_text: str, content_type: str) -> dict[str, str]:
        """Memoised :func:`_build_image_replacements` (one query per mail)."""
        key = (disclaimer_text, content_type)
        if key not in self._image_cache:
            self._image_cache[key] = _build_image_replacements(disclaimer_text, content_type)
        return self._image_cache[key]

    def _replace_template_tags(
        self,
        action: models.Action,
        disclaimer_text: str,
        replacements: dict[str, Any],
        charset: str | None = None,
        *,
        literal: Callable[[str], str] = _identity,
        escape: Callable[[str], str] = _identity,
    ) -> str | None:
        """Replace ``{key}`` and ``{key["subkey"]}`` tags in ``disclaimer_text``.

        Returns the substituted string, or ``None`` if the action should be
        skipped (template_fail and an unresolvable tag). See
        :func:`render_template` for the details.
        """
        del charset  # currently unused; kept for API stability with the old code
        return render_template(
            disclaimer_text,
            replacements,
            template_fail=action.disclaimer.template_fail,
            literal=literal,
            escape=escape,
        )

    def do_action(
        self, mail_parameter: email.message.Message, action: models.Action
    ) -> email.message.Message | None:
        """Apply ``action`` to a copy of ``mail_parameter`` (recursing into MIME parts).

        Returns the modified copy, or ``None`` if the action was skipped.
        """
        return self._apply_action(copy.deepcopy(mail_parameter), action)

    def _apply_action(
        self, mail: email.message.Message, action: models.Action
    ) -> email.message.Message | None:
        """Apply ``action`` to ``mail`` in place.

        ``None`` means the action was skipped for this (part of the) mail,
        which is then left untouched.
        """
        if mail.is_multipart():
            new_payloads = []
            for payload in mail.get_payload():
                returned_mail = self._apply_action(payload, action)
                # A part the action skipped (unresolvable template, failed
                # sender resolution, …) stays as it was — it must not vanish
                # from the mail.
                new_payloads.append(payload if returned_mail is None else returned_mail)
            mail.set_payload(new_payloads)
            return mail

        logging.debug("Got part of content-type %s", mail.get_content_type())

        if (
            mail.get_content_type().lower() not in ("text/plain", "text/html")
            and action.action != constants.ACTION_ACTION_ADDPART
        ):
            syslog.warning(
                "Content-type %s is currently not supported for actions other than "
                "addpart.",
                mail.get_content_type(),
            )
            return mail

        # Pick disclaimer content type (with HTML fallback for ADDPART on
        # non-text/non-html parts).
        if (
            mail.get_content_type().lower() not in ("text/plain", "text/html")
            and action.action == constants.ACTION_ACTION_ADDPART
        ):
            content_type = "text/html" if action.disclaimer.use_html_fallback else "text/plain"
        else:
            content_type = mail.get_content_type().lower()

        if content_type == "text/plain":
            disclaimer_text = action.disclaimer.text
            disclaimer_charset = action.disclaimer.text_charset
            do_replace = action.disclaimer.text_use_template
        elif action.disclaimer.html_use_text:
            disclaimer_text = action.disclaimer.text
            disclaimer_charset = action.disclaimer.text_charset
            do_replace = action.disclaimer.text_use_template
        else:
            disclaimer_text = action.disclaimer.html
            disclaimer_charset = action.disclaimer.html_charset
            do_replace = action.disclaimer.html_use_template

        # The plaintext disclaimer is turned into HTML for an HTML part.
        text_as_html = content_type == "text/html" and action.disclaimer.html_use_text

        charset = mail.get_content_charset() or disclaimer_charset
        logging.debug("Message charset is: %s", charset)
        logging.debug("Disclaimer charset is: %s", disclaimer_charset)

        self.charsetsmatch = charset.lower() == disclaimer_charset.lower()
        if not self.charsetsmatch:
            logging.debug("Message and Disclaimer have different charsets...")
            # In Py3 disclaimer_text is always str — re-decode if needed.
            if isinstance(disclaimer_text, bytes):
                disclaimer_text = disclaimer_text.decode(disclaimer_charset, "replace")

        if do_replace:
            logging.debug("Building replacement dictionary")

            replacements: dict[str, Any] = {
                "sender": self.mail_data["envelope_from"],
                "recipient": self.mail_data["envelope_rcpt"],
                "header": self.mail_data["headers_dict"],
                "resolver": {},
                "image": self._image_replacements(disclaimer_text, content_type),
            }

            if action.resolve_sender:
                resolved_successfully = self._resolve_sender(action, replacements)
                if not resolved_successfully and action.resolve_sender_fail:
                    syslog.warning(
                        "Cannot resolve email %s. Skipping",
                        self.mail_data["envelope_from"],
                    )
                    return None

            if text_as_html:
                # Escape the template text and the values separately so
                # image tags survive as real <img> markup.
                replaced = self._replace_template_tags(
                    action,
                    disclaimer_text.replace("\r\n", "\n"),
                    replacements,
                    charset,
                    literal=self.make_html,
                    escape=self.make_html,
                )
            elif content_type == "text/html":
                replaced = self._replace_template_tags(
                    action, disclaimer_text, replacements, charset, escape=escape_html_value
                )
            else:
                replaced = self._replace_template_tags(
                    action, disclaimer_text, replacements, charset
                )
            if replaced is None:
                return None
            disclaimer_text = replaced
        elif text_as_html:
            disclaimer_text = self.make_html(disclaimer_text)

        logging.debug(
            "Adding Disclaimer %s to body (%s)", action.disclaimer.name, content_type
        )

        encoding, new_text = self.decode_mail(mail)
        new_text = _to_str(new_text, charset)

        if action.action == constants.ACTION_ACTION_REPLACETAG:
            new_text = re.sub(action.action_parameters, disclaimer_text, new_text)

        elif action.action == constants.ACTION_ACTION_ADD:
            if content_type == "text/plain":
                new_text = f"{new_text}\n{disclaimer_text}"
            elif content_type == "text/html":
                # ``etree.HTML`` only exposes child *elements* via iteration —
                # bare text inside ``<body>`` is hidden away in
                # ``body.text`` / ``element.tail`` and silently disappears
                # when we copy "for element in disclaimer_body". For a
                # plaintext-as-HTML disclaimer (the default when
                # ``html_use_text=True``) that meant nothing got appended
                # at all. Wrap such a disclaimer in a ``<p>`` so it parses
                # as a real element subtree.
                if not disclaimer_text.lstrip().startswith("<"):
                    disclaimer_text = f"<p>{disclaimer_text}</p>"

                html_part = etree.HTML(new_text)
                disclaimer_part = etree.HTML(disclaimer_text)
                disclaimer_body = disclaimer_part.xpath("body")[0]

                bodies = html_part.xpath("body")
                target = bodies[0] if bodies else html_part
                # Copy any leading text that lxml stuffed onto body.text
                # (rare for our wrapped-in-<p> case but cheap insurance).
                if disclaimer_body.text:
                    if len(target) > 0:
                        last = target[-1]
                        last.tail = (last.tail or "") + disclaimer_body.text
                    else:
                        target.text = (target.text or "") + disclaimer_body.text
                for element in disclaimer_body:
                    target.append(element)

                new_text = etree.tostring(
                    html_part, pretty_print=True, method="html"
                ).decode(charset, "replace")

        elif action.action == constants.ACTION_ACTION_ADDPART:
            if content_type == "text/plain":
                mail_disclaimer = email.mime.text.MIMEText(
                    disclaimer_text, "plain", disclaimer_charset
                )
            elif content_type == "text/html":
                mail_disclaimer = email.mime.text.MIMEText(
                    disclaimer_text, "html", disclaimer_charset
                )
            else:
                syslog.error("Unsupported content_type for ADDPART: %s", content_type)
                return None

            new_mail = email.mime.multipart.MIMEMultipart("mixed")
            bad_headers = (
                "content-type",
                "content-transfer-encoding",
                "mime-version",
                "content-disposition",
                "content-description",
            )
            for header in mail.keys():
                if header.lower() not in bad_headers:
                    new_mail.add_header(header, mail[header])

            new_mail.attach(email.mime.message.MIMEMessage(mail))
            new_mail.attach(mail_disclaimer)
            new_mail.as_string()  # let MIMEMultipart pick a boundary
            return new_mail

        else:
            syslog.error("Invalid action value %d", action.action)
            return None

        if "Content-Transfer-Encoding" in mail:
            del mail["Content-Transfer-Encoding"]

        logging.debug("Encoding %s with Charset %s", encoding, charset)

        # Python's email library decides on its own whether to base64-encode
        # a payload at ``as_string()`` time based on the payload *type*:
        # bytes always trigger base64 (regardless of the
        # Content-Transfer-Encoding header we add below). For 7bit / 8bit /
        # 78bit we keep the payload as ``str`` so it gets written out
        # unmolested. quoted-printable / base64 still need bytes because
        # the encoders mutate the payload in place.
        if encoding == "quoted-printable":
            mail.set_payload(new_text.encode(charset, "replace"))
            email.encoders.encode_quopri(mail)
        elif encoding == "base64":
            mail.set_payload(new_text.encode(charset, "replace"))
            email.encoders.encode_base64(mail)
        else:
            mail.set_payload(new_text)
            mail.add_header("Content-Transfer-Encoding", encoding)

        logging.debug(
            "Post Content-Transfer-Encoding: %s",
            mail["Content-Transfer-Encoding"].lower(),
        )
        logging.debug("Helper finished, returning mail")
        return mail
