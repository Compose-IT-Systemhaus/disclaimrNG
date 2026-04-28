# Installation

disclaimrNG läuft als Docker-Compose-Stack mit drei Services:

- **db** — PostgreSQL 16 (Named-Volume ``pgdata``)
- **web** — Django-Admin + die API-Endpunkte, die der Milter nutzt
- **milter** — libmilter-Daemon, lauscht auf TCP 5000

## Schnellstart

```bash
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git
cd disclaimrNG
cp .env.example .env
# .env editieren — mindestens DJANGO_SECRET_KEY, POSTGRES_PASSWORD setzen
# und deinen Hostnamen/IP zu DJANGO_ALLOWED_HOSTS hinzufügen
docker compose up -d
```

Beim ersten Boot:

- werden alle Migrationen ausgeführt,
- wird der Admin-User angelegt (siehe **`docker compose logs web`** für
  das einmalige Passwort — Banner-Format
  ``[bootstrap_admin] one-time password: <pw>``),
- läuft ``collectstatic``,
- startet gunicorn auf Port 8000 und der Milter auf Port 5000.

Browse zu ``http://<dein-host>:8000/`` und logge dich als ``admin`` mit
dem generierten Passwort ein. Ändere es sofort über
``/admin/password_change/``.

## Reverse Proxy mit Traefik

Eine eigenständige Alternative-Compose-Datei liegt unter
[``compose.traefik.yml``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/compose.traefik.yml)
bei. Sie stellt das Web-UI hinter Traefik mit automatischen
Let's-Encrypt-Zertifikaten. Statt der Standard-Compose starten:

```bash
# In .env ergänzen:
DISCLAIMR_HOSTNAME=signatures.example.com
ACME_EMAIL=ops@example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://signatures.example.com
MEDIA_BASE_URL=https://signatures.example.com/media

docker compose -f compose.traefik.yml up -d
```

Der Milter lauscht weiterhin direkt auf TCP 5000 — Postfix spricht
libmilter, nicht HTTP, daher läuft das nicht durch den Proxy.

## Postfix anbinden

In ``main.cf``:

```
smtpd_milters = inet:disclaimrng:5000
non_smtpd_milters = inet:disclaimrng:5000
milter_default_action = accept
milter_protocol = 6
```

Ersetze ``disclaimrng`` mit dem Hostnamen oder der IP des
Milter-Containers.

## Erforderliche Umgebungsvariablen

| Variable | Pflicht | Default | Notiz |
|---|---|---|---|
| ``DJANGO_SECRET_KEY`` | ja | — | ``python -c 'import secrets; print(secrets.token_urlsafe(64))'`` |
| ``DJANGO_ALLOWED_HOSTS`` | ja | ``localhost,127.0.0.1`` | Komma-getrennt, **muss** den Host enthalten, über den du das Admin erreichst |
| ``DJANGO_CSRF_TRUSTED_ORIGINS`` | ja | ``http://localhost:8000`` | Origins (Schema + Host[:Port]) für Cross-Site-Forms |
| ``POSTGRES_PASSWORD`` | ja | — | Wird vom db-Service genutzt *und* von Django geparst |
| ``DATABASE_URL`` | ja | — | Connection-String; Hostname = Compose-Service-Name |
| ``MILTER_SOCKET`` | nein | ``inet:0.0.0.0:5000`` | Wo der Milter bindet |
| ``MEDIA_BASE_URL`` | empfohlen | (leer) | Absolute URL, vor Bildpfade in gerenderten Mails gestellt |

Siehe [``.env.example``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/.env.example)
für die vollständige kommentierte Liste, inkl. LDAP- und Tenant-Bootstrap.

## Aktualisieren

```bash
git pull
docker compose pull        # falls du das Registry-Image nutzt
docker compose up -d --build
```

Migrationen laufen automatisch beim nächsten ``web``-Boot.
