# Contributing to disclaimrNG

Thanks for considering a contribution! disclaimrNG is a community-maintained fork — bug reports, feature ideas, and pull requests are welcome.

## Getting started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and the `docker compose` plugin
- [Python 3.12+](https://www.python.org) (only needed if you want to run the test suite outside Docker)
- A GitHub account

### Development setup

```bash
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git
cd disclaimrNG
cp .env.example .env
docker compose -f compose.yml -f compose.dev.yml up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

The dev compose file mounts the source tree into the container and runs Django with auto-reload, so edits in your editor are picked up live.

### Running tests

```bash
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web mypy disclaimr disclaimrwebadmin
```

## How to contribute

1. **Open an issue first** for non-trivial changes so we can align on scope.
2. **Fork** the repository and create a topic branch off `main`:
   ```bash
   git checkout -b feature/short-description
   ```
3. **Make focused commits** — one logical change per commit, present-tense imperative subject (`add`, `fix`, `refactor`).
4. **Run tests and linters** locally before pushing.
5. **Open a pull request** against `main` and reference the issue (`Closes #123`).

## Code style

- **Python:** [PEP 8](https://peps.python.org/pep-0008/) enforced by `ruff` (config in `pyproject.toml`).
- **Type hints:** required on all new public APIs; checked by `mypy` in strict mode where practical.
- **Templates and static assets:** keep vendored libraries (Monaco, TinyMCE) out of git — fetch them at build time in the Dockerfile.

## Reporting security issues

Please **do not** open public issues for security vulnerabilities. Email `security@compose-it-systemhaus.de` instead and we will coordinate a fix and disclosure.

## License

By contributing, you agree that your contributions will be licensed under the MIT License (see [LICENSE](LICENSE)).
