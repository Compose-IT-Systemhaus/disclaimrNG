# CLAUDE.md — disclaimrNG

Projektkontext für Claude Code. Stand: 2026-10-23 (letzter gemergter PR: #25).

## User & Arbeitsweise

- **Sprache:** Mit dem User auf **Deutsch** kommunizieren; technische Begriffe (SMTP, LDAP, Milter, Docker …) bleiben englisch.
- **Commits, PR-Titel und PR-Bodies sind auf Englisch** — so ist es seit PR #1 durchgängig im Repo. Diese Konvention beibehalten.
- **GitHub-Account:** `citfs` (`gh` CLI ist eingeloggt).
- **GitHub-Org:** immer **`Compose-IT-Systemhaus`** (der User schreibt manchmal „Compose-IT“, gemeint ist immer die volle Org).
- **Plattform:** Windows 11. Shell-Kommandos über Git-Bash mit Unix-Pfaden (`/dev/null`, nicht `NUL`); PowerShell steht ebenfalls zur Verfügung.
- **Python und Docker sind lokal NICHT installiert** (`python` im PATH ist nur der WindowsApps-Store-Stub). Nichts blind ausführen, was Python/Docker braucht — solche Kommandos explizit als „muss der User ausführen“ kennzeichnen. Lint/Tests laufen faktisch über GitHub Actions (CI) bzw. beim User im Container.
  Notfalls lokal: `uvx --system-certs ruff check .`; pytest in einer `uv venv --system-certs --python 3.12` mit allen Abhängigkeiten außer `python-ldap` (kein Windows-Build) plus Stub-Paket `ldap` im `PYTHONPATH`, CI-Env-Variablen setzen (`DJANGO_SECRET_KEY`, `DATABASE_URL=sqlite:///:memory:` …). Die venv nicht unter sehr langen Pfaden anlegen (Windows-MAX_PATH bricht Django-Migrationen/Static-Files).

### Git-/PR-Workflow (so wurden PR #1–#25 gemacht)

1. Neuer Branch von `origin/master`: `feat/<kurz>` oder `fix/<kurz>`.
2. Fokussierte Commits, englisch, Imperativ (`Add …`, `Fix …`, `Move …`).
3. Push + PR **gegen `master`** mit Abschnitten `## Summary` (ggf. Unterabschnitte pro Änderung, Begründung/Root-Cause) und `## Test plan` (Checkbox-Liste mit konkreten Klickpfaden), Abschluss `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
4. Der User testet und merged selbst.

**Achtung bei `gh`:** Es gibt zwei Remotes (`origin` = `Compose-IT-Systemhaus/disclaimrNG`, `upstream` = `dploeger/disclaimr`) und **kein `gh repo set-default`**. Ohne `-R` landet `gh pr …` beim Upstream-Repo von Dennis Plöger. Deshalb immer `-R Compose-IT-Systemhaus/disclaimrNG` angeben. Nie PRs gegen upstream öffnen.

- **Base-Branch ist `master`** (CI triggert auf `master`). Der Branch `main` ist veraltet; CONTRIBUTING.md und CHANGELOG.md erwähnen fälschlich noch `main`.
- GitHub-Issues sind im Repo deaktiviert.

## Projekt

**disclaimrNG** = modernisierter Fork von [dploeger/disclaimr](https://github.com/dploeger/disclaimr) (Python 2.7 / Django 1.7, seit Jahren EOL). Open-Source-Mail-Signaturserver: Milter-Daemon für Postfix/Sendmail hängt Signaturen/Disclaimer an ausgehende Mails, zieht Userdaten aus LDAP/AD, Templates werden über eine Web-UI gepflegt. Deployment als Docker-Compose-Stack.

**Warum Port statt Rewrite:** Datenmodell und Architektur des Originals sind solide.

**Lizenz:** MIT. Original-Autor **Dennis Plöger** muss in LICENSE/README genannt bleiben (Copyright gemeinsam mit Compose-IT-Systemhaus).

**Repo:** https://github.com/Compose-IT-Systemhaus/disclaimrNG — lokal unter `C:\Scripts\disclaimrNG`.

## Stack

- Python 3.12, Django 5.x, PostgreSQL 16 (Tests/CI: SQLite in-memory)
- Admin-Theme `django-unfold` (+ `django-admin-sortable2`; PyPI-Name mit Bindestrich, Importname `adminsortable2`)
- LDAP: **`python-ldap`** (C-Binding, braucht `libldap2-dev`/`libsasl2-dev` zum Bauen)
- Milter: **`python-libmilter`** (`import libmilter as lm`), Einstiegspunkt `disclaimr.py`
- Static Files via **WhiteNoise** aus gunicorn (`CompressedStaticFilesStorage`, bewusst *nicht* Manifest — der Editor referenziert `/static/…` hart aus JS)
- Template-Editor: **Monaco + TinyMCE 7 von jsdelivr-CDN** (nicht vendored)
- Docs-Rendering: `markdown` + `Pygments`
- Build: `pyproject.toml` (hatchling), Lint `ruff` (Regeln E,F,W,I,B,UP,DJ; line-length 100), `mypy` mit django-stubs (nicht strict), `pytest-django`

## Struktur

| Pfad | Inhalt |
|---|---|
| `disclaimr.py` | Milter-Daemon (`DisclaimrMilter`, ForkMixin), ruft `django.setup()` |
| `disclaimr/milter_helper.py` | `MilterHelper`: Requirement→Rule→Action-Pipeline, LDAP-Resolve, Template-Tag-Ersetzung, `do_action` |
| `disclaimr/configuration_helper.py` | `build_configuration()` — lädt Regelwerk aus der DB |
| `disclaimr/ldap_helper.py` | `test_connection`, `discover_attributes` (Admin-Buttons) |
| `disclaimr/query_cache.py` | thread-sicherer LDAP-Query-Cache |
| `disclaimrweb/` | Django-Projekt (`settings.py`, `urls.py`, `wsgi.py`) |
| `disclaimrwebadmin/models.py` | `Tenant`, `TenantDomain`, `Rule`, `Requirement`, `Disclaimer`, `DirectoryServer`, `DirectoryServerURL`, `SignatureImage`, `Action` |
| `disclaimrwebadmin/admin.py` | unfold-ModelAdmins + Inlines |
| `disclaimrwebadmin/apps.py` | `verbose_name="disclaimrNG"`; `ready()` patcht `admin.site.get_app_list` → Gruppen „Signatures“/„Settings“ |
| `disclaimrwebadmin/views/` | `preview`, `signature_image` (Quick-Upload), `signature_test`, `directory_server` (Test/Attribute/Vocabulary), `docs` |
| `disclaimrwebadmin/widgets/template_editor.py` | `TemplateEditorWidget` (Tabs Code/Visual/Preview, Chips, Bildergalerie) |
| `disclaimrwebadmin/management/commands/` | `bootstrap_admin`, `sync_tenants`, `sync_directory_servers` |
| `disclaimrwebadmin/static/disclaimrwebadmin/` | Editor-JS/CSS, Language-Switcher, Help-Button, Logos |
| `locale/de/LC_MESSAGES/django.po` | Deutsche Übersetzungen (handgeschrieben); daneben existiert noch `disclaimrwebadmin/locale/de/…` |
| `docs/{de,en}/*.md` | In-Admin-Handbuch (8 Seiten je Sprache) |
| `docker/entrypoint.sh` | Rollen `web` / `milter` / `manage` / beliebiges exec |
| `tests/` | pytest; `conftest.py` setzt Env-Defaults (SQLite) |

### URLs

- **Admin liegt auf `/`** (`path("", admin.site.urls)`), nicht auf `/admin/` (README ist da ungenau).
- Eigene Views unter `/admin/disclaimr/…`: `disclaimer/preview/`, `signatureimage/quick-upload/`, `signature-test/`, `docs/`, `docs/<slug>/`, `directoryserver/<pk>/test/`, `directoryserver/<pk>/attributes/`, `directoryserver/vocabulary/`.
- `/i18n/setlang/` für den Sprachumschalter.

## Fachliche Kernpunkte

- **Template-Platzhalter:** `{sender}`, `{recipient}`, `{header["subject"]}`, `{resolver["cn"]}` (LDAP-Attribute), `{image["slug"]}` (SignatureImage → `<img>` in HTML, nackte URL in Plaintext, Basis-URL aus `MEDIA_BASE_URL`).
- **Editor-Chips:** Gruppen Envelope / Header / Common fields (Name→`cn`, Phone→`telephoneNumber`, Email→`mail`, Address→`streetAddress`) / Verzeichnis-Attribute; Klick fügt am Cursor des aktiven Editors ein (`insertToken`). Labels kommen per `data-common-fields`-JSON aus Python (`gettext_lazy`).
- **Multi-Tenancy:** `Tenant` bündelt Sender-Domains + Directory-Server. FKs von Disclaimer/DirectoryServer/Rule sind nullable mit `SET_NULL`. Auflösung der Directory-Server: erst `action.directory_servers`, sonst die Server des Tenants, dem die Sender-Domain gehört (nur exakte Domain, keine Wildcards).
- **Env-Bootstrap:** `TENANTS` + `TENANT_<HANDLE>_*` und `LDAP_SERVERS` + `LDAP_SERVER_<HANDLE>_*` (Details in `.env.example`). Entrypoint: migrate → collectstatic → `bootstrap_admin` → `sync_tenants` → `sync_directory_servers` → gunicorn. Env-verwaltete Zeilen tragen den Marker `[env-managed]`; `--prune` löscht nur diese.
- **`bootstrap_admin`:** idempotent, legt `admin` mit Zufallspasswort an und loggt es im Banner (`docker compose logs web`); `--reset` erzeugt ein neues.
- **DirectoryServer-Flavors:** LDAP / AD / Custom, liefern nur Default-Query und Attribut-Vokabular (`constants.py`), die Auflösung selbst ist identisch.
- **Signaturtest-Seite:** fährt die *echte* Pipeline (`MilterHelper(build_configuration())`) inkl. LDAP — Ergebnis entspricht dem Produktiv-Milter.
- **In-Admin-Docs:** `DocsView` (staff-only) mit hart codierter `TOC`-Allowlist (Schutz gegen Path-Traversal), Fallback auf `en/`. Neue Seite = Markdown in `docs/de/` **und** `docs/en/` + TOC-Eintrag. Docs werden ins Image kopiert.
- **i18n:** Quellstrings sind **Englisch**, Deutsch kommt aus der `.po`. `.mo` wird beim Docker-Build per `compilemessages` erzeugt (nicht committen). Neue UI-Strings immer in `gettext`/`gettext_lazy` wrappen und deutsche Übersetzung in `locale/de/LC_MESSAGES/django.po` ergänzen.

## Bekannte Stolperfallen

- **Migrationen sind nicht committet.** `disclaimrwebadmin/migrations/` enthält nur `__init__.py`; `makemigrations` läuft im Dockerfile beim Build, pytest nutzt `--no-migrations`. Folge: Modelländerungen erzeugen beim nächsten Build ein neues `0001_initial`, das auf einer bestehenden DB (wo `0001_initial` schon als angewendet markiert ist) **nicht** erneut läuft → Schema-Drift. Vor produktivem Einsatz Migrationen einchecken.
- **Py2→Py3-Erbe:** bytes vs. str (Body-Chunks, LDAP-Attributwerte), `filter()`/`map()` sind Iteratoren, `__unicode__` → `__str__`, `on_delete` überall nötig.
- **Mail-Encoding im Milter:** Payload bei `7bit`/`8bit` als **str** setzen; nur für `quoted-printable`/`base64` bytes — sonst serialisiert Pythons `email` als base64 trotz anderem CTE-Header (Fix PR #19).
- **python-libmilter 2.x spricht bytes:** Adressen, Header, Body-Chunks und Makro-Keys (`b"i"`) kommen als bytes, `replBody`/`addHeader`/`chgHeader` erwarten bytes. Umwandeln nur an der Grenze in `disclaimr.py` (`_text`/`_raw`/`_address`); `MilterHelper` arbeitet mit str. Tests, die `MilterHelper` direkt mit str füttern, sehen solche Fehler nicht → `test_milter_round_trip_with_bytes`.
- **`MilterHelper` lebt pro MTA-Verbindung**, nicht pro Mail: `reset()` bei jedem MAIL FROM / ABORT. Der Milter forkt pro Verbindung → `QueryCache` hält nur innerhalb einer SMTP-Session; der Elternprozess schließt seine DB-Verbindung nach `build_configuration()` und baut den Sender-IP-Vorfilter alle `MILTER_CONFIG_TTL` s neu.
- Platzhalter werden in **einem** Durchlauf ersetzt (`render_template()` in `milter_helper.py`, auch von der Editor-Vorschau genutzt) — ersetzte Werte nie erneut nach Tags scannen (Endlosschleifen, Template-Injection über Header).
- **LDAP-Timeouts:** `OPT_NETWORK_TIMEOUT`/`OPT_TIMEOUT` = 5 s, sonst hängen gunicorn-Worker bis zum 30-s-Timeout (PR #21).
- **ruff E402:** Logger-Init unter die Imports setzen; in `disclaimr.py` stehen Imports nach `django.setup()` mit `# noqa: E402`.
- Die von Upstream geerbten Tests (`test_disclaimer.py`, `test_directoryserver.py`, `test_performance.py`, `test_requirements.py`) haben per-file-ignores in `pyproject.toml`; Live-LDAP-/Perf-Tests skippen ohne Konfiguration.
- GHCR-Imagepfad muss lowercase sein: `ghcr.io/compose-it-systemhaus/disclaimrng` (Tag `dev` bei Push auf master, Semver bei Tags `v*`).
- Unfold-Sidebar ist handkuratiert (`UNFOLD["SIDEBAR"]["navigation"]` in `settings.py`) — neue Admin-Modelle tauchen dort nicht automatisch auf.
- Neue CSS/JS für das Admin-Chrome über `UNFOLD["STYLES"]`/`["SCRIPTS"]` einhängen; Topbar-Elemente (Sprachumschalter, Hilfe-Button) werden per DOM-Injection in `#header-inner .ml-auto` eingefügt (Login: `body.login #page .absolute .ml-auto`). unfold 0.110 hat **kein** `<header>`-Element mehr.
- **unfold-Farbvariablen sind komplette Farben** (`--color-primary-600: rgb(52, 90, 140)`), nie in `rgb(var(…))` wickeln (ergibt ungültiges CSS → randlose Felder, unsichtbare Buttons). Alpha per `color-mix()`. Eigene Seiten bauen auf den `--dz-*`-Tokens und `.dz-*`-Bausteinen aus `admin_chrome.css` auf (Light/Dark dort zentral).
- unfold liefert Tailwind v4 in `@layer`s → unser ungelayertes CSS gewinnt immer gegen unfold-Utilities; Selektoren deshalb eng halten.
- unfold steht vor unserer App in `INSTALLED_APPS`, seine `admin/index.html`/`admin/login.html` überdecken gleichnamige Templates. Unsere heißen `disclaimrwebadmin/admin/{index,login}.html` und werden in `apps.ready()` gesetzt; Dashboard-Daten kommen aus `disclaimrwebadmin/dashboard.py` (`DASHBOARD_CALLBACK`).
- Die Logo-PNGs haben das Transparenz-Schachbrett eingebacken; im UI wird `img/mark.svg` + Text-Wortmarke verwendet.

## Kommandos (vom User im Container auszuführen)

```bash
docker compose up -d                                         # Prod-ähnlich
docker compose -f compose.yml -f compose.dev.yml up -d       # Dev: Source-Mount + runserver
docker compose -f compose.traefik.yml up -d                  # Variante hinter Traefik + Let's Encrypt
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web mypy disclaimr disclaimrwebadmin
docker compose logs web | grep -A3 -i password               # Admin-Passwort nach Erststart
```

CI (`.github/workflows/ci.yml`): Jobs `lint` (ruff), `test` (pytest, SQLite), `docker` (Build; bei PRs Smoke-Import, bei master-Push Push nach GHCR).

## Historie (gemergte PRs)

- #1 Port auf Py3.12/Django 5/Docker, unfold, Template-Editor, DirectoryServer-Flavors + Test/Discover-Buttons
- #2 Env-Bootstrap für LDAP, `SignatureImage`-Uploads
- #3 Multi-Tenancy, `bootstrap_admin`, Slate/Steel-Blue-Theme
- #4–#7 Logo-PNGs, `compose.traefik.yml`, lokaler Build + GHCR-Push
- #10–#14 CI-Fixes, admin.W411, Migration im Image, WhiteNoise, Editor-CDN
- #15–#22 Sidebar-Gruppen, Bild-Picker, Signaturtest-Seite + diverse Fixes (Encoding, UTF-8, LDAP-Timeouts, HTML-Append)
- #23 Platzhalter-Chips, Dashboard-Regruppierung, DE/EN-i18n mit Flaggen-Toggle
- #24 Common-field-Chips (Name/Phone/Email/Address)
- #25 In-Admin-Doku `/admin/disclaimr/docs/` + „?“-Button

## Offene Punkte (beobachtet, nicht vom User priorisiert)

- Migrationen einchecken (siehe Stolperfallen).
- CHANGELOG.md ist veraltet (listet Erledigtes noch unter „Planned“), README-Status-Satz und `/admin/`-URL ebenso; CONTRIBUTING.md nennt `main` statt `master`.
- Lokale Branches sind alle gemergt; vor neuer Arbeit `git fetch` und von `origin/master` abzweigen.
