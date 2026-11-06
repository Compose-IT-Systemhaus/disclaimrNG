#!/usr/bin/env python3
"""End-to-end test: a mail through Postfix gets its signature from the real milter.

Needs the stack from ``tests/e2e/compose.e2e.yml`` (see there) and runs from the
repository root. Standard library only. What it checks:

* Postfix really consults the milter and relays the changed mail (the mail sink sees the
  signature, with data looked up in LDAP).
* The replacement body keeps consistent CRLF line endings.
* A time-limited action outside its window is skipped, one inside it is applied.
* The mail log records the mail.
* LDAPS: without the CA certificate the lookup fails (the mail is still delivered, without
  directory data), with the CA stored on the directory server it works.
* Directory conditions: rules that demand a group membership (memberOf of the test LDAP) or an
  attribute value of the sender apply or not accordingly.
* An image flagged "embed" ends up in the HTML mail as an inline ``cid:`` part (the milter
  reads the file from the shared media volume).
"""

from __future__ import annotations

import email
import email.policy
import json
import re
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.request
from email.message import EmailMessage

COMPOSE = ["docker", "compose", "-f", "compose.yml", "-f", "tests/e2e/compose.e2e.yml"]
SMTP_ADDRESS = ("127.0.0.1", 2525)
MAILPIT = "http://127.0.0.1:8025"
SENDER = "professor@planetexpress.com"  # exists in the test LDAP
failures: list[str] = []


