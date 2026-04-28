# Signatures, rules & the editor

The data model has three layers:

| Model | What it does |
|---|---|
| **Disclaimer** (a.k.a. *Signature*) | The actual signature text — plaintext, HTML, or both. |
| **Rule** | A bag of *requirements* + *actions*. If all requirements match, every enabled action runs. |
| **Requirement** | A regex filter — sender, recipient, header, body, sender IP. |
| **Action** | What to do when the rule matches: append a disclaimer, replace a tag, add a MIME part. |

A *Disclaimer* is just text; a *Rule* is what wires it to a particular
class of mails; an *Action* is the concrete operation (typically:
"append this disclaimer to the body").

## The template editor

Reachable via **Signatures → Manage signatures → Add / edit**. Three
tabs share one underlying textarea so you never lose edits:

- **Code** — Monaco editor with HTML or plaintext syntax highlighting
  and autocomplete for ``{resolver["…"]}`` placeholders.
- **Visual** — TinyMCE WYSIWYG (only on the HTML field).
- **Preview** — server-rendered preview iframe with sample
  ``{sender}``, ``{recipient}`` and a few resolver attributes filled
  in, so you can see what the disclaimer will look like.

### Placeholder chips

Underneath the editor: clickable pills you can use to insert
placeholders at the cursor.

- **Envelope** — ``{sender}``, ``{recipient}``
- **Header** — ``{header["subject"]}``, ``{header["from"]}``, …
- **Common fields** — ``Name``, ``Phone``, ``Email``, ``Address``
  (mapped to the canonical LDAP attributes ``cn``, ``telephoneNumber``,
  ``mail``, ``streetAddress`` so you don't have to remember which one
  to use).
- **Verzeichnis-Attribute** — every attribute the configured
  DirectoryServers have advertised via the vocabulary endpoint.

Click a chip → the placeholder is inserted at the active editor's
cursor. Switching tabs syncs the underlying textarea.

### Image picker

Below the chips, a thumbnail grid of every uploaded ``SignatureImage``.
Click a thumbnail to insert ``{image["slug"]}`` at the cursor.

The **+ Hochladen** button accepts a file directly and creates a new
``SignatureImage`` row on the spot — the slug is derived from the
filename (with a numeric suffix on collision). Images live in the
``media`` Docker volume and are served from ``MEDIA_BASE_URL``.

## Placeholder reference

| Token | Resolves to |
|---|---|
| ``{sender}`` | The envelope-from address |
| ``{recipient}`` | The envelope-to address |
| ``{header["X"]}`` | The value of mail header ``X`` (case-insensitive on the key) |
| ``{resolver["attr"]}`` | The LDAP attribute ``attr`` of the sender entry |
| ``{image["slug"]}`` | An ``<img>`` tag (HTML disclaimer) or a bare URL (plaintext) for the SignatureImage with the given slug |

### "Resolver tag" wrappers

Wrap a chunk that should disappear if its resolver tag is unresolvable
in ``{rt}…{/rt}``:

```text
Best regards,
{resolver["cn"]}
{rt}Phone: {resolver["telephoneNumber"]}{/rt}
```

If the sender has no ``telephoneNumber`` in LDAP, the whole "Phone:"
line drops out instead of leaving a literal ``{resolver["…"]}`` in
the rendered mail.

### Failure mode

If the disclaimer's **Fail if template doesn't exist** option is on
and any resolver tag can't be filled, the action is **skipped** —
the mail leaves the milter unchanged. Use this for high-stakes
signatures where leaving an empty placeholder would be worse than
leaving the mail untouched.

## Rules and actions

A **Rule** is a container; the actual filtering happens in its
**Requirement** inlines. Default values are wide open
(``.*`` / ``0.0.0.0/0``), so a rule with one default Requirement and
one Action will fire on every mail.

Tighten the requirement to scope the rule:

- **Sender** — regex against the envelope-from. ``.*@acme\.com`` only
  matches mail from ``acme.com``.
- **Recipient** — regex against the envelope-to.
- **Header filter** — regex against every header line joined with
  newlines.
- **Body filter** — regex against the message body.
- **Sender-IP** — IP / CIDR of the sending host.

Each Requirement also has an **Action** field of *Accept* or *Deny*.
A *Deny* requirement short-circuits the whole rule for that mail.

The **Action** inline picks the disclaimer and how to merge it:

- **Add a disclaimer string to the body** — appends to the existing
  body. For HTML mails the disclaimer is parsed and inserted before
  ``</body>``.
- **Replace a tag in the body with a disclaimer string** — handy for
  templates where the user puts a literal ``#DISCLAIMER#`` placeholder
  in their drafted mail.
- **Add the disclaimer using an additional MIME part** — wraps the
  original mail in ``multipart/mixed`` and attaches the disclaimer
  as a separate part. Useful when the original mail is binary or
  signed.

If the action's **Resolve sender** flag is on, the milter queries the
linked DirectoryServers (or the tenant's, see
[Tenants](../tenants/)) before substituting placeholders.

## Testing a rule before deploying it

Use **Signatures → Signature test** to play arbitrary mails through
the **live** rule pipeline without involving Postfix. Form fields:

- Sender / Recipient / Subject / Sender-IP / Content-Type / Body

The result panel shows:

- a banner saying which rule(s) matched,
- the **modified body** (rendered HTML for ``text/html``, plain
  ``<pre>`` for ``text/plain``),
- the workflow's add/change/delete header diff,
- the full RFC 822 mail after the pipeline,
- a collapsible view of the input mail.
