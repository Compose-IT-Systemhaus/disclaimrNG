# Verzeichnisserver

Ein **DirectoryServer** speichert die Verbindungsdaten eines LDAP-
oder Active-Directory-Backends. Die Milter-Pipeline bindet dagegen,
um die Kontaktdaten des Absenders abzufragen, die dann über
``{resolver["…"]}``-Platzhalter in die Signatur eingesetzt werden.

## Verzeichnisserver im Admin anlegen

**Settings → Verzeichnisserver → Verzeichnisserver hinzufügen**.

Das Formular hat vier Abschnitte:

- **Identität** — Name (nur Anzeige), Description, Aktiviert-Flag,
  optional Tenant-Verknüpfung.
- **Verbindung**
  - **Variante** — *LDAP* (vanilla OpenLDAP/389DS), *Active
    Directory* oder *Eigene*. AD/LDAP füllen sinnvolle Defaults für
    Suchanfrage und Attributliste; *Eigene* lässt sie leer.
  - **Base DN** — z. B. ``dc=acme,dc=com``.
  - **Authentifizierungsmethode** — *Keine* (anonymer Bind) oder
    *Einfach* (DN + Passwort).
  - **Benutzer-DN** / **Passwort** — nur bei *Einfach*.
- **Anfrage**
  - **Suchanfrage** — parametrisierter Filter; ``%s`` wird zur
    Laufzeit durch die Absender-Mail-Adresse ersetzt. AD-Default:
    ``(userPrincipalName=%s)``. LDAP-Default: ``mail=%s``.
  - **Attributliste** — komma- oder zeilengetrennte Attributnamen,
    die in der Editor-Autovervollständigung sichtbar werden
    (``cn, mail, telephoneNumber, …``). Leer = Variante-Defaults.
- **Cache** — Milter-seitiger Query-Cache; Default an, 1 Stunde TTL.

Im Inline unten mindestens eine **URL** eintragen — z. B.
``ldaps://dc1.acme.com``. Mehrere URLs werden bei Failure in
Reihenfolge probiert (HA).

## Test-Connection und Discover-Attributes Buttons

Im Change-Form (pro Server) liegen zwei Buttons über dem Formular:

- **Test connection** — bindet an jede konfigurierte URL und meldet
  pro URL das Ergebnis (``bind ok``, ``unreachable: …``, ``invalid
  credentials``, ``base DN not found``, ``ldap error: …``).
- **Discover attributes** — sampelt fünf echte Einträge unter dem
  Base-DN und liefert die Vereinigung der gefundenen Attributnamen.
  Damit kann man bequem die *Attributliste* befüllen.

Beide Buttons sind admin-only und POST-only (CSRF-geschützt).

## Bootstrap per Env-Variablen

```dotenv
LDAP_SERVERS=acme_ad
LDAP_SERVER_ACME_AD_FLAVOR=ad
LDAP_SERVER_ACME_AD_BASE_DN=dc=acme,dc=com
LDAP_SERVER_ACME_AD_URL=ldaps://dc1.acme.com,ldaps://dc2.acme.com
LDAP_SERVER_ACME_AD_BIND_DN=CN=disclaimr,OU=Service,DC=acme,DC=com
LDAP_SERVER_ACME_AD_BIND_PASSWORD=change-me
LDAP_SERVER_ACME_AD_TENANT=acme   # verknüpft mit Acme-Tenant
```

Pro Handle (``<HANDLE>`` mit dem uppercased-Handle ersetzen):

| Variable | Default | Notiz |
|---|---|---|
| ``LDAP_SERVER_<HANDLE>_NAME`` | Handle, title-cased | |
| ``LDAP_SERVER_<HANDLE>_DESCRIPTION`` | leer | |
| ``LDAP_SERVER_<HANDLE>_FLAVOR`` | ``ldap`` | ``ldap`` / ``ad`` / ``custom`` |
| ``LDAP_SERVER_<HANDLE>_BASE_DN`` | **Pflicht** | |
| ``LDAP_SERVER_<HANDLE>_URL`` | **Pflicht** | Komma-getrennt für Failover |
| ``LDAP_SERVER_<HANDLE>_BIND_DN`` | leer (anonym) | |
| ``LDAP_SERVER_<HANDLE>_BIND_PASSWORD`` | leer | |
| ``LDAP_SERVER_<HANDLE>_SEARCH_QUERY`` | Variante-Default | |
| ``LDAP_SERVER_<HANDLE>_SEARCH_ATTRIBUTES`` | Variante-Default | |
| ``LDAP_SERVER_<HANDLE>_ENABLE_CACHE`` | ``true`` | |
| ``LDAP_SERVER_<HANDLE>_CACHE_TIMEOUT`` | 3600 | Sekunden |
| ``LDAP_SERVER_<HANDLE>_ENABLED`` | ``true`` | |
| ``LDAP_SERVER_<HANDLE>_TENANT`` | leer | Tenant-Slug zur Verknüpfung |

``manage.py sync_directory_servers`` läuft bei jedem Web-Boot mit
gesetztem ``LDAP_SERVERS``. ``LDAP_SYNC_PRUNE=1`` löscht
env-verwaltete Einträge, die nicht mehr auftauchen.

## Begrenzte Timeouts

Jede Connection wird mit ``OPT_NETWORK_TIMEOUT=5`` und
``OPT_TIMEOUT=5`` geöffnet, damit ein nicht-erreichbarer LDAP-Server
weder den Milter noch das synchrone Signaturtest-Admin-View länger als
ein paar Sekunden hängen lassen kann. Werte ggf. höher setzen in
[``milter_helper.py``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/disclaimr/milter_helper.py)
falls dein LDAP wirklich länger braucht.