def django(code: str, **env: str) -> str:
    """Run Python code with Django set up inside the web container; return its output."""
    args = [*COMPOSE, "exec", "-T"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    result = subprocess.run(
        [*args, "web", "python", "manage.py", "shell", "-v", "0", "-c", code],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(f"django shell failed:\n{result.stdout}\n{result.stderr}")
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def wait_for(what: str, probe, timeout: int = 180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001 — services are still starting
            last = exc
        time.sleep(3)
    raise SystemExit(f"timed out waiting for {what} (last error: {last})")


def mailpit(path: str, method: str = "GET") -> bytes:
    request = urllib.request.Request(f"{MAILPIT}{path}", method=method)  # noqa: S310
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return response.read()


def send(subject: str, html: str | None = None) -> None:
    message = EmailMessage()
    message["From"] = SENDER
    message["To"] = "bob@example.org"
    message["Subject"] = subject
    if html:
        message.set_content(html, subtype="html")
    else:
        message.set_content("Hello Zoidberg\nSecond line\n")

    def attempt():
        # A 4xx while the milter or Postfix are still coming up: try again.
        with smtplib.SMTP(*SMTP_ADDRESS, timeout=30) as smtp:
            smtp.send_message(message)
        return True

    wait_for("Postfix to accept the mail", attempt, timeout=120)


def receive(subject: str) -> str:
    def find():
        for item in json.loads(mailpit("/api/v1/messages"))["messages"]:
            if item["Subject"] == subject:
                return item["ID"]
        return None

    message_id = wait_for(f"the mail {subject!r} at the sink", find, timeout=90)
    return mailpit(f"/api/v1/message/{message_id}/raw").decode("utf-8")


def check(condition: bool, message: str, raw: str = "") -> None:
    print(("  ok    " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)
        if raw:
            print("--- mail as received ---\n" + raw + "--- end ---")


def scenario(title: str, subject: str, *, signature_has_data: bool) -> str:
    print(f"\n{title}")
    send(subject)
    raw = receive(subject)
    check("Hello Zoidberg" in raw, "original text is kept", raw)
    expected = "Sent by Professor Farnsworth" if signature_has_data else "Sent by"
    check(expected in raw, f"signature contains {expected!r}", raw)
    check(
        ("Professor Farnsworth" in raw) == signature_has_data,
        "directory data " + ("is" if signature_has_data else "is NOT") + " in the mail",
        raw,
    )
    check("CURRENT-BANNER" in raw, "banner inside its validity window is added", raw)
    check("OLD-BANNER" not in raw, "banner outside its window is skipped", raw)
    check(re.search(r"(?<!\r)\n", raw) is None, "line endings are CRLF only", raw)
    return raw


SEED = """
from datetime import timedelta
from django.utils import timezone
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import Action, Disclaimer, Requirement, Rule

now = timezone.now()
rule = Rule.objects.create(name="E2E")
Requirement.objects.create(rule=rule, name="any mail")

def add(position, name, text, **kwargs):
    disclaimer = Disclaimer.objects.create(name=name, text=text, text_use_template=True)
    Action.objects.create(rule=rule, disclaimer=disclaimer, position=position, name=name,
                          action=constants.ACTION_ACTION_ADD, **kwargs)

add(0, "Signature", '--\\nSent by {resolver["displayName"]}\\n', resolve_sender=True)
add(1, "Old banner", "OLD-BANNER", valid_until=now - timedelta(days=1))
add(2, "Current banner", "CURRENT-BANNER",
    valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1))
print("seeded")
"""

LDAP_READY = """
from disclaimr.ldap_helper import test_connection
from disclaimrwebadmin.models import DirectoryServer
print("ready" if test_connection(DirectoryServer.objects.get(name="Planetexpress")).ok else "")
"""

SWITCH_TO_TLS = """
import os
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import DirectoryServer, DirectoryServerURL

plain = DirectoryServer.objects.get(name="Planetexpress")
DirectoryServer.objects.filter(pk=plain.pk).update(enabled=False)
tls = DirectoryServer.objects.create(
    name="Planetexpress TLS", tenant=plain.tenant, flavor=constants.DIR_FLAVOR_LDAP,
    base_dn=plain.base_dn, auth=constants.DIR_AUTH_SIMPLE, userdn=plain.userdn,
    password=plain.password, use_tls=True, enable_cache=False,
)
DirectoryServerURL.objects.create(
    directory_server=tls, url="ldaps://planetexpress.com:10636", position=0
)
print("switched")
"""

STORE_CA = """
import os
from disclaimrwebadmin.models import DirectoryServer
DirectoryServer.objects.filter(name="Planetexpress TLS").update(ca_certificate=os.environ["CA_PEM"])
print("stored")
"""

EMBED_SEED = """
import io
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import Action, Disclaimer, Rule, SignatureImage

buf = io.BytesIO()
Image.new("RGB", (2, 2), color="red").save(buf, format="PNG")
SignatureImage.objects.create(
    slug="logo", name="Logo", embed=True,
    image=SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png"),
)
disclaimer = Disclaimer.objects.create(
    name="Logo", html_use_text=False, html='<p>EMBED-LOGO {image["logo"]}</p>', html_use_template=True,
)
Action.objects.create(rule=Rule.objects.get(name="E2E"), disclaimer=disclaimer, position=3,
                      name="Logo", action=constants.ACTION_ACTION_ADD)
print(buf.getvalue().hex())
"""

CONDITION_SEED = """
from disclaimrwebadmin import constants
from disclaimrwebadmin.models import Action, Disclaimer, Requirement, Rule

Rule.objects.update(continue_rules=True)

def conditional(name, text, **condition):
    rule = Rule.objects.create(name=name, continue_rules=True)
    requirement = Requirement.objects.create(rule=rule, name=name)
    requirement.conditions.create(**condition)
    disclaimer = Disclaimer.objects.create(name=name, text=text)
    Action.objects.create(rule=rule, disclaimer=disclaimer, position=0, name=name,
                          action=constants.ACTION_ACTION_ADD)

people = "ou=people,dc=planetexpress,dc=com"
group = constants.COND_KIND_GROUP
conditional("Staff", "GROUP-STAFF", kind=group, group_dn="cn=admin_staff," + people)
conditional("Crew", "GROUP-CREW", kind=group, group_dn="cn=ship_crew," + people)
conditional("Owner", "ATTR-OWNER", attribute="employeeType", pattern="^Owner$")
conditional("Intern", "ATTR-INTERN", attribute="employeeType", pattern="^Intern$")
print("seeded")
"""

LOG_CHECK = """
from disclaimrwebadmin.models import MailLog
print(MailLog.objects.filter(processed=True, applied__contains="E2E → Signature → Signature").count())
"""


def main() -> int:
    print("waiting for the LDAP server")
    wait_for("the test LDAP", lambda: django(LDAP_READY) == "ready")
    print(django(SEED))
    time.sleep(3)  # the milter reloads its prefilter every second (MILTER_CONFIG_TTL)

    scenario("Plain LDAP", "e2e plain", signature_has_data=True)

    logged = int(django(LOG_CHECK))
    check(logged >= 1, f"the mail log has the processed mail ({logged} entries)")

    print("\nSwitching to LDAPS without a CA certificate")
    print(django(SWITCH_TO_TLS))
    scenario("LDAPS, CA not trusted", "e2e tls without ca", signature_has_data=False)

    print("\nStoring the server's CA certificate on the directory server")
    pem = ssl.get_server_certificate(("127.0.0.1", 10636))
    print(django(STORE_CA, CA_PEM=pem))
    scenario("LDAPS with the stored CA", "e2e tls with ca", signature_has_data=True)

    print("\nDirectory conditions")
    print(django(CONDITION_SEED))
    time.sleep(3)
    send("e2e conditions")
    raw = receive("e2e conditions")
    check("GROUP-STAFF" in raw, "member of admin_staff: the group rule applies", raw)
    check("GROUP-CREW" not in raw, "not a member of ship_crew: the group rule is skipped", raw)
    check("ATTR-OWNER" in raw, "employeeType Owner: the attribute rule applies", raw)
    check("ATTR-INTERN" not in raw, "employeeType is not Intern: the attribute rule is skipped", raw)

    print("\nEmbedded image")
    png = bytes.fromhex(django(EMBED_SEED))
    time.sleep(3)
    send("e2e embed", html="<p>Hello Zoidberg</p>")
    raw = receive("e2e embed")
    mail = email.message_from_string(raw, policy=email.policy.default)
    check(mail.get_content_type() == "multipart/related", "mail is multipart/related", raw)
    parts = list(mail.iter_parts()) if mail.is_multipart() else []
    page = next((p for p in parts if p.get_content_type() == "text/html"), None)
    image = next((p for p in parts if p.get_content_type() == "image/png"), None)
    check(page is not None and image is not None, "has an HTML part and an image part", raw)
    if page is not None and image is not None:
        cid = image["Content-ID"].strip("<>")
        check(f"cid:{cid}" in page.get_content(), "the HTML references the image by cid", raw)
        check("EMBED-LOGO" in page.get_content(), "the disclaimer text is in the HTML", raw)
        check(image.get_content() == png, "the image bytes arrive unchanged", raw)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
