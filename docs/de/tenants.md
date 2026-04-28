# Tenants

Ein **Tenant** ist ein logischer Mandant — typisch ein Kunde von dir
oder eine Geschäftseinheit deiner eigenen Firma. Jeder Tenant bündelt:

- eine oder mehrere **Absender-Domains** (z. B. ``acme.com``,
  ``acme.de``),
- die **Verzeichnisserver** mit den Kontaktdaten für diese Domains
  (LDAP oder Active Directory),
- die **Signaturen** (und ihre Regeln), die für ausgehende Mails dieser
  Domains gelten sollen.

Multi-Tenancy ist **additiv** — disclaimrNG läuft auch ohne jeden
Tenant, alles kann global konfiguriert werden. Die Verbindungen von
DirectoryServer / Disclaimer / Rule zu Tenant sind nullable und nutzen
``ON DELETE SET NULL``.

## Wie der Milter den Tenant auflöst

Wenn die Milter-Pipeline LDAP für den Absender einer Mail abfragen
muss, wählt sie die Verzeichnisserver in dieser Reihenfolge:

1. Die **explizit** zur passenden ``Action`` verknüpften
   ``directory_servers`` (im Admin pro Regel konfiguriert).
2. Falls leer: die Verzeichnisserver des Tenants, dem die
   Absender-Domain gehört.

Im häufigen Fall („ein Tenant pro Kunde, ein LDAP pro Tenant") musst
du also nie LDAP-Server an einzelne Actions hängen — einmal mit dem
Tenant verknüpfen reicht, der Milter findet sie zur Laufzeit.

## Tenant im Admin anlegen

1. Sidebar **Settings → Tenants → Tenant hinzufügen**.
2. **Name** ist das, was du im Dashboard sehen willst (z. B.
   „Acme Corp").
3. **Slug** wird automatisch aus dem Namen gefüllt; wird in API-URLs
   und beim Env-Bootstrap als Lookup-Key genutzt.
4. **Tenant-Domains** im Inline unten hinzufügen (z. B. ``acme.com``,
   ``acme.de``). Domains werden **case-insensitive** gegen den
   *rechten Teil* der Envelope-From-Adresse gematcht.
5. Speichern.
6. Anschließend unter **Settings → Verzeichnisserver** den LDAP-/AD-
   Server für diesen Tenant anlegen (oder bearbeiten) und im Feld
   **Tenant** den eben angelegten Tenant auswählen.

## Bootstrap per Env-Variablen

Nützlich für deklarative Deployments. In ``.env``:

```dotenv
TENANTS=acme,globex
TENANT_ACME_NAME=Acme Corp
TENANT_ACME_DOMAINS=acme.com,acme.de
TENANT_GLOBEX_NAME=Globex
TENANT_GLOBEX_DOMAINS=globex.com
```

Pro Handle (``<HANDLE>`` durch den uppercased-Namen aus ``TENANTS``
ersetzen):

| Variable | Default | Notiz |
|---|---|---|
| ``TENANT_<HANDLE>_NAME`` | Handle, title-cased | Anzeigename |
| ``TENANT_<HANDLE>_DESCRIPTION`` | leer | Frei |
| ``TENANT_<HANDLE>_DOMAINS`` | **Pflicht** | Komma-getrennte Absender-Domains |
| ``TENANT_<HANDLE>_ENABLED`` | ``true`` | ``false`` skipt den Tenant beim Sender-Resolve |

Der Web-Container ruft bei jedem Boot ``manage.py sync_tenants`` auf,
sofern ``TENANTS`` gesetzt ist. ``TENANT_SYNC_PRUNE=1`` löscht
env-verwaltete Tenants, die nicht mehr in ``TENANTS`` auftauchen.

Um einen Verzeichnisserver per Env mit einem Tenant zu verknüpfen,
ergänze ``LDAP_SERVER_<HANDLE>_TENANT=<slug>`` im jeweiligen
``LDAP_SERVER_*``-Block — siehe [Verzeichnisserver](../directory-servers/).
