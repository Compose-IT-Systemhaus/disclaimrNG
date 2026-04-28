# disclaimrNG-Dokumentation

disclaimrNG ist ein modernisierter, dockerisierter Fork von
[dploeger/disclaimr][upstream] — ein
[Milter](https://www.milter.org/)-Daemon, der ausgehenden Mails
automatisch Signaturen (auch Disclaimer oder Footer) anhängt und
optional pro-Benutzer-Daten (Name, Titel, Telefon, …) aus LDAP oder
Active Directory zieht.

[upstream]: https://github.com/dploeger/disclaimr

## Was du hier findest

1. **[Installation](installation/)** — Docker Compose, Traefik-Beispiel,
   Umgebungsvariablen.
2. **[Konfiguration](configuration/)** — First-Boot-Admin,
   Django-Settings, Medien-/Static-Files.
3. **[Tenants](tenants/)** — Multi-Tenant-Setup; ein Signatur-Schema
   pro Kunde / Domain.
4. **[Verzeichnisserver](directory-servers/)** — LDAP-/AD-Setup,
   Attribut-Discovery, Suchanfrage-Templates.
5. **[Signaturen & Regeln](signatures/)** — der Editor, Bilder-Picker,
   Resolver-Platzhalter, Requirements, Actions.
6. **[Schritt-für-Schritt — Domain-Signatur](walkthrough/)** —
   Komplett-Beispiel: „Signatur für ``@example.com`` einrichten, die
   Name und Telefon des Absenders aus AD zieht."
7. **[Troubleshooting](troubleshooting/)** — typische Fehler und wie
   man die Logs liest.

## Schnell-Links

- **Admin-UI**: das Admin auf diesem Server (du bist als Staff-User
  eingeloggt, wenn du diese Seite siehst).
- **Quellcode**: <https://github.com/Compose-IT-Systemhaus/disclaimrNG>
- **Issue-Tracker**: <https://github.com/Compose-IT-Systemhaus/disclaimrNG/issues>

## Architektur in einem Diagramm

```
                    ┌────────────────────┐
   ausg. Mail   ──  │  Postfix / Sendmail│ ── Milter (5000) ──┐
                    └────────────────────┘                    │
                                                              ▼
   ┌──────────┐         ┌──────────────┐         ┌────────────────────┐
   │  LDAP /  │ ◄────── │   Milter-    │ ◄─────► │   PostgreSQL       │
   │   AD     │         │   Daemon     │         │  (Regeln, Vorlagen)│
   └──────────┘         └──────────────┘         └────────────────────┘
                                                              ▲
                                                              │
                                              ┌──────────────────┐
                                              │  Django-Web-UI   │ ── Browser
                                              │  (Admin + Editor)│
                                              └──────────────────┘
```

Der **Web-Container** läuft das Admin, das du gerade nutzt. Der
**Milter-Container** ist das, womit deine MTA (Postfix, Sendmail) auf
Port 5000 spricht, um Signaturen anzuhängen. Beide teilen sich dieselbe
Datenbank und Konfiguration; der Milter ist nur lesend dagegen.
