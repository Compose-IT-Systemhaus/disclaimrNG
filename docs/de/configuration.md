# Konfiguration

Sämtliche Laufzeit-Konfiguration läuft über Umgebungsvariablen
(12-Factor). Vorlagen, Regeln, Requirements und Verzeichnisserver
selbst leben in PostgreSQL und werden über das Admin verwaltet.

## First-Boot-Admin-User

Der Entrypoint des Web-Containers ruft nach ``migrate`` automatisch
``manage.py bootstrap_admin`` auf:

- existiert **irgendein** Superuser, passiert nichts,
- sonst wird ``admin`` angelegt mit einem frisch generierten
  24-Zeichen-``secrets.token_urlsafe``-Passwort.

Das Passwort wird in einem auffälligen Banner ins Log geschrieben:

```
========================================================================
[bootstrap_admin] superuser 'admin' created.
[bootstrap_admin] one-time password: a8ghNZI8UN7kX84z0EPOS-pI
[bootstrap_admin] log in and change it at /admin/password_change/
========================================================================
```

Beim ersten Boot vergessen es zu kopieren? Reset:

```bash
docker compose exec web python manage.py bootstrap_admin --reset
```

Erzeugt ``admin`` mit frischem Passwort, auch wenn andere Superuser
existieren.

Lieber ein eigenes Passwort? Setze ``DISCLAIMR_ADMIN_PASSWORD`` in der
``.env`` vor dem ersten Start. Es wird statt eines generierten verwendet
(auch bei ``--reset``) und **nicht** ins Log geschrieben.

## Wichtige Django-Settings

| Setting | Zweck |
|---|---|
| ``DJANGO_DEBUG`` | In Produktion immer ``False``. ``True`` nur lokal — zeigt Tracebacks. |
| ``DJANGO_LOG_LEVEL`` | Default ``INFO``; ``DEBUG`` falls Milter-Entscheidungen nachverfolgt werden müssen. |
| ``DJANGO_TIME_ZONE`` | Alle Zeitstempel und Date-Picker im Admin nutzen das. Default ``Europe/Berlin``. |
| ``DJANGO_LANGUAGE_CODE`` | Default-UI-Sprache; Admins können über die Topbar-Flagge umschalten. |
| ``MILTER_CONFIG_TTL`` | Sekunden, nach denen der Milter den Sender-IP-Vorfilter neu aus der DB lädt (Default ``60``). Neue oder geänderte Requirements greifen so ohne Neustart. |
| ``MAIL_LOG_RETENTION_DAYS`` | Tage, die die Mail-Logs aufbewahrt werden (Default ``30``, ``0`` = unbegrenzt). |

## Static Files

Werden von [WhiteNoise](https://whitenoise.evans.io) direkt aus
gunicorn ausgeliefert — kein separates nginx nötig. ``collectstatic``
läuft bei jedem Boot.

Die Editor-Bibliotheken Monaco / TinyMCE gehören zum Image: der Docker-Build
lädt gepinnte Versionen aus der npm-Registry (mit Prüfsumme) in die
statischen Dateien, der Admin braucht zur Laufzeit also keinen
Internet-Zugang. Der Build selbst braucht Internet. Wird der Quellbaum über
`/app` gemountet (so wie in der Dev-Compose-Datei), ist dieser Ordner
verdeckt und der Editor lädt dieselben Versionen vom **jsdelivr-CDN**.

## Medien-Uploads (Signatur-Bilder)

``MEDIA_BASE_URL`` muss auf die **öffentliche** absolute URL gesetzt
werden, z. B. ``https://signatures.example.com``. Mails fliegen durch
MTAs, die nichts von deinem internen Netzwerk wissen — relative URLs
sind nutzlos.

```dotenv
# .env
MEDIA_BASE_URL=https://signatures.example.com
```

Standardmäßig liegen hochgeladene Bilder in einem Docker-Named-Volume.
Für ein Host-Bind-Mount (z. B. für Backups):

```dotenv
MEDIA_HOST_PATH=/srv/disclaimrng/media
```

## Tenants und LDAP-Server per Env-Variablen bootstrappen

Beides geht deklarativ — nützlich für Compose, Helm, Ansible. Siehe:

- [Tenants](../tenants/) für das ``TENANTS=...``-Schema
- [Verzeichnisserver](../directory-servers/) für ``LDAP_SERVERS=...``

``manage.py sync_tenants`` und ``manage.py sync_directory_servers``
laufen automatisch bei jedem Web-Container-Boot, wenn die jeweilige
Env-Variable gesetzt ist. ``TENANT_SYNC_PRUNE=1`` /
``LDAP_SYNC_PRUNE=1`` löscht env-verwaltete Einträge, die aus der Env
verschwunden sind (manuell angelegte Einträge bleiben unangetastet —
sie werden anhand des ``[env-managed]``-Markers in der Description
erkannt).
