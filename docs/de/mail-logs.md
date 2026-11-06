# Mail-Logs

Unter **Einstellungen → Logs** siehst du, welche Mails den Milter durchlaufen
haben und welche Signatur angehängt wurde. Die Seite ist **nur für
Administratoren** (Superuser) sichtbar — Staff-Benutzer mit einzelnen
Modellrechten sehen sie nicht, auch nicht per URL.

## Was die Liste zeigt

| Spalte | Bedeutung |
|---|---|
| Zeit | Wann der Milter das Mail-Ende (Body) erhalten hat. |
| Absender / Empfänger | Envelope-Adressen. Bei mehreren Empfängern der erste, auf den ein Requirement passt, sonst der erste Empfänger. |
| Betreff | Wert des ``Subject``-Headers. |
| Signatur angehängt | Häkchen, wenn mindestens eine Aktion die Mail geändert hat. |
| Angewendete Signaturen | Je Aktion eine Zeile ``Regel → Aktion → Signatur``. |

Im Detail zusätzlich: Queue-ID des MTA (falls er eine sendet — Stalwart tut
das nicht) und die IP des einliefernden Clients.

Regel, Aktion und Signatur werden **als Text** gespeichert. Ein Eintrag bleibt
lesbar, auch wenn du die Signatur später umbenennst oder löschst.

## Unbearbeitete Mails ausblenden

Es werden **alle** Mails protokolliert, die der Milter sieht — auch die, auf
die keine Regel passte (Häkchen leer, keine Signaturzeile). Standardmäßig zeigt
die Liste beides. Über den Filter **Signatur angehängt → Ja** in der rechten
Spalte blendest du die unbearbeiteten Mails aus; **Nein** zeigt nur diese, etwa
um zu prüfen, warum eine Mail keine Signatur bekommen hat.

Die Suche durchsucht Absender, Empfänger, Betreff, Queue-ID und die
angewendeten Signaturen; die Datumsnavigation oberhalb der Liste grenzt auf
Jahr, Monat und Tag ein.

## Aufbewahrung

Einträge werden nach **30 Tagen** automatisch gelöscht. Die Frist stellst du in
``.env`` ein:

```dotenv
MAIL_LOG_RETENTION_DAYS=30   # 0 = nie löschen
```

Danach ``docker compose up -d`` (Web und Milter lesen die Variable beim
Start). Aufgeräumt wird vom **Milter-Container** beim Start und danach
höchstens einmal pro Stunde; läuft er nicht, bleiben alte Einträge liegen.
Einzelne Einträge kannst du als Administrator in der Liste auch von Hand
löschen (Auswahl → „Ausgewählte Logs löschen“).

## Grenzen

- Protokolliert wird, was der **Milter** sieht. Mails, die der MTA nicht an den
  Milter übergibt (z. B. Stalwart ohne aktiviertes Milter für diese Einlieferung,
  siehe Runbook), erscheinen nicht.
- Abgebrochene Verbindungen und Mails, die der MTA vor dem Ende des Body
  verwirft, haben keinen Eintrag.
- Die Einträge enthalten **Mail-Adressen und Betreffzeilen im Klartext** und
  sind damit personenbezogene Daten. Wähle die Aufbewahrungsfrist passend zu
  deinen Datenschutzvorgaben.
- Jede Mail, die den Milter erreicht, erzeugt einen Datenbank-Eintrag. Bei
  sehr hohem Mailaufkommen eine kürzere Frist wählen.
