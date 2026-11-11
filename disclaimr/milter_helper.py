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
import email.mime.image
import email.mime.message
import email.mime.multipart
import email.mime.text
import hashlib
import html
import logging
import mimetypes
import quopri
import re
from collections.abc import Callable
from typing import Any

import ldap
import ldap.filter
import netaddr
from django.db.models import Prefetch
from lxml import etree

from disclaimr.ldap_helper import open_connection
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
# Any line ending, to normalise the replacement body to CRLF.
_NEWLINE_RE = re.compile(r"\r?\n")
# ``resolver["attr"]`` references — only these attributes are fetched from LDAP.
_RESOLVER_REF_RE = re.compile(r'resolver\["([^"]+)"\]', re.IGNORECASE)

_HTML_ESCAPE_TABLE = str.maketrans(
    {"&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;"}
)


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


# shortcut: bigger images are linked instead of embedded; make it a setting if anyone needs more.
_EMBED_MAX_BYTES = 1024 * 1024


def _embedded_image(image: models.SignatureImage) -> email.mime.image.MIMEImage | None:
    """The image as an inline MIME part, or ``None`` (then the caller links it)."""
    subtype = (mimetypes.guess_type(image.image.name)[0] or "").partition("image/")[2]
    try:
        with image.image.open("rb") as fh:
            data = fh.read(_EMBED_MAX_BYTES + 1)
    except OSError as exc:
        syslog.warning("Cannot embed image %s (%s). Linking it.", image.slug, exc)
        return None
    if not subtype or len(data) > _EMBED_MAX_BYTES:
        syslog.warning("Image %s is too large or not an image. Linking it.", image.slug)
        return None
    part = email.mime.image.MIMEImage(data, subtype)
    part.add_header("Content-ID", f"<{image.slug}.{hashlib.sha1(data).hexdigest()[:8]}@disclaimr>")
    part.add_header("Content-Disposition", "inline", filename=image.image.name.rpartition("/")[2])
    return part


