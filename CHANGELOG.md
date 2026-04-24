# Changelog

All notable changes to **disclaimrNG** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The first release of disclaimrNG ports the original [disclaimr](https://github.com/dploeger/disclaimr) (Python 2.7 / Django 1.7, last commit 2019) to a current stack and packages it as a Docker-Compose deployment.

### Added
- Fork of `dploeger/disclaimr` as `Compose-IT-Systemhaus/disclaimrNG` with a `main` branch for new development (`master` retained as legacy reference).
- Documentation skeleton: new `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`.

### Changed
- Re-licensed under MIT with copyright held jointly by Dennis Plöger (original) and Compose-IT-Systemhaus (modernisation).

### Planned
- Port to Python 3.12 and Django 5.x.
- Replace MySQL/MariaDB recommendation with PostgreSQL as the default backend.
- Replace Grappelli admin theme with `django-unfold`.
- Add Monaco + TinyMCE based template editor with live preview.
- Multi-stage `Dockerfile` and `compose.yml` (Postgres + web + milter).
- GitHub Actions CI: `ruff`, `mypy`, `pytest`, Docker build.
