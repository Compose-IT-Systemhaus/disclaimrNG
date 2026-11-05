# Changelog

All notable changes to **disclaimrNG** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/releases/tag/v0.1.0
