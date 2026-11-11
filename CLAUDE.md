# CLAUDE.md — disclaimrNG

Projektkontext für Claude Code. Stand: 2026-11-11 (letzter gemergter PR: #60).

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
- Template-Editor: **Monaco + TinyMCE 7**, beim Docker-Build per `docker/fetch_editor_assets.py` von der npm-Registry geladen (sha512-geprüft, nicht im Git) nach `static/disclaimrwebadmin/vendor/`; `template_editor.js` fällt auf die jsdelivr-CDN zurück, wo der Ordner fehlt (z. B. Dev-Mount). Versionen in Script **und** JS gemeinsam anheben. TinyMCE 7 ist GPL-2.0-or-later (`license_key: "gpl"`).
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
- Eigene Views unter `/admin/disclaimr/…`: `disclaimer/preview/`, `signatureimage/quick-upload/`, `signature-test/`, `docs/`, `docs/<slug>/`, `directoryserver/test/` (POST mit den Formulardaten, optional `_object_id`), `directoryserver/<pk>/attributes/`, `directoryserver/vocabulary/`.
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

- **Migrationen sind committet** (`disclaimrwebadmin/migrations/`). Nach jeder Modelländerung `python manage.py makemigrations disclaimrwebadmin` ausführen und die Datei mit einchecken — die CI bricht bei `makemigrations --check` ab, wenn sie fehlt. Bereits angewendete Migrationen nie umschreiben, immer eine neue anlegen. pytest läuft mit Migrationen (kein `--no-migrations`).
- **Py2→Py3-Erbe:** bytes vs. str (Body-Chunks, LDAP-Attributwerte), `filter()`/`map()` sind Iteratoren, `__unicode__` → `__str__`, `on_delete` überall nötig.
- **Mail-Encoding im Milter:** Payload bei `7bit`/`8bit` als **str** setzen; nur für `quoted-printable`/`base64` bytes — sonst serialisiert Pythons `email` als base64 trotz anderem CTE-Header (Fix PR #19).
- **python-libmilter 2.x spricht bytes:** Adressen, Header, Body-Chunks und Makro-Keys (`b"i"`) kommen als bytes, `replBody`/`addHeader`/`chgHeader` erwarten bytes. Umwandeln nur an der Grenze in `disclaimr.py` (`_text`/`_raw`/`_address`); `MilterHelper` arbeitet mit str. Tests, die `MilterHelper` direkt mit str füttern, sehen solche Fehler nicht → `test_milter_round_trip_with_bytes`.
- **`MilterHelper` lebt pro MTA-Verbindung**, nicht pro Mail: `reset()` bei jedem MAIL FROM / ABORT. Der Milter forkt pro Verbindung → `QueryCache` hält nur innerhalb einer SMTP-Session; der Elternprozess schließt seine DB-Verbindung nach `build_configuration()` und baut den Sender-IP-Vorfilter alle `MILTER_CONFIG_TTL` s neu.
- Platzhalter werden in **einem** Durchlauf ersetzt (`render_template()` in `milter_helper.py`, auch von der Editor-Vorschau genutzt) — ersetzte Werte nie erneut nach Tags scannen (Endlosschleifen, Template-Injection über Header).
- **LDAP-Timeouts:** `OPT_NETWORK_TIMEOUT`/`OPT_TIMEOUT` = 5 s, sonst hängen gunicorn-Worker bis zum 30-s-Timeout (PR #21).
- **ruff E402:** Logger-Init unter die Imports setzen; in `disclaimr.py` stehen Imports nach `django.setup()` mit `# noqa: E402`.
- Die von Upstream geerbten Tests (`test_disclaimer.py`, `test_directoryserver.py`, `test_performance.py`, `test_requirements.py`) haben per-file-ignores in `pyproject.toml`; Live-LDAP-/Perf-Tests skippen ohne Konfiguration.
- GHCR-Imagepfad muss lowercase sein: `ghcr.io/compose-it-systemhaus/disclaimrng` (Tag `dev` bei Push auf master, Semver bei Tags `v*`).
- Unfold-Sidebar ist handkuratiert (`UNFOLD["SIDEBAR"]["navigation"]` in `settings.py`) — neue Admin-Modelle tauchen dort nicht automatisch auf. Jeder Eintrag trägt einen `permission`-Callback (`_sees(app, model)`), neue Einträge ebenso.
- **Healthchecks:** `web` antwortet auf `/healthz` (DB-Check, ohne Login), `milter` wird per TCP-Connect auf Port 5000 geprüft; beide stehen in `compose.yml`/`compose.traefik.yml`, der Milter wartet auf ein gesundes `web` (Migrationen sind dann durch). `ALLOWED_HOSTS` bekommt `127.0.0.1`/`localhost` dazu, sonst scheitert der Check bei eng gesetzten Hosts. `DISCLAIMR_ADMIN_PASSWORD` setzt das Admin-Passwort in `bootstrap_admin` (wird nicht geloggt).
- Neue CSS/JS für das Admin-Chrome über `UNFOLD["STYLES"]`/`["SCRIPTS"]` einhängen; Topbar-Elemente (Sprachumschalter, Hilfe-Button) werden per DOM-Injection in `#header-inner .ml-auto` eingefügt (Login: `body.login #page .absolute .ml-auto`). unfold 0.110 hat **kein** `<header>`-Element mehr.
- **unfold-Farbvariablen sind komplette Farben** (`--color-primary-600: rgb(52, 90, 140)`), nie in `rgb(var(…))` wickeln (ergibt ungültiges CSS → randlose Felder, unsichtbare Buttons). Alpha per `color-mix()`. Eigene Seiten bauen auf den `--dz-*`-Tokens und `.dz-*`-Bausteinen aus `admin_chrome.css` auf (Light/Dark dort zentral).
- unfold liefert Tailwind v4 in `@layer`s → unser ungelayertes CSS gewinnt immer gegen unfold-Utilities; Selektoren deshalb eng halten.
- unfold steht vor unserer App in `INSTALLED_APPS`, seine `admin/index.html`/`admin/login.html` überdecken gleichnamige Templates. Unsere heißen `disclaimrwebadmin/admin/{index,login}.html` und werden in `apps.ready()` gesetzt; Dashboard-Daten kommen aus `disclaimrwebadmin/dashboard.py` (`DASHBOARD_CALLBACK`).
- Die Logo-PNGs haben das Transparenz-Schachbrett eingebacken; im UI wird `img/mark.svg` + Text-Wortmarke verwendet.
- **Requirement-Empfänger:** Die `recipient`-Regex muss **mindestens einen** Empfänger treffen. `rcpt()` merkt sich nur Treffer (`_rcpt_matched`), `eoh()` entscheidet — Tests, die `eoh()` ohne vorheriges `rcpt()` aufrufen, verlieren sonst alle Requirements. `{recipient}` ist der erste passende Empfänger.
- **Fehler im Milter-Callback** lässt `python-libmilter` still schlucken (`log()` ist leer): Verbindung weg, MTA stellt die Mail zurück. Deshalb loggt `DisclaimrMilter.dataReceived` den Traceback; Regexe werden beim Speichern validiert (`validate_regex`), LDAP-Fehler (`ldap.LDAPError`) überspringen nur den Server.
- **Eigene Admin-Views** (`directory_server`, `preview`, `signature_test`) prüfen Modellrechte über `views/permissions.py::staff_with_perm`, nicht nur `is_staff`; `signature_image` prüft `add_signatureimage` und validiert die Datei als Bild. Tests dafür brauchen einen Superuser oder gezielte Rechte.
- **`/media/` wird immer von Django ausgeliefert** (`disclaimrweb/urls.py`, `serve`), auch ohne `DEBUG` — die Bilder gehen per Mail an Empfänger ohne Login. Bei viel Bild-Traffic einen Proxy davor setzen.
- Der Milter-Port wird nur auf `${MILTER_BIND:-127.0.0.1}` veröffentlicht (kein Auth im Protokoll, ein Fork pro Verbindung). `DJANGO_SECURE_COOKIES=true` (in `compose.traefik.yml` gesetzt) schaltet Secure-Cookies und `X-Forwarded-Proto` ein.
- **Compose:** Das Image kommt aus `${DISCLAIMR_IMAGE:-…:dev}` mit `${DISCLAIMR_PULL_POLICY:-build}` (Standard: lokal bauen; für ein Release `DISCLAIMR_IMAGE=…:0.3.1` + `missing`). `WEB_BIND` steuert die Host-Adresse von Port 8000 in `compose.yml`. Der Milter mountet `/app/media` read-only (nur für eingebettete Bilder, s. u.). `compose.dev.yml` führt beim Start `migrate`, `compilemessages` und `bootstrap_admin` aus, bevor `runserver` startet — der Healthcheck bleibt bis dahin rot, der Milter wartet darauf. Traefik ist auf `v3.7` gepinnt (ältere Versionen vertragen sich nicht mit neuen Docker-Engines).
- **Stalwart-Runbook:** `docs/{de,en}/stalwart-active-directory.md` (TOC-Slug `stalwart-active-directory`) beschreibt Stalwart 1.0 + AD; `compose.stalwart.yml` hängt den Milter als `disclaimrng-milter` ins externe Docker-Netz `mailnet`. Die private CA für `ldaps://` gilt für jedes Setup: `compose.yml`/`compose.traefik.yml` mounten `./certs` nach `/etc/ssl/ad` (read-only, nicht im Git), und `docker/entrypoint.sh` setzt `LDAPTLS_CACERT` auf `/etc/ssl/ad/ad-ca.pem`, wenn die Datei existiert und die Variable nicht schon gesetzt ist (nur für den Hauptprozess — `docker compose exec` sieht sie nicht). Stalwart ruft Milter nur bei der Einlieferung (kein Outbound-Filter), Stage `data`, `enable: authenticated_as != ''`; es sendet keine Queue-ID (`i`). Der Ablauf ist nur gegen die Stalwart-Doku und den Quelltext geschrieben, nicht gegen eine laufende Instanz. Der AD-Standardfilter hat zwei `%s` — `_lookup_sender` ersetzt alle (früher `TypeError`).
- **Stalwart-Kompatibilität (gegen Doku und Quelltext `crates/smtp/src/inbound/milter` geprüft):** Stalwart bietet die Protokollmaske 66 an, also keine NR-Flags — jeder Befehl wird synchron beantwortet, python-libmilter regelt das beim Aushandeln. Es sendet `raw_body` (nur den Body, obwohl die Doku „Header inklusive“ sagt) und schreibt den Ersatz-Body **unverändert** in die Mail, deshalb liefert `eob()` den Body mit CRLF (`_NEWLINE_RE`). `ChangeHeader` zählt Vorkommen (Index 1 = erstes), `AddHeader` landet oben. Die Context7-Kopie der Stalwart-Doku ist älter (Feld `hostname`, in 1.0 heißt es `host`) — die offizielle 1.0-Referenz gilt.
- **Verzeichnisserver-TLS:** `DirectoryServer.use_tls` (Standard an) bestimmt das Schema der URLs. Im Admin gibt es kein URL-Inline mehr: `DirectoryServerForm.hosts` (Block *Connection*, `host[:port]` je Zeile, eine eingefügte URL wird auf den Host gekürzt) und `DirectoryServerAdmin.save_model` schreibt die `DirectoryServerURL`-Zeilen bei jedem Speichern neu (`ldaps://` bei TLS, sonst `ldap://`, Reihenfolge = Failover). STARTTLS gibt es nicht. `ca_certificate` (PEM, im Admin als Upload oder Text) liegt in der DB, weil Milter und Web kein gemeinsames Dateisystem haben; `ldap_helper.open_connection(url, server)` schreibt sie in eine Datei im Temp-Verzeichnis (libldap liest CAs nur aus Dateien) und setzt `OPT_X_TLS_REQUIRE_CERT`, `OPT_X_TLS_CACERTFILE` und zuletzt `OPT_X_TLS_NEWCTX`. Ohne CA gilt der Container-Speicher/`LDAPTLS_CACERT`. Das Env-Bootstrap leitet `use_tls` aus den URLs ab und lässt ein hochgeladenes CA unangetastet. Der Button *Verbindung testen* sitzt neben den Speichern-Buttons (per JS in `#submit-row` eingefügt) und schickt das ungespeicherte Formular an `DirectoryServerTestView`, die `DirectoryServerForm` validiert und `test_connection(form.save(commit=False), form.urls())` aufruft — nichts wird gespeichert.
- **Actions mit Gültigkeitsfenster:** `Action.valid_from/valid_until` (optional); `Action.objects.active()` (Manager) liefert aktivierte Actions im Fenster und wird nur im Milter (`eob`) benutzt — der Vorfilter `build_configuration` bleibt bei `enabled`, damit Grenzen sekundengenau gelten und nicht erst nach `MILTER_CONFIG_TTL`.
- **Eingebettete Bilder:** `SignatureImage.embed` (Standard aus) hängt das Bild in HTML-Teilen als `cid:`-Part an statt es per `MEDIA_BASE_URL` zu verlinken (`_build_image_replacements(…, embedded)`, nur im Milter; Vorschau und Plaintext bleiben bei der URL). `do_action` sammelt die Parts in `_pending_images` und `_attach_images` legt sie in ein Top-Level-`multipart/related` (Entity-Header bleiben am Inhalt, alle anderen wandern nach außen; schon vorhandene Content-IDs werden nicht doppelt angehängt). Ein Bild über 1 MiB, ohne Bild-Typ oder nicht lesbar wird verlinkt (Warnung im Log). Deshalb braucht der Milter das `media`-Volume.
- **Verzeichnis-Bedingungen:** `RequirementCondition` (`kind`: Attribut + Regex oder Gruppe + `group_dn`, UND-verknüpft je `Requirement`, Admin als Inline der eigenständigen `RequirementAdmin`, die per `get_model_perms` aus Dashboard/Sidebar ausgeblendet und über `show_change_link` der Regel erreicht wird — Django kennt keine verschachtelten Inlines). `MilterHelper._failed_directory_conditions` läuft am Ende der Requirement-Filter in `eob` (nur für noch aktive Requirements mit Bedingungen), `_sender_entry` fragt die Server des Mandanten der Absender-Domain (nicht die Actions-Server) einmal pro Mail mit der Attributliste aller Bedingungen. Gruppen: bei Flavor AD fragt `_is_member` den Server pro Gruppe mit `(&<Sender-Query>(memberOf:1.2.840.113556.1.4.1941:=<DN>))` (verschachtelt; Referral-Einträge `(None, …)` zählen nicht), sonst werden die `memberOf`-Werte des Absenders (DN normalisiert: klein, ohne Blanks um `,`/`=`) verglichen — die primäre AD-Gruppe steht nie in `memberOf`. `MilterHelper.condition_log` speist die Anzeige der Signaturtest-Seite. Nicht erreichbar/unbekannt ⇒ Bedingung nicht erfüllt (auch bei Deny: dann greift das Deny nicht), Mail wird nicht zurückgestellt.
- **Rollen:** `disclaimrwebadmin/roles.py` legt die Gruppen `Admins`/`Editor`/`Reader` nach jedem `migrate` an (`post_migrate` in `apps.ready`, nicht per Datenmigration — Rechte existieren dort noch nicht). Rechte werden nur beim Anlegen gesetzt (Anpassungen im Admin bleiben), `manage.py sync_roles --reset` stellt sie wieder her. Reader = `view_` auf Disclaimer/Rule/Requirement/Condition/Action/SignatureImage; Editor = zusätzlich `add_`/`change_` (kein Löschen) und `view_tenant` (das Tenant-Autocomplete der Formulare liefert sonst 403); Admins = alle Rechte von `disclaimrwebadmin` und `auth`. Bewusst kein `view_directoryserver` für Reader/Editor (gespeicherte Bind-Passwörter). Mail-Log/Statistik bleiben superuser-only.
- **SSO (OIDC):** `django-allauth` (nur der `openid_connect`-Provider; immer in `INSTALLED_APPS`, aktiv und geroutet nur mit `OIDC_SERVER_URL`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET`, `settings.OIDC_ENABLED`). Geroutet werden nur `/accounts/oidc/sso/login/` und `…/callback/` (`disclaimrweb/urls.py`), **nicht** allauths Account-Seiten. `disclaimrwebadmin/sso.py`: `SocialAccountAdapter.pre_social_login` legt den Benutzer beim ersten Login selbst an (`is_staff`, kein Passwort, eindeutiger Username via `generate_unique_username`, **keine** Verknüpfung per E-Mail mit lokalen Konten — das allauth-Signup-Flow würde Formulare/Mail-Abgleich verlangen) und ruft bei jedem Login `sync_user`: `SSOGroupMapping`-Gruppen (+ Reader) werden gesetzt/entfernt, ohne Treffer gilt Reader, `is_superuser` = Mitglied von Admins; von Hand vergebene Gruppen bleiben. Gruppen kommen aus `id_token` ∪ `userinfo` (`OIDC_GROUPS_CLAIM`). Fehler/inaktive Konten → Redirect auf den Admin-Login mit Meldung (allauths Fehlerseiten würden an nicht gerouteten URL-Namen scheitern). Login-Button über den Context-Processor `sso_context`. Redirect-URI: `https://<Host>/accounts/oidc/sso/login/callback/` (hinter Proxy `DJANGO_SECURE_COOKIES=true`). Tests laufen mit `tests/settings.py` (setzt die Env-Defaults **und** `OIDC_*`; `pyproject.toml` zeigt darauf, weil die Settings vor jeder `conftest.py` geladen werden). Nicht gegen ein echtes Authentik getestet.
- **Dashboard-Kennzahlen** (`dashboard._mail_stats`, nur Superuser wie das Log selbst) kommen aus `MailLog`: Tage, signiert/unverändert, Top-5 nach identischem `applied`-Text, letzte Mail. Fehler im Milter stehen nicht im Log und fehlen deshalb.
- **E2E-Test** (`tests/e2e/`, CI-Job `e2e`, ca. 2 Minuten): das echte `compose.yml` plus Postfix (`tests/e2e/postfix`, `milter_default_action = tempfail`), Test-LDAP (`ghcr.io/rroemhild/docker-test-openldap`, eigener Healthcheck, Alias `planetexpress.com` passend zum Zertifikat) und Mailpit als Senke; `tests/e2e/run.py` (nur Standardbibliothek) prüft Signatur mit LDAP-Daten, CRLF, Banner-Gültigkeit, Mail-Log und LDAPS ohne/mit gespeicherter CA. Lokal braucht es Docker: `cp .env.example .env`, dann `docker compose -f compose.yml -f tests/e2e/compose.e2e.yml up -d --build --wait` und `python3 tests/e2e/run.py`. Der Test ersetzt nichts, was Unit-Tests abdecken — er fängt, was nur der echte Mailfluss zeigt (erster Fund: eine Methode `_eob` in `DisclaimrMilter` überdeckte die interne `_eob` von python-libmilter; Unit-Tests rufen `eob()` direkt auf und merkten nichts, jede echte Mail wurde zurückgestellt). Neue Regeln erreichen den Milter erst nach `MILTER_CONFIG_TTL` (im E2E auf 1 s). Eine Stalwart-Variante gibt es noch nicht.
- **Ein Verbindungs-Setup für LDAP:** `ldap_helper.open_connection()` (Timeouts, Referrals aus; CA über `LDAPTLS_CACERT`) wird von Milter und Admin-Buttons genutzt. Der Milter-Kindprozess schließt seine DB-Verbindung nach jeder Mail (`eob`/`abort`), gunicorn legt den Heartbeat nach `/dev/shm`.
- **Lokal testen geht doch:** `uv venv --system-certs --python 3.12 C:/dz-venv`, alle Abhängigkeiten außer `python-ldap` installieren und ein Stub-Paket `ldap` (jede Großbuchstaben-Konstante als `LDAPError`-Unterklasse, `ldap.filter.escape_filter_chars`) per `PYTHONPATH` einhängen; dazu `DJANGO_SECRET_KEY=x DATABASE_URL=sqlite:///:memory:`. Damit läuft die ganze Suite (144 Tests) in etwa 15 s.

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

CI (`.github/workflows/ci.yml`): Jobs `lint` (ruff), `test` (pytest, SQLite), `e2e` (siehe unten), `docker` (Build; bei PRs Smoke-Import, bei master-Push Push nach GHCR).

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
- #26 CLAUDE.md
- #27 Milter: bytes-API von python-libmilter, schnellere Pipeline
- #28 UI-Refresh: minimales Theme, Dashboard, Login, eigene Seiten
- #29 Topbar-Labels über gettext, Aufräumen nach #28
- #30 Audit-Must-Fixes: Regex-Validierung, LDAP-Fehler, Log bei Callback-Fehlern, `/media/`, Upload-Prüfung, Milter-Port
- #31 Audit-Should-Fixes: „mindestens ein Empfänger passt“, `7bit`-Fallback, Rechte auf Admin-Views
- #32 Toten Code entfernt, `DJANGO_SECURE_COOKIES`, `.mo` nicht mehr im Repo
- #33 Initiale Migration eingecheckt, CI-Check `makemigrations --check`
- #34 Doku-Refresh, Version 0.1.0, `release.yml`
- #35 `/healthz` + Compose-Healthchecks, `DISCLAIMR_ADMIN_PASSWORD`, Sidebar-Rechte
- #36 Monaco/TinyMCE beim Docker-Build ins Image (CDN nur noch Fallback)
- #37 CLAUDE.md-Stand
- #39 Compose-Refresh: Traefik 3.7, `DISCLAIMR_IMAGE`, `WEB_BIND`, Dev-Start mit `migrate`
- #40 Stalwart-Runbook, `compose.stalwart.yml`, Fix AD-Standardfilter
- #41 LDAPS-CA (`./certs`) in allen Compose-Dateien
- #43 Milter/Stalwart: CRLF-Body, DB-Verbindung pro Mail schließen, ein LDAP-Setup
- Release `v0.1.1` (CHANGELOG, Version in `pyproject.toml` und `disclaimr.py`)
- #45 Mail-Logs-Ansicht
- #46 TLS-Auswahl und CA-Zertifikat je Verzeichnisserver, Passwortfeld-Breite
- Release `v0.1.2` (**defekt**: jede echte Mail wurde zurückgestellt, siehe #50)
- #48 Actions mit Gültigkeitsfenster, Dashboard-Kennzahlen
- #49 End-to-End-Test in der CI (Postfix, Milter, Test-LDAP, Mailpit)
- #50 Fix: `_eob` in `DisclaimrMilter` überdeckte python-libmilters interne Methode
- Release `v0.1.3`
- #52 Eingebettete Signaturbilder (`cid:`)
- #53 Verzeichnis-Bedingungen (Attribut + Regex) an Requirements
- #54 Gruppen-Bedingungen (AD verschachtelt, sonst `memberOf`)
- Release `v0.2.0`
- #56 Ungenutzten systemd-Code aus dem Milter entfernt
- #57 Rollen Admins/Editor/Reader
- #58 SSO per OpenID Connect (allauth) mit Gruppen-Mapping
- Release `v0.3.0`
- #60 Verzeichnisserver: Feld „Hosts“ statt URL-Inline, „Verbindung testen“ mit Formularwerten, Bearbeiten-Spalte
- Release `v0.3.1`

## Releases

Release (zuletzt `v0.3.1`): Version in `pyproject.toml` (`X.Y.Z`) und `disclaimr.py` (`vX.Y.Z`) anheben, CHANGELOG ergänzen und als PR mergen, danach den Tag auf dem grünen `master` setzen (`git tag -a vX.Y.Z -m … && git push origin vX.Y.Z`). Der Tag löst den Image-Build mit Semver-Tags (CI) und das GitHub Release (`.github/workflows/release.yml`) aus; der Workflow bricht ab, wenn Tag und `pyproject.toml`-Version nicht übereinstimmen.

## Offene Punkte (beobachtet, nicht vom User priorisiert)

- Lokale Branches sind alle gemergt; vor neuer Arbeit `git fetch` und von `origin/master` abzweigen.
