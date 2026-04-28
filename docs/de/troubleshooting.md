# Troubleshooting

Symptome zuerst, dann Diagnose. ``docker compose logs web`` und
``docker compose logs milter`` sind deine Freunde — die meisten
Probleme landen dort einen klaren Traceback.

## „Bad Request (400)" im Admin

```
django.core.exceptions.DisallowedHost: Invalid HTTP_HOST header: '192.168.x.x:8000'
```

Dein Hostname/IP fehlt in ``DJANGO_ALLOWED_HOSTS``. In ``.env``
ergänzen:

```dotenv
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,signatures.example.com,192.168.x.x
```

Dann ``docker compose up -d``.

## Admin lädt ohne CSS

Vermutlich ``DJANGO_DEBUG=False`` (korrekt) aber Static Files wurden
nicht eingesammelt. Der Entrypoint ruft ``collectstatic`` automatisch
auf — falls das in der Dev-Umgebung passiert, hilft
``docker compose up --build``. WhiteNoise serviert das Resultat, kein
nginx nötig.

## ``relation "disclaimrwebadmin_…" does not exist``

Die Migrationen der disclaimrwebadmin-App wurden nicht angewendet. Das
Dockerfile ruft ``makemigrations`` zur Build-Zeit, der Entrypoint ruft
``migrate`` beim Boot — stelle sicher dass du auf einem aktuellen
Build bist:

```bash
git pull
docker compose up -d --build
```

Falls du Modellfelder per Hand geändert hast (Working-Copy-Edit):

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

## Signaturtest hängt / 500-Fehler

Zwei wahrscheinliche Ursachen:

1. **Kaputte Regex in einer Requirement.** Ein Pattern wie
   ``*example.com`` (statt ``.*example\.com``) lässt ``re.compile``
   crashen — die Pipeline fängt das jetzt ab und zeigt ein
   freundliches Banner. Die Requirement bearbeiten (Sender /
   Empfänger / Header / Body Feld).
2. **Nicht erreichbarer LDAP-Server.** Connections haben jetzt 5 s
   Timeout pro URL, aber bei N schlechten URLs kann die Antwort bis
   zu N×5 s dauern. Prüfe die konfigurierten DirectoryServer-URLs.

## ``denied`` beim Stack-Start

```
Error response from daemon: pull access denied for ghcr.io/...
```

Das veröffentlichte Image ist (noch) nicht öffentlich (oder der Host
hat kein Internet). Die Compose-Files nutzen ``pull_policy: build``,
so dass ein frischer Checkout lokal baut — einfach:

```bash
docker compose up -d --build
```

## Milter-Container restartet endlos

``docker compose logs milter`` checken. Häufige Gründe:

- ``relation "disclaimrwebadmin_requirement" does not exist`` — siehe
  oben.
- ``ldap.SERVER_DOWN`` — DirectoryServer-URL ist falsch; der Milter
  versucht es alle paar Sekunden erneut.
- ``Address already in use`` — Port 5000 ist auf dem Host belegt. In
  ``compose.yml`` auf einen anderen Port mappen.

## Signatur erschien nicht in der echten Mail

1. **Signaturtest** mit Sender / Empfänger / Body einer Mail laufen
   lassen, die gefeuert haben sollte. Das Result-Panel sagt sofort,
   ob eine Regel matchte.
2. Sagt der Test „keine Regel matchte", obwohl du es erwartet hast —
   öffne die Regel und prüfe die Sender-Regex. ``alice@example.com``
   matcht NICHT ``example\.com`` — du brauchst ``.*@example\.com``.
3. Sagt der Test es matchte, aber die echte Mail bekam nichts — prüfe
   Postfix:
   - ``postconf smtpd_milters`` — zeigt auf den richtigen
     Host:Port?
   - ``postconf milter_default_action`` — sollte ``accept`` sein
     (damit Mails noch durchkommen wenn der Milter aus ist), aber
     **nicht** ``no-action`` (was Milter für manche Events
     komplett überspringt).
   - ``mailq`` und ``cat /var/log/mail.log`` — irgendwelche
     ``milter-reject`` / Connection-Fehler?

## Admin-Passwort zurücksetzen

```bash
docker compose exec web python manage.py bootstrap_admin --reset
```

Banner-gedruckt in ``docker compose logs web``.

## Wo landen hochgeladene Bilder?

Standardmäßig im Docker-Named-Volume ``media``. Für ein Host-Bind-
Mount:

```dotenv
MEDIA_HOST_PATH=/srv/disclaimrng/media
```

Dateien liegen unter ``signatures/<slug>/<filename>``. Re-Upload mit
gleichem Slug löscht die alte Datei nicht — alte Versionen bleiben auf
Platte bis du sie manuell entfernst.
