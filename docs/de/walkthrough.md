# Schritt-für-Schritt — Signatur für ``@example.com``

Ende-zu-Ende-Rezept: disclaimrNG so konfigurieren, dass jede Mail von
``@example.com`` eine Signatur mit **Name**, **Titel** und
**Telefonnummer** des Absenders aus Active Directory bekommt — plus
Firmen-Logo.

Diese Seite setzt voraus:

- disclaimrNG läuft (siehe [Installation](../installation/)),
- Zugriff auf ein Active Directory unter z. B. ``dc=example,dc=com``,
- ein Service-Account, der AD lesen darf (read-only reicht — Bind
  + ``search_s`` ist alles, was der Milter macht),
- ein PNG-Logo zum Einbinden.

Dauert komplett ~10 Minuten.

---

## Schritt 1 — Tenant anlegen

Tenants verknüpfen eine Absender-Domain mit ihrem Verzeichnisserver,
damit der Milter weiß, wo er den Sender suchen soll.

1. Sidebar **Settings → Tenants → Tenant hinzufügen**.
2. Ausfüllen:
   - **Name**: ``Example Inc.``
   - **Slug**: ``example`` (auto-gefüllt aus dem Namen)
3. Im Inline **Tenant-Domains** unten eine Zeile hinzufügen:
   - **Domain**: ``example.com``
4. Speichern.

Weitere Domains kannst du später ergänzen (``example.de``,
``example.org``) — der Milter matcht jeweils die Domain, der die
Sender-Adresse gehört.

## Schritt 2 — Active Directory anlegen

1. Sidebar **Settings → Verzeichnisserver → Verzeichnisserver
   hinzufügen**.
2. Ausfüllen:
   - **Tenant**: ``Example Inc.`` (eben angelegt)
   - **Name**: ``Example AD``
   - **Aktiviert**: ✓
3. Verbindungs-Block:
   - **Variante**: *Active Directory* (füllt die Suchanfrage)
   - **Base DN**: ``dc=example,dc=com``
   - **Authentifizierungsmethode**: *Einfach*
   - **Benutzer-DN**: ``CN=disclaimr,OU=Service,DC=example,DC=com``
   - **Passwort**: (Service-Account-Passwort)
4. Anfrage-Block — AD-Defaults lassen
   (``(userPrincipalName=%s)``).
5. URL-Inline:
   - **URL**: ``ldaps://dc1.example.com``
   - Zweite URL für Failover: ``ldaps://dc2.example.com``
6. Speichern.
7. Auf der Change-Seite oben **Test connection** klicken — beide URLs
   sollten ``bind + base search ok`` melden.
8. **Discover attributes** klicken — sampelt ein paar echte Einträge
   und listet die AD-Attribute. Die relevanten Namen (``cn``,
   ``displayName``, ``title``, ``telephoneNumber``, ``mobile``,
   ``mail``, ``streetAddress``, ``company``, ``department``) in die
   **Attributliste** kopieren, damit sie im Editor-Autocomplete
   erscheinen.
9. Erneut speichern.

## Schritt 3 — Firmen-Logo hochladen

1. Sidebar **Signaturen → Bilder → Bild hinzufügen**.
2. Ausfüllen:
   - **Slug**: ``example-logo`` (das schreibst du später ins Template)
   - **Name**: ``Example Inc. Logo``
   - **Bild**: PNG vom Datenträger wählen
   - **Alternativtext**: ``Example Inc.``
   - **Anzeigebreite**: ``180`` (oder leer für die natürliche Größe)
3. Speichern.

Du kannst auch direkt aus dem Disclaimer-Editor in Schritt 4 hochladen.

## Schritt 4 — Disclaimer schreiben

1. Sidebar **Signaturen → Signaturen verwalten → Signatur hinzufügen**.
2. Ausfüllen:
   - **Tenant**: ``Example Inc.``
   - **Name**: ``Example Inc. — Standard``
   - **Description**: ``Standard-Footer für @example.com-Mails``
3. **Plaintext-Teil** → ggf. zum **Code**-Tab wechseln:

   ```text
   --
   {resolver["displayName"]}
   {rt}{resolver["title"]}{/rt}
   Example Inc.
   {rt}Tel.: {resolver["telephoneNumber"]}{/rt}
   {rt}Mobil: {resolver["mobile"]}{/rt}
   Web: https://example.com
   ```

   Die ``{rt}…{/rt}``-Wrapper lassen die *Tel.:* / *Mobil:*-Zeilen
   sauber wegfallen, falls der AD-Eintrag diese Attribute nicht
   hat.
