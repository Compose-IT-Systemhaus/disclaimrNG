# Runbook — disclaimrNG mit Stalwart 1.0 und Active Directory

Schritt für Schritt: ausgehende Mails, die Benutzer über **Stalwart 1.0**
einliefern, bekommen eine Signatur mit Daten aus dem **Active Directory**.
Stalwart und disclaimrNG laufen als Docker-Container auf **demselben Host**.

> **Stand.** Am 11. 11. 2026 getestet mit Stalwart 1.0, einem Active Directory mit
> LDAPS und interner CA sowie echten Postfächern (disclaimrNG 0.3.3). Den Abnahmetest
> in [Schritt 8](#schritt-8-abnahme) trotzdem im eigenen Setup durchführen. Weichen
> Menü- oder Feldnamen in einer neueren Stalwart-Version ab, mit der
> [Stalwart-Doku](https://stalw.art/docs/) abgleichen.

## 0. Überblick

```
 Mail-Client ──465 (Login)──► Stalwart ──DATA-Stage──► disclaimrNG-Milter
                                 │   │                  (disclaimrng-milter:5000)
                  LDAPS 636      │   │                          │  LDAPS 636
              (Login, Empfänger) │   └─ Queue: DKIM-Signatur,   │  (Absenderdaten)
                                 ▼      dann Zustellung         ▼
                              Active Directory  ◄───────────────┘
```

Was man dazu wissen muss:

- Stalwart hat **keine Filterstufe für die ausgehende Zustellung**. Milter laufen
  bei der **Einlieferung** (auch bei authentifizierten Sessions auf Port 465/587).
  Dort hängt disclaimrNG die Signatur an; **danach** signiert Stalwart die Mail
  mit DKIM. Die Signatur ist also Teil der DKIM-signierten Nachricht.
- Der Milter wird nur auf der **DATA-Stage** gefragt. Stalwart öffnet dazu eine
  Verbindung und schickt Verbindungsdaten, EHLO, Absender, Empfänger, Header und
  Body in einem Rutsch — mehr braucht disclaimrNG nicht.
- Stalwart schickt auf der DATA-Stage keine Queue-ID. Das ist unkritisch: disclaimrNG
  nutzt sie nur für Logzeilen.
- **Zwei** AD-Verbindungen, mit **zwei** Dienstkonten: Stalwart (Anmeldung der
  Benutzer, Empfängerprüfung) und disclaimrNG (Absenderdaten für die Signatur).

Platzhalter in diesem Runbook — bitte durch eigene Werte ersetzen:

| Platzhalter | Beispiel |
|---|---|
| Mail-Domain | `example.com` |
| Mail-Hostname von Stalwart | `mail.example.com` |
| AD-Domäne / Base DN | `corp.example.com` / `DC=corp,DC=example,DC=com` |
| Domänencontroller | `dc1.corp.example.com`, `dc2.corp.example.com` |
| Verzeichnis auf dem Docker-Host | `/opt/disclaimrng` (disclaimrNG), `/opt/stalwart` (Stalwart) |
| Docker-Netz für beide Stacks | `mailnet` |

## 1. Voraussetzungen

| Prüfpunkt | Wie prüfen |
|---|---|
| Docker Engine mit Compose-Plugin auf dem Host | `docker compose version` |
| Host erreicht die Domänencontroller auf **636/tcp** (LDAPS) | `openssl s_client -connect dc1.corp.example.com:636 </dev/null` |
| LDAPS auf den DCs ist aktiv (Zertifikat vorhanden) | siehe [Schritt 1](#schritt-1-active-directory-vorbereiten) |
| Benutzer haben im AD das Attribut **`mail`** gesetzt | siehe [Schritt 1](#schritt-1-active-directory-vorbereiten) |
| Stalwart 1.0 läuft oder ist installiert (Mail-DNS, MX, Zertifikat) | [Stalwart: Docker](https://stalw.art/docs/install/platform/docker/) |
| Port 8000 (disclaimrNG-Admin) soll **nicht** öffentlich erreichbar sein | Zugriff per VPN oder SSH-Tunnel |

> Stalwart belegt auf dem Host die Ports 25, 465, 993, 995, 4190 und **443**.
> `compose.traefik.yml` von disclaimrNG (ebenfalls 443) ist auf diesem Host daher
> keine Option; nutze `compose.yml`.

## Schritt 1: Active Directory vorbereiten

### 1.1 Zwei Dienstkonten anlegen

Beide Konten brauchen nur **Lesezugriff** (jeder authentifizierte Benutzer darf
im AD standardmäßig lesen). Auf einem Domänencontroller in PowerShell:

```powershell
$ou = "OU=Service Accounts,DC=corp,DC=example,DC=com"

foreach ($name in "svc-stalwart", "svc-disclaimr") {
    New-ADUser -Name $name -SamAccountName $name `
        -UserPrincipalName "$name@corp.example.com" -Path $ou `
        -AccountPassword (Read-Host -AsSecureString "Passwort für $name") `
        -Enabled $true -PasswordNeverExpires $true -CannotChangePassword $true
}
```

Zwei getrennte Konten, damit sich Passwörter einzeln rotieren lassen und im
AD-Log erkennbar ist, wer fragt. Die Konten dürfen **keine** Gruppen mit
Schreibrechten bekommen.

### 1.2 E-Mail-Attribut prüfen

disclaimrNG sucht den Absender über die Envelope-Adresse, Stalwart den Empfänger
über `mail`. Benutzer ohne `mail` bekommen also weder Daten in der Signatur noch
Mail in Stalwart.

```powershell
# Benutzer OHNE mail-Attribut finden
Get-ADUser -Filter 'Enabled -eq $true' -Properties mail |
    Where-Object { -not $_.mail } | Select-Object SamAccountName

# Fehlendes Attribut setzen
Set-ADUser jdoe -EmailAddress "jdoe@example.com"
```

Für die Signatur sollten außerdem `displayName`, `title`, `telephoneNumber` (und
was ihr sonst anzeigt) gepflegt sein.

### 1.3 LDAPS prüfen und CA-Zertifikat exportieren

disclaimrNG und Stalwart sprechen **LDAPS (636)**. Klartext-LDAP ist keine Option:
disclaimrNG unterstützt kein STARTTLS, und Domänencontroller verlangen für
Simple Binds meist LDAPS oder Signing.

1. Exportiere das **Root-CA-Zertifikat**, das die DC-Zertifikate ausgestellt hat,
   Base-64-codiert (PEM), z. B. über `certlm.msc` → *Vertrauenswürdige
   Stammzertifizierungsstellen* → Zertifikat → *Alle Aufgaben → Exportieren*.
   Gibt es Zwischenzertifizierungsstellen, hänge sie in derselben Datei an.
   Alternative in PowerShell auf dem CA-Server (die Anführungszeichen sind nötig,
   sonst zerlegt PowerShell `-ca.cert`): `certutil '-ca.cert' C:\Temp\ca.cer`, oder
   auf jedem Domänenrechner `certutil -store Root "<CA-Name>" C:\Temp\ca.cer`; danach
   `certutil -encode C:\Temp\ca.cer C:\Temp\ad-ca.pem`. Es muss das Zertifikat der
   **CA** sein (Aussteller des DC-Zertifikats), nicht das DC-Zertifikat selbst — der
   häufigste Fehler im Live-Test.
2. Lege die Datei auf dem Docker-Host ab:

   ```bash
   sudo mkdir -p /opt/disclaimrng/certs
   sudo cp ad-ca.pem /opt/disclaimrng/certs/ad-ca.pem
   ```
3. Prüfe die Kette vom Host aus:

   ```bash
   openssl s_client -connect dc1.corp.example.com:636 \
       -CAfile /opt/disclaimrng/certs/ad-ca.pem </dev/null 2>&1 | grep "Verify return code"
   ```

   Erwartet: `Verify return code: 0 (ok)`. Der Name im Zertifikat muss zum
   Hostnamen passen, den du später in der URL verwendest (`dc1.corp.example.com`,
   nicht die IP).

## Schritt 2: Gemeinsames Docker-Netz

Stalwart erreicht den Milter nur, wenn beide Container im selben Docker-Netz
hängen. (`127.0.0.1` auf dem Host hilft nicht: der Milter-Port ist dort nur für
Prozesse auf dem Host sichtbar, nicht aus einem anderen Container heraus.)

```bash
docker network create mailnet
```

Hänge den Stalwart-Container in dieses Netz — im Compose-File von Stalwart:

```yaml
services:
  stalwart:
    # ... bestehende Einstellungen ...
    networks:
      - default
      - mailnet

networks:
  mailnet:
    external: true
```

```bash
cd /opt/stalwart && docker compose up -d
docker network inspect mailnet --format '{{range .Containers}}{{.Name}} {{end}}'
```

Der Name `stalwart` muss in der Ausgabe stehen. (`docker network connect mailnet
stalwart` geht auch, überlebt aber kein Neuanlegen des Containers.)

## Schritt 3: Stalwart mit AD-Verzeichnis

Die Installation von Stalwart selbst (Wizard, DNS, Zertifikat) beschreibt die
[Stalwart-Docker-Anleitung](https://stalw.art/docs/install/platform/docker/).
Hier nur das, was für diesen Aufbau zählt.

### 3.1 Wizard: internes Verzeichnis wählen

Wähle im Wizard (Bildschirm 3) **„Use the internal directory“**. Damit entsteht
das Administratorkonto `admin@example.com`, mit dem du dich anmeldest. Das AD
wird erst danach als Verzeichnis eingehängt.

### 3.2 Wiederherstellungs-Administrator als Rückfallebene

Sobald ein externes Verzeichnis aktiv ist, entstehen Konten erst bei der ersten
Anmeldung, und ein Konto aus dem AD bekommt nicht automatisch Adminrechte. Setze
deshalb während der Umstellung einen Wiederherstellungs-Administrator (Details:
[Docker-Anleitung, Abschnitt *Special cases › External directory*](https://stalw.art/docs/install/platform/docker/#external-directory)):

```yaml
    environment:
      STALWART_RECOVERY_ADMIN: "admin:<langes-passwort>"
      LDAP_BIND_PASSWORD: "<passwort von svc-stalwart>"
```

Das Passwort von `svc-stalwart` kommt ebenfalls als Umgebungsvariable in den
Container, damit es nicht in der Stalwart-Konfiguration steht. Container neu
anlegen (`docker compose up -d`). **Nach** Abschluss von Schritt 3 entfernst du
`STALWART_RECOVERY_ADMIN` wieder.

### 3.3 Verzeichnis anlegen

WebUI: `https://mail.example.com/admin` → **Settings › Authentication ›
Directories** → neues Verzeichnis vom Typ **Ldap**. Als Objekt (JSON-Form der
Stalwart-Doku, [LDAP Server](https://stalw.art/docs/auth/backend/ldap/)):

```json
{
  "@type": "Ldap",
  "description": "Active Directory",
  "url": "ldaps://dc1.corp.example.com",
  "urlFailover": {"ldaps://dc2.corp.example.com": true},
  "baseDn": "DC=corp,DC=example,DC=com",
  "bindDn": "CN=svc-stalwart,OU=Service Accounts,DC=corp,DC=example,DC=com",
  "bindSecret": {"@type": "EnvironmentVariable", "variableName": "LDAP_BIND_PASSWORD"},
  "bindAuthentication": true,
  "filterLogin": "(&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2))(|(mail=?)(userPrincipalName=?)))",
  "filterRecipient": "(|(&(objectClass=user)(mail=?))(&(objectClass=group)(mail=?)))",
  "filterMemberOf": "(&(objectClass=group)(member=?))",
  "attrEmail": {"mail": true},
  "attrDescription": {"displayName": true},
  "attrMemberOf": {"memberOf": true},
  "attrSecretChanged": {"pwdLastSet": true},
  "groupClass": "group"
}
```

Erklärt:

- `filterLogin` erlaubt die Anmeldung mit der **E-Mail-Adresse oder dem UPN** und
  schließt **deaktivierte** Konten aus (`userAccountControl`-Bit 2). Stalwart-Clients
  melden sich mit der vollen E-Mail-Adresse an.
- `urlFailover` (zweiter DC) ist ein **Enterprise-Feature** von Stalwart. In der
  Community-Edition die Zeile weglassen und nur `url` setzen.
- AD verrät keine Passwort-Hashes, deshalb `bindAuthentication: true` (der Standard).

Danach das Verzeichnis als Authentifizierungsverzeichnis wählen (**Settings ›
Authentication**, Feld *Directory* / `directoryId`).

### 3.4 Vertrauen in die AD-CA

Stalwart muss dem Zertifikat der Domänencontroller trauen. Wie Stalwart eine
**private CA** aufnimmt, ist in der Stalwart-Doku nicht beschrieben. Vorgehen in
dieser Reihenfolge:

1. **CA ins Truststore des Containers.** Binde die CA-Datei ein und setze
   `SSL_CERT_FILE` auf ein Bündel aus den öffentlichen Root-Zertifikaten **plus**
   deiner AD-CA. Ein Bündel, das nur die AD-CA enthält, würde Stalwarts
   Verbindungen zu Let's Encrypt und GitHub brechen.

   ```bash
   cat /etc/ssl/certs/ca-certificates.crt /opt/disclaimrng/certs/ad-ca.pem \
       > /opt/stalwart/ca-bundle.pem
   ```

   ```yaml
       environment:
         SSL_CERT_FILE: /etc/ssl/stalwart-ca-bundle.pem
       volumes:
         - ./ca-bundle.pem:/etc/ssl/stalwart-ca-bundle.pem:ro
   ```
2. Anmeldetest mit einem AD-Benutzer (Schritt 3.5). Meldet Stalwart einen
   Zertifikatsfehler (`store.ldap-…` im Log, `docker logs stalwart`), wirkt die
   Variante nicht.
3. **Nur zum Testen:** `allowInvalidCerts: true` am Verzeichnis schaltet die
   Prüfung ab. Nicht produktiv lassen — Passwörter laufen über diese Verbindung.

### 3.5 Anmeldung testen und Administrator zuweisen

1. Melde dich mit einem AD-Benutzer an (`https://mail.example.com/account`,
   Benutzername = `jdoe@example.com`). Beim ersten Mal legt Stalwart das lokale
   Konto an.
2. Melde dich als Wiederherstellungs-Administrator an und weise dem Konto des
   künftigen Administrators eine Administratorrolle zu
   (Docker-Anleitung, Abschnitt *Special cases › External directory*).
3. Entferne `STALWART_RECOVERY_ADMIN` aus dem Compose-File, `docker compose up -d`.

## Schritt 4: disclaimrNG installieren

```bash
cd /opt
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git disclaimrng
cd disclaimrng
git checkout v0.3.3            # der aktuelle Release-Tag
cp .env.example .env
chmod 600 .env
```

`ad-ca.pem` liegt bereits unter `/opt/disclaimrng/certs/` (Schritt 1.3); Compose
bindet dieses Verzeichnis ein.

Trage in `.env` mindestens ein (Beispielwerte ersetzen, Passwörter selbst erzeugen,
z. B. `openssl rand -base64 33`):

```dotenv
DJANGO_SECRET_KEY=<openssl rand -base64 48>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
DJANGO_TIME_ZONE=Europe/Berlin
DJANGO_LANGUAGE_CODE=de

POSTGRES_PASSWORD=<passwort>
DATABASE_URL=postgres://disclaimr:<passwort>@db:5432/disclaimr

# Admin-Oberfläche nur lokal: Zugriff per SSH-Tunnel (ssh -L 8000:127.0.0.1:8000 host)
WEB_BIND=127.0.0.1

# Mandant und Active Directory deklarativ anlegen
TENANTS=example
TENANT_EXAMPLE_NAME=Example
TENANT_EXAMPLE_DOMAINS=example.com

LDAP_SERVERS=ad
LDAP_SERVER_AD_NAME=Active Directory
LDAP_SERVER_AD_FLAVOR=ad
LDAP_SERVER_AD_BASE_DN=DC=corp,DC=example,DC=com
LDAP_SERVER_AD_URL=ldaps://dc1.corp.example.com,ldaps://dc2.corp.example.com
LDAP_SERVER_AD_BIND_DN=CN=svc-disclaimr,OU=Service Accounts,DC=corp,DC=example,DC=com
LDAP_SERVER_AD_BIND_PASSWORD=<passwort von svc-disclaimr>
LDAP_SERVER_AD_TENANT=example
```

Die Variablen sind in [Verzeichnisserver](../directory-servers/) und
[Mandanten](../tenants/) beschrieben. Der Tenant ordnet die Absender-Domain dem
AD zu; sonst müsstest du das Verzeichnis in jeder Action einzeln wählen.

> Der AD-Standard-Suchfilter von disclaimrNG ist
> `(|(mail=%s)(userPrincipalName=%s))`. Nutzen eure Benutzer Alias-Adressen
> (`proxyAddresses`), setze `LDAP_SERVER_AD_SEARCH_QUERY` auf
> `(|(mail=%s)(userPrincipalName=%s)(proxyAddresses=smtp:%s))`.

### 4.1 Compose-Overlay für Stalwart

Im Repository liegt `compose.stalwart.yml`. Es hängt den **Milter** mit dem Namen
`disclaimrng-milter` in das Netz `mailnet`. Die AD-CA braucht kein Overlay: `compose.yml`
bindet das Verzeichnis `./certs` in `web` und `milter` ein, und der Entrypoint setzt
`LDAPTLS_CACERT` automatisch, sobald dort `ad-ca.pem` liegt (Schritt 1.3). Im Log steht
dann `LDAPS: trusting the CA in /etc/ssl/ad/ad-ca.pem`.
Alternativ lädst du die CA am Verzeichnisserver im Admin hoch (Feld *CA-Zertifikatsdatei*);
sie gilt dann nur für diesen Server und braucht keinen Mount.

```bash
docker compose -f compose.yml -f compose.stalwart.yml up -d --build
docker compose -f compose.yml -f compose.stalwart.yml ps
```

Erwartet: `db`, `web` und `milter` mit Status `healthy`. Beim ersten Start
`docker compose logs web | grep -A3 -i password` für das Admin-Passwort.

> Verwende ab jetzt für **alle** Compose-Befehle beide `-f`-Dateien (oder setze
> `COMPOSE_FILE=compose.yml:compose.stalwart.yml` in der `.env`).

Prüfe, dass Stalwarts Netz den Milter sieht:

```bash
docker run --rm --network mailnet python:3.12-slim python -c \
  "import socket; socket.create_connection(('disclaimrng-milter', 5000), 3).close(); print('Milter erreichbar')"
```

## Schritt 5: Signatur und Regel in disclaimrNG

Öffne die Admin-Oberfläche über den SSH-Tunnel (`http://localhost:8000/`), melde
dich als `admin` an und ändere das Passwort. Unter **Settings → Directory servers →
Active Directory** den Button **Test connection** drücken: erwartet `bind + base
search ok` für beide URLs. Dann **Discover attributes** — das füllt den
Platzhalter-Editor mit echten AD-Attributen.

Signatur, Regel und Action baust du wie im [Walkthrough](../walkthrough/)
(Schritte 3 bis 6). Für diesen Aufbau gelten folgende Werte:

| Feld | Wert |
|---|---|
| Requirement → Sender | `@example\.com$` |
| Requirement → Recipient | `.*` (oder z. B. nur externe Empfänger, siehe unten) |
| Requirement → Sender-IP | `0.0.0.0` / Netzmaske `0` (jeder Client; die Einschränkung macht Stalwart) |
| Action → Resolve sender | an (und „fail when unable to resolve“ nach Geschmack) |
| Action → Directory servers | leer — der Tenant `example` liefert das AD |

Beispiel für eine Signatur (Text):

```
{resolver["displayName"]}
{resolver["title"]}
{rt}Tel.: {resolver["telephoneNumber"]}{/rt}
```

Mit `{rt}…{/rt}` entfällt die Zeile, wenn das Attribut leer ist.

> **Nur an Mails nach außen?** Die `recipient`-Regex muss **mindestens einen**
> Empfänger treffen. „Nur wenn jemand extern ist“: Requirement Recipient
> `^(?!.*@example\.com$)` — trifft, sobald **ein** Empfänger nicht intern ist. Mails
> an beliebig viele interne Empfänger plus einen externen bekommen die Signatur.

Prüfe die Regel auf der Seite **Signature test** (Absender `jdoe@example.com`,
Empfänger extern). Das Ergebnis entspricht dem, was der Milter produktiv macht.

## Schritt 6: Milter in Stalwart eintragen

WebUI: **Settings › MTA › Filters › Milters** → neuer Milter
([Stalwart: Milter filters](https://stalw.art/docs/mta/filter/milter/)):

| Feld | Wert | Warum |
|---|---|---|
| `host` | `disclaimrng-milter` | Netzwerk-Alias aus `compose.stalwart.yml` |
| `port` | `5000` | |
| `stages` | nur `data` | disclaimrNG braucht die frühen Stufen nicht |
| `enable` | `authenticated_as != ''` | nur **eingelieferte** Mails von angemeldeten Benutzern; eingehende Mails aus dem Internet bleiben unberührt |
| `useTls` | aus | internes Docker-Netz |
| `protocolVersion` | `v6` (Standard) | |
| `tempFailOnError` | an (Standard) — siehe unten | |
| Timeouts | Standard (30 s / 30 s / 60 s) | |

Als JSON-Objekt:

```json
{
  "host": "disclaimrng-milter",
  "port": 5000,
  "stages": {"data": true},
  "enable": {"else": "authenticated_as != ''"},
  "useTls": false,
  "tempFailOnError": true
}
```

**`tempFailOnError`:** Ist der Milter nicht erreichbar oder stürzt ab, antwortet
Stalwart mit `451 4.3.5`; der Client versucht es später erneut und **keine Mail
geht ohne Signatur raus**. Ausgeschaltet läuft Mail bei einem Milter-Ausfall
**unsigniert** weiter. Wenn die Signatur rechtlich vorgeschrieben ist, lasse den
Schalter an. Ein ausgefallenes AD stoppt keine Mail — dann entfällt nur der
AD-Teil der Signatur (je nach „fail when unable to resolve“ die ganze).

## Schritt 7: Netz und Abläufe absichern

- Der Milter-Port ist **nicht** im Internet erreichbar: `compose.yml` veröffentlicht
  ihn nur auf `127.0.0.1`; Stalwart erreicht ihn über das interne Netz `mailnet`.
- Admin-Oberfläche von disclaimrNG nur über SSH-Tunnel/VPN (`WEB_BIND=127.0.0.1`).
- `.env` mit `chmod 600`; die Passwörter von `svc-disclaimr` und `svc-stalwart`
  stehen nur dort bzw. in der Umgebung des Stalwart-Containers.
- Sicherungen: Postgres-Volume `pgdata` und das Medien-Volume von disclaimrNG,
  außerdem die Volumes `stalwart-etc` und `stalwart-data` von Stalwart.

## Schritt 8: Abnahme

1. **Netz:** der Test aus Schritt 4.1 meldet `Milter erreichbar`.
2. **Mail senden:** mit einem Mail-Client (Server `mail.example.com`, Port 465,
   SSL/TLS, Benutzer `jdoe@example.com`) eine Mail an eine **externe** Adresse
   schicken.
3. **Signatur ansehen:** beim Empfänger muss die Signatur mit Name, Titel und
   Telefonnummer **aus dem AD** stehen.
4. **Logs:**

   ```bash
   docker compose -f compose.yml -f compose.stalwart.yml logs --tail=50 milter
   ```

   Erwartet eine Zeile `Adding Disclaimer (Action: … | Rule: … | Disclaimer: …)`.
5. **DKIM:** in den Headern der empfangenen Mail steht `dkim=pass` — die
   Signatur darf die DKIM-Prüfung nicht gebrochen haben.
6. **Anzeige:** die Mail in einem weiteren Client öffnen (Zeilenumbrüche, Umlaute
   in der Signatur, HTML- und Text-Teil).
7. **Ausfalltest:** `docker compose … stop milter`, dann erneut senden. Mit
   `tempFailOnError` an meldet der Client `451`/Zustellung später; danach
   `start milter`, die Mail geht mit Signatur durch.
8. **Eingehende Mail:** eine Mail von außen an einen Benutzer: **keine** Signatur
   (der Milter ist nur für angemeldete Sessions aktiv).

## Betrieb

| Aufgabe | Vorgehen |
|---|---|
| disclaimrNG aktualisieren | `git fetch --tags && git checkout vX.Y.Z`, dann `docker compose -f compose.yml -f compose.stalwart.yml up -d --build`. Migrationen laufen beim Start. |
| Stalwart aktualisieren | Tag `v1` ziehen (`docker compose pull && docker compose up -d`); Hinweise zu größeren Sprüngen in der [Stalwart-Doku](https://stalw.art/docs/). |
| Passwort von `svc-disclaimr` ändern | im AD ändern, `LDAP_SERVER_AD_BIND_PASSWORD` in der `.env` anpassen, `docker compose … up -d` (der Sync schreibt es beim Start in die DB). |
| AD-CA wurde erneuert | `certs/ad-ca.pem` ersetzen, `docker compose … restart web milter`; in Stalwart das CA-Bündel neu bauen. |
| Signatur kurzfristig abschalten | in Stalwart den Milter deaktivieren (oder `enable` auf `false`); Mail läuft sofort unsigniert. |
| Logs | `docker compose … logs -f milter`, `docker logs -f stalwart` |

## Fehlersuche

| Symptom | Ursache und Abhilfe |
|---|---|
| Client bekommt `451 4.3.5` beim Senden | Milter nicht erreichbar oder abgestürzt. `docker compose … ps` (healthy?), Netztest aus Schritt 4.1, `host` in Stalwart = `disclaimrng-milter`? `docker compose … logs milter` auf `Unhandled error` prüfen. |
| Mail geht durch, aber **ohne** Signatur | (1) Milter in Stalwart nicht aktiv: `enable` greift nur bei angemeldeten Sessions. (2) Keine Regel passt: **Signature test** mit Absender/Empfänger probieren. (3) Recipient-Regex trifft keinen Empfänger. (4) `fail when unable to resolve` an und AD-Lookup fehlgeschlagen. |
| Signatur ohne AD-Daten (leere Felder) | Absender wird im AD nicht gefunden: `mail` am Benutzer gesetzt? Alias-Adresse? Dann `SEARCH_QUERY` erweitern (Schritt 4). Im Milter-Log `Cannot resolve email …`. Vor 0.3.2 gab ein Base-DN am Domänen-Stamm (`DC=…,DC=…`) immer leere Felder (`Multiple results found` im Log) — aktualisieren. |
| **Verbindung testen**: `certificate not trusted` | Die hochgeladene/eingehängte Datei ist nicht das Zertifikat der CA, die das DC-Zertifikat ausgestellt hat (Schritt 1.3). |
| **Verbindung testen**: `the certificate is not issued for …` | Unter *Hosts* steht die IP oder ein Kurzname; den FQDN aus dem DC-Zertifikat eintragen (`dc1.corp.example.com`). |
| **Verbindung testen**: `unreachable`/`ldap error` (vor 0.3.2 auch bei Zertifikatsproblemen) | Netz/Port 636, Hostname im Zertifikat, CA nicht vertraut. Prüfen: `docker compose … logs web \| grep LDAPS` (muss `trusting the CA` zeigen) und `docker compose … exec web ls -l /etc/ssl/ad` (liegt `ad-ca.pem` dort? Dateiname genau so, Zugriff lesbar für Benutzer 1000?). |
| **Test connection**: `invalid credentials` | Bind-DN/Passwort von `svc-disclaimr`; Sonderzeichen im Passwort in der `.env` ggf. in Anführungszeichen setzen. |
| Stalwart: Anmeldung mit AD-Benutzer schlägt fehl | `filterLogin` zu streng (Konto deaktiviert, kein `mail`/UPN?), `bindDn`/Passwort falsch, CA nicht vertraut (Schritt 3.4). `docker logs stalwart` zeigt die LDAP-Meldung. |
| Nach der Umstellung auf das AD kommt kein Admin mehr in die WebUI | Wiederherstellungs-Administrator setzen (`STALWART_RECOVERY_ADMIN`, siehe Schritt 3.2) und dem AD-Konto die Administratorrolle zuweisen. |

## Weiterführend

- [Installation](../installation/), [Konfiguration](../configuration/)
- [Verzeichnisserver](../directory-servers/), [Mandanten](../tenants/)
- [Signaturen & Regeln](../signatures/), [Walkthrough](../walkthrough/)
- Stalwart: [Milter filters](https://stalw.art/docs/mta/filter/milter/),
  [Filter-Überblick](https://stalw.art/docs/mta/filter/),
  [LDAP Server](https://stalw.art/docs/auth/backend/ldap/),
  [Docker](https://stalw.art/docs/install/platform/docker/)
