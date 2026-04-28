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
  - **Base DN** — e.g. ``dc=acme,dc=com``.
  - **Auth method** — *None* (anonymous bind) or *Simple* (DN +
    password).
  - **User-DN** / **Password** — only when auth is *Simple*.
- **Query**
  - **Search query** — a parameterised filter; ``%s`` is replaced
    with the sender's email at lookup time. AD default:
    ``(userPrincipalName=%s)``. LDAP default: ``mail=%s``.
  - **Attribute vocabulary** — comma- or newline-separated list of
    attribute names exposed in the template editor's autocomplete
    (``cn, mail, telephoneNumber, …``). Leave empty to use the
    flavour defaults.
- **Cache** — milter-side query cache; on by default with a 1-hour
  TTL.

Add at least one **URL** in the inline at the bottom — e.g.
``ldaps://dc1.acme.com``. Multiple URLs are tried in order on
failure for HA.

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

## Bound timeouts

Every connection is opened with ``OPT_NETWORK_TIMEOUT=5`` and
``OPT_TIMEOUT=5`` so an unreachable LDAP server can never hang the
milter or the synchronous Signaturtest admin view for more than a few
seconds. Set these higher in
[``milter_helper.py``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/disclaimr/milter_helper.py)
if your LDAP genuinely needs more time.
