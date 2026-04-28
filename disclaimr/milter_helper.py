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
import logging
import quopri
import re
from typing import Any

import ldap
from lxml import etree

from disclaimr.query_cache import QueryCache
from disclaimrwebadmin import constants, models

syslog = logging.getLogger("disclaimr")

# Tag like {key} but not the {rt}/{/rt} wrapper itself.
_TEMPLATE_TAG_RE = re.compile(r"\{((?!rt|/rt)[^}]*)\}")
# Subkey form: key["subkey"].
_SUBKEY_TAG_RE = re.compile(r'^([^\[]*)\["([^"]*)"\]$')


def _to_str(value: Any, charset: str = "utf-8") -> str:
    """Decode bytes (LDAP attribute values, body chunks) to str."""
    if isinstance(value, bytes):
        try:
            return value.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return value.decode("utf-8", errors="replace")
    return value


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
            attrs = [f'src="{absolute_url}"']
            alt = image.alt_text or image.name
            attrs.append(f'alt="{alt}"')
            if image.width:
                attrs.append(f'width="{image.width}"')
            if image.height:
                attrs.append(f'height="{image.height}"')
            rendered[image.slug.lower()] = f"<img {' '.join(attrs)} />"
        else:
            rendered[image.slug.lower()] = absolute_url
    return rendered


