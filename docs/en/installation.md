# Installation

disclaimrNG ships as a Docker Compose stack with three services:

- **db** — PostgreSQL 16 (named volume ``pgdata``)
- **web** — Django admin + the API endpoints used by the milter
- **milter** — libmilter daemon listening on TCP 5000

## Quickstart

```bash
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git
cd disclaimrNG
cp .env.example .env
# edit .env — at minimum set DJANGO_SECRET_KEY, POSTGRES_PASSWORD,
# and add your hostname/IP to DJANGO_ALLOWED_HOSTS
docker compose up -d
```

The first boot:

- runs all migrations,
- creates the admin user (see the **`docker compose logs web`** output
  for the one-time password — banner format
  ``[bootstrap_admin] one-time password: <pw>``),
- runs ``collectstatic``,
- starts gunicorn on port 8000 and the milter on port 5000.

Browse to ``http://<your-host>:8000/`` and log in as ``admin`` with the
generated password. Change it via ``/admin/password_change/``
immediately.

## Reverse proxy with Traefik

A self-contained alternative compose file is bundled at
[``compose.traefik.yml``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/compose.traefik.yml).
It puts the web UI behind Traefik with automatic Let's Encrypt
certificates. Start it instead of the default compose:

```bash
# Add to .env:
DISCLAIMR_HOSTNAME=signatures.example.com
ACME_EMAIL=ops@example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://signatures.example.com
MEDIA_BASE_URL=https://signatures.example.com/media

docker compose -f compose.traefik.yml up -d
```

The milter still listens on TCP 5000 directly — Postfix speaks
libmilter, not HTTP, so it never goes through the proxy.

## Connecting Postfix

In ``main.cf``:

```
smtpd_milters = inet:disclaimrng:5000
non_smtpd_milters = inet:disclaimrng:5000
milter_default_action = accept
milter_protocol = 6
```

Replace ``disclaimrng`` with the hostname or IP that resolves to your
milter container.

## Required environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| ``DJANGO_SECRET_KEY`` | yes | — | ``python -c 'import secrets; print(secrets.token_urlsafe(64))'`` |
| ``DJANGO_ALLOWED_HOSTS`` | yes | ``localhost,127.0.0.1`` | Comma-separated, **must** include the host you reach the admin on |
| ``DJANGO_CSRF_TRUSTED_ORIGINS`` | yes | ``http://localhost:8000`` | Origins (scheme + host[:port]) trusted for cross-site forms |
| ``POSTGRES_PASSWORD`` | yes | — | Used by the db service *and* parsed by Django |
| ``DATABASE_URL`` | yes | — | Connection string; hostname is the compose service name |
| ``MILTER_SOCKET`` | no | ``inet:0.0.0.0:5000`` | Where the milter binds |
| ``MEDIA_BASE_URL`` | recommended | (empty) | Absolute URL prepended to image paths in rendered mails |

See [``.env.example``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/.env.example)
for the full annotated list, including LDAP and tenant bootstrap.

## Updating

```bash
git pull
docker compose pull        # if you're using the registry image
docker compose up -d --build
```

Migrations run automatically on the next ``web`` boot.
