# Changelog

All notable changes to **disclaimrNG** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-06

New migrations run on start-up (`0008` and the tables of `django-allauth`). The roles Admins, Editor and Reader are created automatically. Single sign-on stays off until the `OIDC_*` variables are set; see the new documentation page *Single sign-on (OIDC)* — the sign-in round trip has not been tested against a live Authentik yet.

### Added
- Single sign-on over OpenID Connect (for Authentik and other OIDC providers): set `OIDC_SERVER_URL`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` and the login page gets a button. Users are created on their first sign-in; at every sign-in the groups of the provider are mapped onto local groups (*Settings › SSO groups*), users without a mapped group become Readers, and members of Admins are superusers. Local accounts are never linked or taken over. New dependency `django-allauth`; its tables are created by `migrate`.
- Built-in roles: the groups Admins (everything), Editor (look at, create and change signatures and rules) and Reader (look only) are created on start-up. Their permissions can be changed in the admin and are kept; `manage.py sync_roles --reset` restores them.

### Removed
- The unused systemd notification of the milter and its start-up warning "Missing module systemd.daemon". The milter runs in a container, where systemd never starts it.

## [0.2.0] - 2026-11-06

Three new migrations (`0005`–`0007`) run on start-up. If you use your own Compose file, mount the `media` volume read-only at `/app/media` in the milter container to use embedded images; without it such images are linked as before (warning in the milter log).

### Added
- Directory conditions for requirements: a requirement can demand that a directory attribute of the sender (e.g. `department`) matches a regex, so rules can target departments or titles. All conditions of a requirement have to hold; if the directory cannot be asked they do not hold. The conditions are edited on the requirement's own page, linked from the rule.
- Group conditions: a requirement can demand that the sender is a member of a group. On Active Directory nested groups count (in-chain matching rule), otherwise the sender's `memberOf` values are compared. The signature test page lists the checked conditions.
- Signature images can be embedded in the mail instead of linked: tick "Embed in the mail" on the image and HTML mails carry it as an inline `cid:` part (`multipart/related`), so it shows without "load images" and without a request to your server. Images over 1 MiB are still linked. The milter now mounts the `media` volume read-only (Compose files updated); a custom setup needs the same mount.

## [0.1.3] - 2026-11-06

**Release 0.1.2 must not be used:** it defers every mail that reaches the milter through a real MTA (see "Fixed"). Update to 0.1.3.

### Added
- Time-limited actions: an action can have a "valid from" and a "valid until" moment, so campaign banners and holiday notices start and stop on their own. The milter judges the window when it processes the mail.
- Dashboard card "Mails of the last 7 days" for administrators: seen, signed and untouched mails, a bar per day, the most frequent signatures and the time of the last mail, taken from the mail log.
- An end-to-end test in the CI (Postfix, the milter, a test LDAP and a mail sink) that checks the signature, the line endings, banner validity, the mail log and LDAPS with a stored CA certificate.

### Fixed
- Every mail through a real MTA was deferred (`TypeError: _eob() takes 2 positional arguments but 3 were given`): a method of the milter shadowed python-libmilter's internal `_eob`. Introduced in 0.1.2.

## [0.1.2] - 2026-11-06

### Added
- "Logs" view under Settings (administrators only): every mail the milter sees, with sender, recipient, subject and the applied rule/action/signature; unprocessed mails can be filtered out. Entries are removed after `MAIL_LOG_RETENTION_DAYS` days (default 30, `0` keeps them). Documented on the new "Mail logs" handbook page.
- Directory servers choose TLS: a checkbox "Encrypt the connection (TLS)" (on by default; the URL scheme has to match, `ldaps://` with TLS, `ldap://` without) and, with TLS, a CA certificate per server that can be uploaded as a PEM file or pasted. It is stored in the database and used by the milter and by the "Test connection" / "Discover attributes" buttons; without one the container's CA store still applies. Existing servers get TLS switched on when they use `ldaps://` URLs.

### Fixed
- The password field of the directory server form was narrower than the user-DN field.

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

[Unreleased]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Compose-IT-Systemhaus/disclaimrNG/releases/tag/v0.1.0
