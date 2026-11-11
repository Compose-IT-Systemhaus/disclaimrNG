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
  - **Hosts** — Hostname oder IP-Adresse des Servers, optional mit
    ``:Port``, z. B. ``dc1.acme.com``. Einer pro Zeile; weitere Zeilen werden
    der Reihe nach versucht, wenn der erste nicht antwortet. Die URL baut
    disclaimrNG selbst.
  - **Verbindung verschlüsseln (TLS)** — standardmäßig an: ``ldaps://``
    (Port 636). Aus: ``ldap://`` (Port 389), und alles — auch das
    Bind-Passwort — läuft unverschlüsselt.
  - **Base DN** — z. B. ``dc=acme,dc=com``.
  - **CA-Zertifikatsdatei** / **CA-Zertifikat** — nur mit TLS. PEM-Datei
    der CA, die das Serverzertifikat ausgestellt hat, hochladen (oder den
    PEM-Text einfügen). Sie liegt in der Datenbank und gilt für diesen Server,
    im Milter wie bei den Admin-Buttons. Leer: der CA-Speicher des Containers.
  - **Authentifizierungsmethode** — *Keine* (anonymer Bind) oder
    *Einfach* (DN + Passwort).
  - **Benutzer-DN** / **Passwort** — nur bei *Einfach*.
- **Anfrage**
  - **Suchanfrage** — parametrisierter Filter; ``%s`` wird zur
    Laufzeit durch die Absender-Mail-Adresse ersetzt. AD-Default:
    ``(|(mail=%s)(userPrincipalName=%s))``. LDAP-Default: ``mail=%s``.
  - **Attributliste** — komma- oder zeilengetrennte Attributnamen,
    die in der Editor-Autovervollständigung sichtbar werden
    (``cn, mail, telephoneNumber, …``). Leer = Variante-Defaults.
- **Cache** — Milter-seitiger Query-Cache; Default an, 1 Stunde TTL.

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

## LDAPS mit privater CA

``ldaps://``-URLs werden gegen ein CA-Zertifikat geprüft. Der übliche Weg ist das Feld
**CA-Zertifikat** am Verzeichnisserver (Upload im Admin, siehe oben): es gilt nur für diesen
Server. Für eine CA, die für **alle** Verzeichnisserver gelten soll, oder wenn du Server
über Umgebungsvariablen anlegst, nimm den CA-Speicher des Containers:

1. Lege das CA-Zertifikat (PEM, Zwischenzertifikate angehängt) unter
   ``./certs/ad-ca.pem`` neben der ``compose.yml`` ab. Die Compose-Dateien binden
   ``./certs`` read-only in ``web`` und ``milter`` ein.
2. Neu starten: ``docker compose up -d``. Der Entrypoint findet
   ``/etc/ssl/ad/ad-ca.pem`` und setzt ``LDAPTLS_CACERT``; im Log steht
   ``LDAPS: trusting the CA``.
3. **Test connection** am Verzeichnisserver muss ``bind + base search ok`` zeigen.

Ein in der ``.env`` gesetztes ``LDAPTLS_CACERT`` hat Vorrang. Die Datei ersetzt für
LDAP-Verbindungen die System-Roots — für ein internes Verzeichnis ist das gewollt.
Reines ``ldap://`` mit STARTTLS wird nicht unterstützt — nutze ``ldaps://``.

## Begrenzte Timeouts

Jede Connection wird mit ``OPT_NETWORK_TIMEOUT=5`` und
``OPT_TIMEOUT=5`` geöffnet, damit ein nicht-erreichbarer LDAP-Server
weder den Milter noch das synchrone Signaturtest-Admin-View länger als
ein paar Sekunden hängen lassen kann. Werte ggf. höher setzen in
[``milter_helper.py``](https://github.com/Compose-IT-Systemhaus/disclaimrNG/blob/master/disclaimr/milter_helper.py)
falls dein LDAP wirklich länger braucht.
