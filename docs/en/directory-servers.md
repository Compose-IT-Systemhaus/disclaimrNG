# Directory servers

A **DirectoryServer** holds the connection details for one LDAP or
Active Directory backend. The milter pipeline binds against it to look
up the sender's contact data, which is then substituted into the
disclaimer template via ``{resolver["…"]}`` placeholders.

## Adding a directory server in the admin

**Settings → Directory servers → Add directory server**.

The form has four sections:

- **Identity** — name (display only), description, enabled flag,
  optional Tenant link.
- **Connection**
  - **Flavour** — *LDAP* (vanilla OpenLDAP/389DS), *Active Directory*,
    or *Custom*. Picking AD or LDAP fills in sensible defaults for
    the search query and attribute vocabulary; *Custom* leaves them
    blank.
  - **Hosts** — host name or IP address of the server, optionally with
    ``:port``, e.g. ``dc1.acme.com``. One per line; further lines are tried
    in order if the first does not answer. disclaimrNG builds the URL itself.
  - **Encrypt the connection (TLS)** — on by default: ``ldaps://``
    (port 636). Off: ``ldap://`` (port 389), and everything — including the
    bind password — travels unencrypted.
  - **Base DN** — e.g. ``dc=acme,dc=com``.
  - **CA certificate file** / **CA certificate** — only with TLS. Upload a
    PEM file (or paste the PEM text) of the CA that signed the server
    certificate. It is stored in the database and used for this server by
    the milter and the admin buttons. Empty: the container's CA store.
  - **Auth method** — *None* (anonymous bind) or *Simple* (DN +
    password).
  - **User-DN** / **Password** — only when auth is *Simple*.
- **Query**
  - **Search query** — a parameterised filter; ``%s`` is replaced
    with the sender's email at lookup time. AD default:
    ``(|(mail=%s)(userPrincipalName=%s))``. LDAP default: ``mail=%s``.
  - **Attribute vocabulary** — comma- or newline-separated list of
    attribute names exposed in the template editor's autocomplete
    (``cn, mail, telephoneNumber, …``). Leave empty to use the
    flavour defaults.
- **Cache** — milter-side query cache; on by default with a 1-hour
  TTL.

## Test-connection and discover-attributes buttons

In the change form (per server), two buttons live above the form:

- **Test connection** — binds to every configured URL and reports
  the per-URL outcome (``bind ok``, ``unreachable: …``, ``invalid
  credentials``, ``base DN not found``, ``ldap error: …``).
- **Discover attributes** — samples five real entries under the base
  DN and returns the union of attribute names found. Use the result
  to populate the *Attribute vocabulary* field.

Both buttons are admin-only and POST-only (CSRF-protected).

## Bootstrap from env vars

```dotenv
LDAP_SERVERS=acme_ad
LDAP_SERVER_ACME_AD_FLAVOR=ad
LDAP_SERVER_ACME_AD_BASE_DN=dc=acme,dc=com
LDAP_SERVER_ACME_AD_URL=ldaps://dc1.acme.com,ldaps://dc2.acme.com
LDAP_SERVER_ACME_AD_BIND_DN=CN=disclaimr,OU=Service,DC=acme,DC=com
LDAP_SERVER_ACME_AD_BIND_PASSWORD=change-me
LDAP_SERVER_ACME_AD_TENANT=acme   # links to the Acme tenant
```

Per handle (replace ``<HANDLE>`` with the uppercased handle):

| Variable | Default | Notes |
|---|---|---|
| ``LDAP_SERVER_<HANDLE>_NAME`` | handle, title-cased | |
| ``LDAP_SERVER_<HANDLE>_DESCRIPTION`` | empty | |
| ``LDAP_SERVER_<HANDLE>_FLAVOR`` | ``ldap`` | ``ldap`` / ``ad`` / ``custom`` |
| ``LDAP_SERVER_<HANDLE>_BASE_DN`` | **required** | |
| ``LDAP_SERVER_<HANDLE>_URL`` | **required** | Comma-separated for failover |
| ``LDAP_SERVER_<HANDLE>_BIND_DN`` | empty (anonymous) | |
| ``LDAP_SERVER_<HANDLE>_BIND_PASSWORD`` | empty | |
| ``LDAP_SERVER_<HANDLE>_SEARCH_QUERY`` | flavour default | |
| ``LDAP_SERVER_<HANDLE>_SEARCH_ATTRIBUTES`` | flavour default | |
| ``LDAP_SERVER_<HANDLE>_ENABLE_CACHE`` | ``true`` | |
| ``LDAP_SERVER_<HANDLE>_CACHE_TIMEOUT`` | 3600 | seconds |
| ``LDAP_SERVER_<HANDLE>_ENABLED`` | ``true`` | |
| ``LDAP_SERVER_<HANDLE>_TENANT`` | empty | Tenant slug to link to |

``manage.py sync_directory_servers`` runs on every web boot when
``LDAP_SERVERS`` is set. ``LDAP_SYNC_PRUNE=1`` deletes env-managed
rows that no longer appear.

## LDAPS with a private CA

``ldaps://`` URLs are verified against a CA certificate. The usual way is the
**CA certificate** field of the directory server (upload in the admin, see above): it
applies to that server only. For a CA that should apply to **every** directory server,
or when you bootstrap servers from environment variables, use the container's CA store:

1. Put the CA certificate (PEM, intermediates appended) at ``./certs/ad-ca.pem`` next to
   ``compose.yml``. The compose files mount ``./certs`` read-only into ``web`` and
   ``milter``.
2. Restart: ``docker compose up -d``. The entrypoint sees ``/etc/ssl/ad/ad-ca.pem`` and
   sets ``LDAPTLS_CACERT`` for the process; the log says ``LDAPS: trusting the CA``.
3. **Test connection** on the directory server must show ``bind + base search ok``.

An ``LDAPTLS_CACERT`` set in ``.env`` takes precedence. The file replaces the
system roots for LDAP connections, which is what you want for an internal directory.
Plain ``ldap://`` with STARTTLS is not supported — use ``ldaps://``.

## Bound timeouts

Every connection is opened with ``OPT_NETWORK_TIMEOUT=5`` and
``OPT_TIMEOUT=5`` so an unreachable LDAP server can never hang the
milter or the synchronous Signaturtest admin view for more than a few
seconds. Set these higher in
[``milter_helper.py``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/disclaimr/milter_helper.py)
if your LDAP genuinely needs more time.