4. **HTML-Teil** → **Textteil verwenden** *abwählen* (wir wollen eine
   reichhaltigere HTML-Variante). Im **Visual**-Tab mit der Toolbar
   arbeiten — oder im **Code**-Tab:

   ```html
   <p style="font-family: sans-serif; font-size: 13px; color: #333;">
     <strong>{resolver["displayName"]}</strong>
     {rt}<br>{resolver["title"]}{/rt}<br>
     Example Inc.<br>
     {rt}Tel.: <a href="tel:{resolver["telephoneNumber"]}">{resolver["telephoneNumber"]}</a><br>{/rt}
     <a href="https://example.com">example.com</a>
   </p>
   {image["example-logo"]}
   ```

   Statt die Platzhalter zu tippen, kannst du auch die Chips
   **Common fields** unter dem Editor (Name / Telefon / E-Mail /
   Adresse) klicken — die fügen den passenden ``{resolver["…"]}``-
   Token am Cursor ein.
5. **Vorlagen-Platzhalter verwenden** muss für beide Teile aktiv sein.
6. Speichern.

## Schritt 5 — Mit einer Regel verbinden

1. Sidebar **Signaturen → Regeln → Regel hinzufügen**.
2. Ausfüllen:
   - **Tenant**: ``Example Inc.``
   - **Name**: ``Example Inc. — Standard-Footer``
   - **Position**: ``0`` (erste Regel in der Auswertung)
3. **Requirements**-Inline → eine Zeile:
   - **Sender**: ``.*@example\.com``
   - Rest auf Defaults (``.*``, ``0.0.0.0/0``)
   - **Action**: *Regel akzeptieren*
4. **Actions**-Inline → eine Zeile:
   - **Position**: ``0``
   - **Name**: ``Standard-Footer anhängen``
   - **Action**: *Add a disclaimer string to the body*
   - **Disclaimer**: ``Example Inc. — Standard``
   - **Resolve the sender**: ✓
   - **Directory servers**: leer lassen (Milter fällt auf den
     ``Example AD`` des Tenants zurück)
5. Speichern.

## Schritt 6 — Testen

1. Sidebar **Signaturen → Signaturtest**.
2. Ausfüllen:
   - **Absender**: ``alice@example.com`` (muss ein existierender
     AD-User sein, sonst findet der Resolver nichts)
   - **Empfänger**: ``bob@external.tld``
   - **Betreff**: ``Hallo``
   - **Mail-Inhalt**: zwei, drei beliebige Zeilen
3. **Test ausführen** klicken.

Erwartetes Ergebnis:

- Grünes Banner: ``1 Regel hat gegriffen``.
- **Gegriffene Regeln**: ``Example Inc. — Standard-Footer``.
- **Modifizierter Mail-Body**: deine Original-Zeilen + die gerenderte
  Signatur mit ``displayName`` / ``title`` / ``telephoneNumber`` aus
  AD.
- **Vollständige Mail nach der Pipeline** zeigt die On-the-wire-Form.

Wenn ein Platzhalter leer bleibt, prüfe ob der AD-Attributname exakt
stimmt (AD-Attribute sind im Template case-sensitive — ``displayName``,
nicht ``displayname``).

## Schritt 7 — Postfix auf den Milter zeigen

In ``main.cf``:

```
smtpd_milters = inet:disclaimrng:5000
non_smtpd_milters = inet:disclaimrng:5000
milter_default_action = accept
milter_protocol = 6
```

``systemctl reload postfix`` und eine echte Mail von
``alice@example.com`` an deine externe Adresse schicken. Die Signatur
sollte unten erscheinen.

---

## Varianten

### Verschiedene Signaturen pro Abteilung

Eine zweite Regel mit engerem ``Header-Filter`` (``X-Department:
Sales``) — oder sauberer: das AD in mehrere DirectoryServer-Einträge
nach ``base_dn`` splitten (eine pro OU) und jeden mit einem anderen
Tenant verknüpfen.

### Zwei Domains, gleiche Signatur

Einfach eine zweite Domain zum gleichen Tenant hinzufügen
(*Settings → Tenants → Example Inc.* → ``example.de`` ins
Domains-Inline). Eine Regel, eine Signatur, beide Domains.

### Zwei Domains, verschiedene Signaturen

Zwei Tenants anlegen, jeder mit eigener Domain. Pro Tenant eigenen
DirectoryServer + Disclaimer + Rule konfigurieren. Der Milter routet
zur Laufzeit nach Sender-Domain.
