# Configuration

All runtime configuration is driven by environment variables (12-factor
style). Templates, rules, requirements and directory servers themselves
live in PostgreSQL and are managed via the admin.

## First-boot admin user

The web container's entrypoint runs ``manage.py bootstrap_admin`` after
``migrate``:

- if **any** superuser exists already, it does nothing,
- otherwise creates ``admin`` with a freshly generated 24-character
  ``secrets.token_urlsafe`` password.

The password is printed inside a banner so it's easy to grep out of
``docker compose logs web``:

```
========================================================================
[bootstrap_admin] superuser 'admin' created.
[bootstrap_admin] one-time password: a8ghNZI8UN7kX84z0EPOS-pI
[bootstrap_admin] log in and change it at /admin/password_change/
========================================================================
```

Forgot to copy it on first boot? Run:

```bash
docker compose exec web python manage.py bootstrap_admin --reset
```

This forcibly recreates ``admin`` with a fresh password, even if other
superusers exist.

## Django settings worth knowing

| Setting | Purpose |
|---|---|
| ``DJANGO_DEBUG`` | Always ``False`` in production. ``True`` only for local dev — exposes tracebacks. |
| ``DJANGO_LOG_LEVEL`` | ``INFO`` by default; set to ``DEBUG`` if you need to trace milter decisions. |
| ``DJANGO_TIME_ZONE`` | All timestamps and the admin date pickers use this. Defaults to ``Europe/Berlin``. |
| ``DJANGO_LANGUAGE_CODE`` | Default UI language; admins can flip via the topbar flag toggle. |

## Static files

Served by [WhiteNoise](https://whitenoise.evans.io) directly out of
gunicorn — no separate nginx required. ``collectstatic`` runs on every
boot.

The template editor's vendored Monaco / TinyMCE assets are loaded from
**jsdelivr** (pinned versions, see
[``template_editor.js``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/disclaimrwebadmin/static/disclaimrwebadmin/template_editor/template_editor.js)).
Self-hosting them is tracked as a follow-up; for now the admin needs
internet access to load the editor.

## Media uploads (signature images)

Set ``MEDIA_BASE_URL`` to the **public** absolute URL prefix, e.g.
``https://signatures.example.com``. Mails fly through MTAs that don't
know about your private network — relative URLs are useless.

```dotenv
# .env
MEDIA_BASE_URL=https://signatures.example.com
```

The default compose stack stores uploaded images in a Docker named
volume. To bind-mount a host directory instead (for backups), set:

```dotenv
MEDIA_HOST_PATH=/srv/disclaimrng/media
```

## Bootstrapping tenants and LDAP servers from env vars

Both can be declared declaratively, useful for declarative deployments
(Compose, Helm, Ansible). See:

- [Tenants](../tenants/) for the ``TENANTS=...`` schema
- [Directory servers](../directory-servers/) for the ``LDAP_SERVERS=...`` schema

Both ``manage.py sync_tenants`` and ``manage.py sync_directory_servers``
run automatically on every web container boot when the corresponding
env var is set. Set ``TENANT_SYNC_PRUNE=1`` / ``LDAP_SYNC_PRUNE=1`` to
delete env-managed rows that have disappeared from the env (manually
created rows are never touched — they're recognised by a ``[env-managed]``
description marker).