def _build_image_replacements(
    disclaimer_text: str,
    content_type: str,
    embedded: dict[str, email.mime.image.MIMEImage] | None = None,
) -> dict[str, str]:
    """Resolve ``image["slug"]`` references against the SignatureImage table.

    Returns a slug → rendered-fragment dict. For HTML disclaimers the
    fragment is an ``<img>`` tag with the absolute URL; for plaintext it is
    just the URL. Slugs that don't resolve are omitted — the caller's
    template_fail logic decides whether to skip the action.

    With an ``embedded`` dict, images flagged ``embed`` are referenced as ``cid:`` in
    HTML and their MIME parts are collected there (Content-ID → part).
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
            src = absolute_url
            part = _embedded_image(image) if embedded is not None and image.embed else None
            if part is not None:
                cid = part["Content-ID"].strip("<>")
                embedded[cid] = part
                src = f"cid:{cid}"
            alt = image.alt_text or image.name
            attrs = [f'src="{html.escape(src)}"', f'alt="{html.escape(alt)}"']
            if image.width:
                attrs.append(f'width="{image.width}"')
            if image.height:
                attrs.append(f'height="{image.height}"')
            rendered[image.slug.lower()] = f"<img {' '.join(attrs)} />"
        else:
            rendered[image.slug.lower()] = absolute_url
    return rendered


# LDAP_MATCHING_RULE_IN_CHAIN: memberOf including nested groups (Active Directory).
_AD_IN_CHAIN = "1.2.840.113556.1.4.1941"


def _normalize_dn(dn: str) -> str:
    """Case and blanks around ``,``/``=`` do not distinguish DNs."""
    return re.sub(r"\s*([,=])\s*", r"\1", dn.strip().lower())


def signature_html(disclaimer: Any, markup: str, *, always: bool = False) -> str:
    """``markup`` in a ``<div>`` with the default font and size of the signature.

    Without a default font the markup is returned as it is, unless ``always`` (the add
    action needs an element to copy into the mail).
    """
    style = "; ".join(
        rule
        for rule in (
            f"font-family: {disclaimer.font_family}" if disclaimer.font_family else "",
            f"font-size: {disclaimer.font_size}pt" if disclaimer.font_size else "",
        )
        if rule
    )
    if not style and not always:
        return markup
    attr = f' style="{html.escape(style)}"' if style else ""
    return f"<div{attr}>{markup}</div>"


def _is_entity_header(name: str) -> bool:
    """``Content-*`` and ``MIME-Version`` describe the body, not the mail."""
    return name.lower().startswith("content-") or name.lower() == "mime-version"


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
        # Requirement ids whose recipient regex matched at least one RCPT.
        self._rcpt_matched: set[int] = set()
        self.requirements: list[int] = []
        self.actions: list[Any] = []
        # "rule → action → signature" per action applied to the current mail.
        self.applied: list[str] = []
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
        self._image_cache: dict[
            tuple[str, str], tuple[dict[str, str], dict[str, email.mime.image.MIMEImage]]
        ] = {}
        # Images the current do_action() has to attach (Content-ID → part).
        self._pending_images: dict[str, email.mime.image.MIMEImage] = {}
        # (requirement, condition, holds) per checked directory condition; shown by the
        # signature test page.
        self.condition_log: list[tuple[str, str, bool]] = []

    def reset(self) -> None:
        """Forget everything about the previous mail on this connection."""
        sender_ip = self.mail_data.get("sender_ip")
        self.mail_data = {"headers": [], "headers_dict": {}, "body": ""}
        if sender_ip is not None:
            self.mail_data["sender_ip"] = sender_ip
        self.requirements = list(self._connection_requirements)
        self.enabled = bool(self.requirements)
        self._rcpt_matched = set()
        self.applied = []
        self.charsetsmatch = True
        self._body_chunks = []
        self._requirement_rows = None
        self._resolver_cache = {}
        self._image_cache = {}
        self.condition_log = []

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
                )
                .select_related("rule")
                .prefetch_related("conditions")
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

    @property
    def rcptmatch(self) -> bool:
        """Whether every requirement still in play has matched a recipient."""
        return bool(self.requirements) and self._rcpt_matched.issuperset(self.requirements)

    def rcpt(self, recip: str, cmd_dict: dict) -> None:
        """Called for each RCPT TO value.

        A requirement's recipient regex has to match *at least one* recipient.
        Requirements that matched none are dropped in :meth:`eoh`, once all
        recipients are known.
        """
        matched = {
            req.id for req in self._active_requirements() if re.search(req.recipient, recip)
        }
        # {recipient} is the first recipient that matched a requirement.
        if matched and not self._rcpt_matched:
            self.mail_data["envelope_rcpt"] = recip
        self._rcpt_matched |= matched
        self.mail_data.setdefault("envelope_rcpt", recip)

    def header(self, key: str, val: str, cmd_dict: dict) -> None:
        """Called for each header line."""
        self.mail_data["headers_dict"][key.lower()] = val
        self.mail_data["headers"].append(f"{key}: {val}")

    def eoh(self, cmd_dict: dict) -> None:
        """Called once all headers have been received."""
        joined = "\n".join(self.mail_data["headers"])
        self._drop_requirements(
            {
                req.id
                for req in self._active_requirements()
                if req.id not in self._rcpt_matched or not re.search(req.header, joined)
            }
        )

        if not self.requirements:
            logging.debug("Couldn't match recipient or header in any requirement. Skipping.")
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
        # Last, because it may need a directory lookup.
        self._drop_requirements(self._failed_directory_conditions())

        if not self.requirements:
            logging.debug("Couldn't match body or directory data in any requirement. Skipping.")
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
            models.Action.objects.active()
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
                    self.applied.append(
                        f"{rule.name} → {action.name} → {action.disclaimer.name}"
                    )

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

        # The milter protocol carries CRLF lines. Postfix accepts both, Stalwart writes
        # the replacement body as it is, so it must not get the LF the email package emits.
        workflow["repl_body"] = _NEWLINE_RE.sub("\r\n", new_body)
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
                "Falling back to 7bit"
            )
            encoding = "7bit"

        charset = mail.get_content_charset() or "utf-8"
        return encoding, _to_str(mail_text, charset)

    def _failed_directory_conditions(self) -> set[int]:
        """Ids of the requirements in play whose directory conditions do not hold.

        Without conditions nothing is looked up. Servers are the ones of the sender's
        tenant; if the sender cannot be looked up, no condition holds.
        """
        checked = [req for req in self._active_requirements() if req.conditions.all()]
        if not checked:
            return set()

        conditions = [c for req in checked for c in req.conditions.all()]
        attrlist = sorted(
            {c.attribute.lower() for c in conditions if c.kind == constants.COND_KIND_ATTRIBUTE}
        )
        wants_groups = any(c.kind == constants.COND_KIND_GROUP for c in conditions)
        found = self._sender_entry(attrlist, wants_groups)
        if found is None:
            syslog.warning(
                "Cannot look up %s for the directory conditions. They do not hold.",
                self.mail_data["envelope_from"],
            )
        server, values = found or (None, {})

        memberships: dict[str, bool] = {}

        def holds(condition: models.RequirementCondition) -> bool:
            if condition.kind == constants.COND_KIND_GROUP:
                if server is None:
                    return False
                key = _normalize_dn(condition.group_dn)
                if key not in memberships:
                    memberships[key] = self._is_member(server, values, condition.group_dn)
                return memberships[key]
            return any(
                re.search(condition.pattern, v)
                for v in values.get(condition.attribute.lower(), [])
            )

        failed: set[int] = set()
        for req in checked:
            results = [(c, holds(c)) for c in req.conditions.all()]
            self.condition_log += [(req.name, str(c), ok) for c, ok in results]
            if not all(ok for _, ok in results):
                failed.add(req.id)
        return failed

    def _sender_entry(
        self, attrlist: list[str], wants_groups: bool
    ) -> tuple[models.DirectoryServer, dict[str, list[str]]] | None:
        """Server and values of ``attrlist`` for the sender, from the first server that knows it.

        Servers that are not Active Directory also deliver ``memberOf`` when group
        conditions need it (AD answers those with a query, see :meth:`_is_member`).
        """
        envelope_from = self.mail_data["envelope_from"]
        tenant = models.Tenant.match_sender(envelope_from)
        servers = tenant.directory_servers.filter(enabled=True) if tenant else []
        for directory_server in servers:
            ask = list(attrlist)
            if wants_groups and directory_server.flavor != constants.DIR_FLAVOR_AD:
                ask = sorted({*ask, "memberof"})
            ask = ask or ["1.1"]  # no attributes, only whether the sender exists
            query = self._sender_query(directory_server, envelope_from)
            cache_key = f"{query}|{','.join(ask)}"
            result = (
                QueryCache.get(directory_server, cache_key)
                if directory_server.enable_cache
                else None
            )
            if result is None:
                for url in directory_server.directoryserverurl_set.all():
                    result = self._search_url(directory_server, url, query, ask)
                    if result is not None:
                        break
            if not result or len(result) != 1:
                continue
            if directory_server.enable_cache:
                QueryCache.set(directory_server, cache_key, result)
            return directory_server, {
                key.lower(): [_to_str(v) for v in raw_values]
                for key, raw_values in result[0][1].items()
            }
        return None

    def _is_member(
        self,
        directory_server: models.DirectoryServer,
        values: dict[str, list[str]],
        group_dn: str,
    ) -> bool:
        """Whether the sender belongs to ``group_dn``.

        Active Directory: a second query for the sender that also asks for the group
        through the in-chain rule, so nested groups count. Otherwise the ``memberOf``
        values of the sender are compared.
        """
        if directory_server.flavor != constants.DIR_FLAVOR_AD:
            wanted = _normalize_dn(group_dn)
            return any(_normalize_dn(v) == wanted for v in values.get("memberof", []))

        query = self._sender_query(directory_server, self.mail_data["envelope_from"])
        if not query.lstrip().startswith("("):
            query = f"({query})"
        in_group = f"(memberOf:{_AD_IN_CHAIN}:={ldap.filter.escape_filter_chars(group_dn)})"
        for url in directory_server.directoryserverurl_set.all():
            result = self._search_url(directory_server, url, f"(&{query}{in_group})", ["1.1"])
            if result is not None:
                return any(dn for dn, _ in result)  # (None, …) entries are referrals
        return False

    @staticmethod
    def _sender_query(directory_server: models.DirectoryServer, envelope_from: str) -> str:
        # Every %s becomes the address — the Active Directory default query has two of them,
        # which "%" with a one-element tuple would reject.
        return directory_server.search_query.replace(
            "%s", ldap.filter.escape_filter_chars(envelope_from)
        )

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
            query = self._sender_query(directory_server, envelope_from)
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
                    attributes[key.lower()] = ",".join(_to_str(v) for v in raw_values)

        return resolved_successfully, attributes

    @staticmethod
    def _search_url(
        directory_server: models.DirectoryServer,
        url: models.DirectoryServerURL,
        query: str,
        attrlist: list[str] | None,
    ) -> list | None:
        """Bind to ``url`` and run ``query``; ``None`` if the server is unusable."""
        conn = open_connection(url.url, directory_server)

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
            except ldap.LDAPError as exc:
                # e.g. AD demanding LDAPS/signing — must not defer the mail.
                syslog.warning("Cannot bind to server %s: %s. Skipping.", url, exc)
                return None

            try:
                results = conn.search_s(
                    directory_server.base_dn, ldap.SCOPE_SUBTREE, query, attrlist
                )
                # Active Directory adds search references (dn None) to DomainDnsZones,
                # ForestDnsZones and Configuration when the base is the domain root; they
                # are no entries, and counting them made every sender look ambiguous.
                return [entry for entry in results if entry[0] is not None]
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
            except ldap.LDAPError as exc:
                # e.g. OPERATIONS_ERROR (AD anonymous), FILTER_ERROR (bad query).
                syslog.warning("Cannot search server %s: %s. Skipping.", url, exc)
            return None
        finally:
            try:
                conn.unbind_s()
            except ldap.LDAPError:
                pass

    def _image_replacements(self, disclaimer_text: str, content_type: str) -> dict[str, str]:
        """Memoised :func:`_build_image_replacements` (one query per mail).

        The parts of embedded images are queued in ``_pending_images``; they are only
        attached once the action went through (see :meth:`do_action`).
        """
        key = (disclaimer_text, content_type)
        if key not in self._image_cache:
            embedded: dict[str, email.mime.image.MIMEImage] = {}
            replacements = _build_image_replacements(disclaimer_text, content_type, embedded)
            self._image_cache[key] = (replacements, embedded)
        replacements, embedded = self._image_cache[key]
        self._pending_images.update(embedded)
        return replacements

    @staticmethod
    def _attach_images(
        mail: email.message.Message, images: list[email.mime.image.MIMEImage]
    ) -> email.message.Message:
        """Put ``images`` into a top-level ``multipart/related`` around ``mail``."""
        known = {p["Content-ID"] for p in mail.walk()}
        images = [i for i in images if i["Content-ID"] not in known]
        if not images:
            return mail
        if mail.get_content_type() == "multipart/related":
            related = mail
        else:
            related = email.mime.multipart.MIMEMultipart("related")
            # The MIME entity headers stay with the content, all others move to the envelope.
            moved = [(k, v) for k, v in mail.items() if not _is_entity_header(k)]
            for key, value in moved:
                related.add_header(key, value)
            for key in {k.lower() for k, _ in moved}:
                del mail[key]
            related.attach(mail)
        for image in images:
            related.attach(image)
        related.as_string()  # let MIMEMultipart pick a boundary
        return related

    def _replace_template_tags(
        self,
        action: models.Action,
        disclaimer_text: str,
        replacements: dict[str, Any],
        *,
        literal: Callable[[str], str] = _identity,
        escape: Callable[[str], str] = _identity,
    ) -> str | None:
        """Replace ``{key}`` and ``{key["subkey"]}`` tags in ``disclaimer_text``.

        Returns the substituted string, or ``None`` if the action should be
        skipped (template_fail and an unresolvable tag). See
        :func:`render_template` for the details.
        """
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
        self._pending_images = {}
        result = self._apply_action(copy.deepcopy(mail_parameter), action)
        if result is not None and self._pending_images:
            result = self._attach_images(result, list(self._pending_images.values()))
        return result

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
                    literal=self.make_html,
                    escape=self.make_html,
                )
            elif content_type == "text/html":
                replaced = self._replace_template_tags(
                    action, disclaimer_text, replacements, escape=escape_html_value
                )
            else:
                replaced = self._replace_template_tags(action, disclaimer_text, replacements)
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

        if content_type == "text/html" and action.action != constants.ACTION_ACTION_ADD:
            disclaimer_text = signature_html(action.disclaimer, disclaimer_text)

        if action.action == constants.ACTION_ACTION_REPLACETAG:
            new_text = re.sub(action.action_parameters, disclaimer_text, new_text)

        elif action.action == constants.ACTION_ACTION_ADD:
            if content_type == "text/plain":
                # Two blank lines keep the signature off the greeting ("Kind regards");
                # a signature that rendered empty adds no gap.
                if disclaimer_text.strip():
                    new_text = f"{new_text.rstrip()}\n\n\n{disclaimer_text}"
                else:
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
                # The <div> (with the signature's default font) gives bare text an element
                # to live in; two line breaks keep it off the greeting, as in plain text.
                gap = "<br /><br />" if disclaimer_text.strip() else ""
                disclaimer_text = signature_html(
                    action.disclaimer, gap + disclaimer_text, always=True
                )

                if not new_text.strip():
                    # lxml raises "Document is empty"; nothing to append to.
                    return mail
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
            for header in mail.keys():
                if not _is_entity_header(header):
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
        # Content-Transfer-Encoding header we add below). For 7bit / 8bit
        # we keep the payload as ``str`` so it gets written out
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
