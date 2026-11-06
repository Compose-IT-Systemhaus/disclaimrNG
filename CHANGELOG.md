# Changelog

All notable changes to **disclaimrNG** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- "Logs" view under Settings (administrators only): every mail the milter sees, with sender, recipient, subject and the applied rule/action/signature; unprocessed mails can be filtered out. Entries are removed after `MAIL_LOG_RETENTION_DAYS` days (default 30, `0` keeps them). Documented on the new "Mail logs" handbook page.

## [0.1.1] - 2026-11-05

### Added
- Runbook "disclaimrNG with Stalwart 1.0 and Active Directory" (German and English) in the in-admin documentation, and `compose.stalwart.yml`, an overlay that attaches the milter to a shared Docker network as `disclaimrng-milter`.
- Private CA for `ldaps://` in every setup: `compose.yml` and `compose.traefik.yml` mount `./certs`, and the entrypoint trusts `certs/ad-ca.pem` (sets `LDAPTLS_CACERT`) when it exists.
- `DISCLAIMR_IMAGE` and `DISCLAIMR_PULL_POLICY` run a published image instead of building from source; `WEB_BIND` sets the host address of the web port in `compose.yml`.

### Changed
- The milter answers with a CRLF replacement body. Postfix accepts both, Stalwart writes the body as it is, so LF-only lines no longer end up in the message.
- The milter process releases its database connection after every mail instead of holding it for the whole SMTP connection.
- LDAP connections are opened in one place (`ldap_helper.open_connection`), and gunicorn keeps its heartbeat file in `/dev/shm`.
- Traefik 3.1 -> 3.7 in `compose.traefik.yml`; the milter container no longer mounts the media volume; `MILTER_SOCKET` defaults to `inet:0.0.0.0:5000`.
- `compose.dev.yml` runs the migrations, compiles the translations and creates the admin user before `runserver`, and publishes Postgres on `127.0.0.1` only.
- The Postfix example in the documentation uses `127.0.0.1:5000` (the milter port is published on the loopback address).

### Fixed
- The Active Directory default search query has two placeholders, which made every lookup with it fail with a `TypeError`. The documentation named a different default.

## [0.1.0] - 2026-11-05

The first release of disclaimrNG ports the original [disclaimr](https://github.com/dploeger/disclaimr) (Python 2.7 / Django 1.7, last commit 2019) to a current stack and ships it as a Docker Compose deployment.

### Added
- Port to Python 3.12 and Django 5.x with PostgreSQL 16 as the default database.
- Multi-stage `Dockerfile` and `compose.yml` (Postgres + web + milter); `compose.traefik.yml` for Traefik with Let's Encrypt; `compose.dev.yml` for development.
- Admin UI on `django-unfold` with a dashboard, grouped sidebar and a German/English language toggle.
- Template editor: Monaco code editor, TinyMCE visual editor, live preview, placeholder chips (envelope, header, common fields, directory attributes) and an image gallery with quick upload.
- `SignatureImage` uploads, referenced as `{image["slug"]}`; images are served under `/media/`.
- Multi-tenancy: tenants bundle sender domains and directory servers.
- Directory server flavours (LDAP / Active Directory / custom) with connection test and attribute discovery.
- Environment bootstrap for tenants (`TENANTS`) and directory servers (`LDAP_SERVERS`); `bootstrap_admin` creates the first admin with a random password.
- Signature test page that runs the real milter pipeline, including LDAP.
- In-admin documentation (German and English) under `/admin/disclaimr/docs/`.
- Committed initial migration, checked by CI (`makemigrations --check`).
- GitHub Actions CI: `ruff`, `pytest`, Docker build with push to GHCR (`:dev` from `master`, semver tags from `v*`).

### Changed
- Re-licensed under MIT with copyright held jointly by Dennis Plöger (original) and Compose-IT-Systemhaus (modernisation).
- A requirement's recipient regex has to match **at least one** recipient (before, the first non-matching recipient dropped the requirement). `{recipient}` is the first matching recipient.
- Template placeholders are replaced in a single pass, so substituted values are never scanned for tags again.
- The milter port is published on `127.0.0.1` by default; set `MILTER_BIND` when your MTA runs on another host.
- The admin's own views (directory server test, preview, signature test, image upload) require model permissions, not only staff status.

### Fixed
- Requirement regexes are validated on save; an invalid pattern can no longer make the milter defer every mail.
- LDAP errors during bind or search skip the server instead of aborting the mail; exceptions in milter callbacks are logged with a traceback.
- Mails without a `Content-Transfer-Encoding` header get a valid `7bit` instead of an invented value.
- Uploaded images were not served in production.

[Unreleased]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/releases/tag/v0.1.0