class MilterHelper:
    """Stateful helper that processes a single mail through the milter pipeline."""

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

    def connect(self, hostname: str, family: int, ip: str, port: int, cmd_dict: dict) -> None:
        """Called when a client connects to the milter."""
        self.mail_data["sender_ip"] = ip

        for sender_ip in self.configuration["sender_ip"]:
            if ip in sender_ip["ip"]:
                logging.debug("Found IP in a requirement.")
                if sender_ip["id"] not in self.requirements:
                    self.requirements.append(sender_ip["id"])

        if not self.requirements:
            logging.debug("Couldn't find the IP in any requirement. Skipping.")
            self.enabled = False

    def mail_from(self, addr: str, cmd_dict: dict) -> None:
        """Called when the MAIL FROM envelope value has been received."""
        for req in models.Requirement.objects.filter(id__in=self.requirements):
            if not re.search(req.sender, addr):
                self.requirements = [r for r in self.requirements if r != req.id]

        if not self.requirements:
            logging.debug("Couldn't match sender address in any requirement. Skipping.")
            self.enabled = False

        self.mail_data["envelope_from"] = addr

    def rcpt(self, recip: str, cmd_dict: dict) -> None:
        """Called when an RCPT TO envelope value has been received."""
        for req in models.Requirement.objects.filter(id__in=self.requirements):
            if not re.search(req.recipient, recip):
                self.requirements = [r for r in self.requirements if r != req.id]
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
        for req in models.Requirement.objects.filter(id__in=self.requirements):
            if not re.search(req.header, joined):
                self.requirements = [r for r in self.requirements if r != req.id]

        if not self.requirements:
            logging.debug("Couldn't match header in any requirement. Skipping.")
            self.enabled = False

    def body(self, chunk: bytes | str, cmd_dict: dict) -> None:
        """Called for each body chunk."""
        # Body chunks come in as bytes from libmilter — normalise to str so the
        # downstream regex/email machinery has something stable to work with.
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        self.mail_data["body"] += chunk

    def eob(self, cmd_dict: dict) -> dict[str, Any] | None:
        """Called once the entire body has been received.

        Returns the workflow dictionary that the milter applies to the mail
        (replace body, add/change/delete headers).
        """
        for req in models.Requirement.objects.filter(id__in=self.requirements):
            if not re.search(req.body, self.mail_data["body"]):
                self.requirements = [r for r in self.requirements if r != req.id]

        if not self.requirements:
            logging.debug("Couldn't match body in any requirement. Skipping.")
            self.enabled = False
            return None

        rules_blacklist: list[int] = []
        rules: list[int] = []
        for req in models.Requirement.objects.filter(id__in=self.requirements):
            if req.action == constants.REQ_ACTION_DENY:
                rules_blacklist.append(req.rule.id)
            if req.rule.id not in rules_blacklist and req.rule.id not in rules:
                rules.append(req.rule.id)

        rules = [r for r in rules if r not in rules_blacklist]

        if not rules:
            self.enabled = False
            return None

        mail = email.message_from_string(
            "{}\n{}".format("\n".join(self.mail_data["headers"]), self.mail_data["body"])
        )
        orig_mail = copy.deepcopy(mail)

        for rule in models.Rule.objects.filter(id__in=rules):
            for action in rule.action_set.all():
                if not action.enabled:
                    continue
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
            if header not in orig_mail.keys():
                workflow.setdefault("add_header", {})[header] = orig_mail[header]
            elif mail[header] != orig_mail[header]:
                workflow.setdefault("change_header", {})[header] = mail[header]

        for header in orig_mail.keys():
            if header not in mail.keys():
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
        text = re.sub("\r\n", "\n", text)
        html_escape_table = {
            "&": "&amp;",
            '"': "&quot;",
            "'": "&apos;",
            ">": "&gt;",
            "<": "&lt;",
        }
        text = "".join(html_escape_table.get(c, c) for c in text)
        return re.sub("\n", "<br />", text)

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

    def _resolve_sender(
        self, action: models.Action, replacements: dict[str, Any]
    ) -> bool:
        """Populate ``replacements['resolver']`` from configured directory servers.

        Returns whether at least one directory server delivered a result.
        """
        resolved_successfully = False
        envelope_from = self.mail_data["envelope_from"]

        for directory_server in self._directory_servers_for(action, envelope_from):
            if not directory_server.enabled:
                logging.debug(
                    "Directory server %s is disabled. Skipping.", directory_server.name
                )
                continue

            logging.debug("Connecting to directory server %s", directory_server.name)
            query = directory_server.search_query % (envelope_from,)
            result = None

            if directory_server.enable_cache:
                result = QueryCache.get(directory_server, query)
                if result is not None:
                    resolved_successfully = True

            if result is None:
                for url in directory_server.directoryserverurl_set.all():
                    logging.debug("Trying url %s", url.url)
                    conn = ldap.initialize(url.url)
                    # Bound, network-level timeouts so an unreachable LDAP
                    # server can never hang the milter (or the synchronous
                    # signature-test admin view) for more than a few
                    # seconds. python-ldap's defaults are effectively
                    # infinite, which used to take down gunicorn workers.
                    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
                    conn.set_option(ldap.OPT_TIMEOUT, 5)

                    ldap_user = ""
                    ldap_password = ""
                    if directory_server.auth == constants.DIR_AUTH_SIMPLE:
                        ldap_user = directory_server.userdn
                        ldap_password = directory_server.password

                    try:
                        conn.simple_bind_s(ldap_user, ldap_password)
                    except ldap.SERVER_DOWN:
                        syslog.warning("Cannot reach server %s. Skipping.", url)
                        continue
                    except ldap.TIMEOUT:
                        syslog.warning(
                            "Timeout binding to server %s. Skipping.", url
                        )
                        continue
                    except (ldap.INVALID_CREDENTIALS, ldap.INVALID_DN_SYNTAX):
                        syslog.warning(
                            "Cannot authenticate to directory server %s with dn %s. "
                            "Skipping.",
                            url,
                            directory_server.userdn,
                        )
                        continue

                    try:
                        result = conn.search_s(
                            directory_server.base_dn, ldap.SCOPE_SUBTREE, query
                        )
                    except ldap.SERVER_DOWN:
                        syslog.warning("Cannot reach server %s. Skipping.", url)
                        continue
                    except ldap.TIMEOUT:
                        syslog.warning(
                            "Timeout searching server %s. Skipping.", url
                        )
                        continue
                    except (ldap.INVALID_CREDENTIALS, ldap.NO_SUCH_OBJECT):
                        syslog.warning(
                            "Cannot authenticate to directory server %s as guest or "
                            "cannot query. Skipping.",
                            url,
                        )
                        continue

                    if not result:
                        if action.resolve_sender_fail:
                            syslog.warning(
                                "Cannot resolve email %s. Skipping", envelope_from
                            )
                            return False
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
                            return False

                    logging.debug("Found entry %s", result[0][0])

                    if directory_server.enable_cache:
                        QueryCache.set(directory_server, query, result)

                    resolved_successfully = True
                    break

            if result is not None and len(result) == 1:
                # Flatten the LDAP result into the replacement dict. python-ldap
                # returns attribute values as bytes; decode them before use.
                attrs = result[0][1]
                for key in attrs.keys():
                    raw_values = attrs[key]
                    try:
                        joined = ",".join(_to_str(v) for v in raw_values)
                        replacements["resolver"][key.lower()] = joined
                    except UnicodeDecodeError:
                        # Binary attribute (e.g. thumbnailPhoto) — base64-encode it.
                        joined_bytes = b"".join(raw_values)
                        replacements["resolver"][key.lower()] = base64.b64encode(
                            joined_bytes
                        ).decode("ascii")

        return resolved_successfully

    def _replace_template_tags(
        self,
        action: models.Action,
        disclaimer_text: str,
        replacements: dict[str, Any],
        charset: str,
    ) -> str | None:
        """Replace ``{key}`` and ``{key["subkey"]}`` tags in ``disclaimer_text``.

        Returns the substituted string, or ``None`` if the action should be
        skipped (template_fail and an unresolvable tag).
        """
        while True:
            match = _TEMPLATE_TAG_RE.search(disclaimer_text)
            if not match:
                break

            key = match.groups()[0].lower()
            replace_key = match.groups()[0]
            logging.debug("Replacing key %s", key)

            dictmatch = _SUBKEY_TAG_RE.search(key)
            subkey: str | None = None
            value: str = ""

            if dictmatch:
                key = dictmatch.groups()[0].lower()
                subkey = dictmatch.groups()[1].lower()

                if key in replacements and subkey in replacements[key]:
                    value = replacements[key][subkey]
                elif action.disclaimer.template_fail:
                    syslog.warning("Cannot resolve key %s. Skipping", key)
                    return None
                else:
                    logging.debug(
                        "Cannot resolve '%s' for '%s'",
                        subkey,
                        self.mail_data["envelope_from"],
                    )
            else:
                if key in replacements:
                    value = replacements[key]
                elif action.disclaimer.template_fail:
                    syslog.warning("Cannot resolve key %s. Skipping", key)
                    return None
                else:
                    logging.debug(
                        "Cannot resolve '%s' for '%s'",
                        key,
                        self.mail_data["envelope_from"],
                    )

            if len(value) > 0:
                # If the disclaimer wraps the resolver tag in {rt}…{/rt}, keep
                # the surrounding text and just drop the marker.
                removetag = None
                if subkey:
                    removetag = re.search(
                        r'{rt}(.*)({resolver\["' + subkey + r'"\]})(.*){/rt}',
                        disclaimer_text,
                        re.IGNORECASE,
                    )
                if removetag:
                    logging.debug("Cleaning tag up...")
                    replace_key = (
                        "rt}"
                        + removetag.groups()[0]
                        + removetag.groups()[1]
                        + removetag.groups()[2]
                        + "{/rt"
                    )
                    value = removetag.groups()[0] + value + removetag.groups()[2]

                disclaimer_text = disclaimer_text.replace(
                    f"{{{replace_key}}}", value
                )
            else:
                # No value: drop the whole {rt}…{/rt} block (or just the tag).
                if subkey:
                    remove = re.search(
                        r'(\n)?{rt}.*{resolver\["'
                        + subkey
                        + r'"\]}.*{/rt}(\r|<br />)?|{resolver\["'
                        + subkey
                        + r'"\]}',
                        disclaimer_text,
                        re.IGNORECASE,
                    )
                    if remove:
                        logging.debug("Removing tag...")
                        disclaimer_text = (
                            disclaimer_text[: remove.start()] + disclaimer_text[remove.end():]
                        )
                else:
                    disclaimer_text = disclaimer_text.replace(f"{{{replace_key}}}", "")

        del charset  # currently unused; kept for API stability with the old code
        return disclaimer_text

    def do_action(
        self, mail_parameter: email.message.Message, action: models.Action
    ) -> email.message.Message | None:
        """Apply ``action`` to ``mail_parameter`` (recursing into MIME parts)."""
        mail = copy.deepcopy(mail_parameter)

        if mail.is_multipart():
            new_payloads = []
            for payload in mail.get_payload():
                returned_mail = self.do_action(payload, action)
                if returned_mail is not None:
                    new_payloads.append(returned_mail)
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
                "image": _build_image_replacements(disclaimer_text, content_type),
            }

            if action.resolve_sender:
                resolved_successfully = self._resolve_sender(action, replacements)
                if not resolved_successfully and action.resolve_sender_fail:
                    syslog.warning(
                        "Cannot resolve email %s. Skipping",
                        self.mail_data["envelope_from"],
                    )
                    return None

            replaced = self._replace_template_tags(
                action, disclaimer_text, replacements, charset
            )
            if replaced is None:
                return None
            disclaimer_text = replaced

        if content_type == "text/html" and action.disclaimer.html_use_text:
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
                html_part = etree.HTML(new_text)
                disclaimer_part = etree.HTML(disclaimer_text)
                disclaimer_body = disclaimer_part.xpath("body")[0]

                if html_part.xpath("body"):
                    for element in disclaimer_body:
                        html_part.xpath("body")[0].append(element)
                else:
                    for element in disclaimer_body:
                        html_part.append(element)

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
