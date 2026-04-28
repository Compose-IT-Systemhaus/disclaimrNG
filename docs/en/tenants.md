# Tenants

A **Tenant** is a logical mandant — typically one customer of yours,
or one division within your own company. Each tenant bundles:

- one or more **sender domains** (e.g. ``acme.com``, ``acme.de``),
- the **directory servers** that hold the contact data for those
  domains (LDAP or Active Directory),
- the **signatures** (and their rules) that should apply to mail
  leaving those domains.

Multi-tenancy is **additive** — you can run disclaimrNG with no
tenants at all and configure everything globally. The links from
DirectoryServer / Disclaimer / Rule to Tenant are nullable and use
``ON DELETE SET NULL``.

## How the milter resolves a tenant

When the milter pipeline needs to query LDAP for the sender of a mail,
it picks directory servers in this order:

1. The **explicit** ``directory_servers`` linked to the matching
   ``Action`` (configured per-rule in the admin).
2. If that's empty, the directory servers belonging to the tenant
   whose domain owns the sender's email address.

So in the common case ("one tenant per customer, one LDAP per tenant")
you never need to attach LDAP servers to individual actions — just
link them to the tenant once and the milter figures it out.

## Adding a tenant in the admin

1. **Settings → Tenants → Add tenant** in the sidebar.
2. **Name** is whatever you want to see in the dashboard (e.g.
   "Acme Corp").
3. **Slug** is filled in from the name automatically; it's used for
   API URLs and as the lookup key when env-bootstrapping.
4. Add one or more **Tenant domains** in the inline at the bottom
   (e.g. ``acme.com``, ``acme.de``). Domains are matched
   **case-insensitively** against the *right-hand side* of the
   envelope-from address.
5. Save.
6. Now go to **Settings → Directory servers** and edit (or add) the
   LDAP/AD server for this tenant. Set its **Tenant** field to the
   tenant you just created.

## Bootstrap from env vars

Useful for declarative deployments. Add to your ``.env``:

```dotenv
TENANTS=acme,globex
TENANT_ACME_NAME=Acme Corp
TENANT_ACME_DOMAINS=acme.com,acme.de
TENANT_GLOBEX_NAME=Globex
TENANT_GLOBEX_DOMAINS=globex.com
```

Per handle (replace ``<HANDLE>`` with the uppercased name from
``TENANTS``):

| Variable | Default | Notes |
|---|---|---|
| ``TENANT_<HANDLE>_NAME`` | handle, title-cased | Display name |
| ``TENANT_<HANDLE>_DESCRIPTION`` | empty | Free-form |
| ``TENANT_<HANDLE>_DOMAINS`` | **required** | Comma-separated sender domains |
| ``TENANT_<HANDLE>_ENABLED`` | ``true`` | ``false`` skips the tenant during sender resolution |

The web container's entrypoint runs ``manage.py sync_tenants`` on every
boot when ``TENANTS`` is set. Add ``TENANT_SYNC_PRUNE=1`` to delete
env-managed tenants that no longer appear in ``TENANTS``.

To wire a directory server to a tenant via env, add
``LDAP_SERVER_<HANDLE>_TENANT=<slug>`` to the matching
``LDAP_SERVER_*`` block — see [Directory servers](../directory-servers/).
