# disclaimrNG — Mail Signature Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org)
[![Django](https://img.shields.io/badge/Django-5.x-darkgreen.svg)](https://www.djangoproject.com)

**disclaimrNG** is a modernised, dockerized fork of [dploeger/disclaimr](https://github.com/dploeger/disclaimr) — a [milter daemon](https://www.milter.org/) that dynamically attaches signatures (also called disclaimers or footers) to outgoing email.

It hooks into the SMTP mail flow of any milter-capable MTA (Postfix, Sendmail), pulls per-user data (name, title, phone, mail address, …) from an LDAP server or Active Directory, and lets non-technical staff manage signature templates through a modern web interface.

> **Status:** active development. The Python 2 / Django 1.7 port is in progress — see the [CHANGELOG](CHANGELOG.md) for the current state.

## Features

- **Milter integration** with Postfix and Sendmail — drop into the existing mail flow without touching delivery logic.
- **LDAP / Active Directory resolver** with per-server query cache: pull display name, title, phone, mail attributes etc. directly into signatures.
- **Web UI for templates** with side-by-side **Code editor** (Monaco, with auto-completion for resolver variables) and **WYSIWYG editor** (TinyMCE), plus a live **preview** rendered against sample LDAP data.
- **Rule engine** with requirements (sender IP / regex, recipient regex, header / body filters) and actions (append disclaimer, replace tag, …) — configurable through the web UI.
- **Plaintext and HTML** mail support including charset handling and an HTML-fallback option.
- **Docker-Compose stack** with Postgres, web frontend and milter daemon — `docker compose up` and you are running.

## Quickstart

```bash
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git
cd disclaimrNG
cp .env.example .env
# edit .env — at minimum set DJANGO_SECRET_KEY and DJANGO_ALLOWED_HOSTS
docker compose up -d
docker compose exec web python manage.py createsuperuser
```

The web UI is then available on `http://localhost:8000/admin/`. Configure your MTA to talk to the milter on port `5000`, e.g. for Postfix:

```
smtpd_milters = inet:disclaimrng:5000
non_smtpd_milters = inet:disclaimrng:5000
milter_default_action = accept
```

## Architecture

```
                    ┌────────────────────┐
   outgoing mail ── │  Postfix / Sendmail│ ── milter (5000) ──┐
                    └────────────────────┘                    │
                                                              ▼
   ┌──────────┐         ┌──────────────┐         ┌────────────────────┐
   │  LDAP /  │ ◄────── │   milter     │ ◄─────► │   PostgreSQL       │
   │   AD     │         │   daemon     │         │  (rules, templates)│
   └──────────┘         └──────────────┘         └────────────────────┘
                                                              ▲
                                                              │
                                              ┌──────────────────┐
                                              │  Django web UI   │ ── browser
                                              │  (admin + editor)│
                                              └──────────────────┘
```

## Configuration

All runtime configuration is via environment variables — see [`.env.example`](.env.example) for the full list. Templates, rules, requirements and directory servers are managed in the web UI and persisted in PostgreSQL.

### Behind Traefik

A ready-to-use compose file with Traefik + Let's Encrypt is included as [`compose.traefik.yml`](compose.traefik.yml). It is a self-contained alternative to `compose.yml` (don't stack the two):

```bash
# in .env
DISCLAIMR_HOSTNAME=signatures.example.com
ACME_EMAIL=ops@example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://signatures.example.com
MEDIA_BASE_URL=https://signatures.example.com/media

docker compose -f compose.traefik.yml up -d
```

The milter still listens on TCP 5000 directly (Postfix speaks libmilter, not HTTP, so it does not pass through the proxy).

## Documentation

- [CHANGELOG](CHANGELOG.md) — release notes and migration steps from upstream `disclaimr`.
- [CONTRIBUTING](CONTRIBUTING.md) — local development setup and contribution guidelines.

## Credits

disclaimrNG is a fork of [disclaimr](https://github.com/dploeger/disclaimr) by **Dennis Plöger** (MIT). The original architecture (milter daemon, Django data model, LDAP resolver, query cache) is by him; this fork modernises the stack and adds the new web template editor.

## License

MIT — see [LICENSE](LICENSE).
