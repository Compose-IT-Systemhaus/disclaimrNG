# Signaturen, Regeln & Editor

Das Datenmodell hat drei Schichten:

| Modell | Was es macht |
|---|---|
| **Disclaimer** (= *Signatur*) | Der eigentliche Signatur-Text — Plain, HTML oder beides. |
| **Rule** | Container aus *Requirements* + *Actions*. Wenn alle Requirements matchen, laufen alle aktiven Actions. |
| **Requirement** | Regex-Filter — Sender, Empfänger, Header, Body, Sender-IP. |
| **Action** | Was getan wird wenn die Regel matcht: Disclaimer anhängen, Tag ersetzen, MIME-Part hinzufügen. |

Eine *Signatur* ist nur Text; eine *Regel* ist das, was sie an eine
bestimmte Mail-Klasse bindet; eine *Action* ist der konkrete Vorgang
(typisch: „diese Signatur an den Body anhängen").

## Der Template-Editor

Erreichbar über **Signaturen → Signaturen verwalten → Hinzufügen /
Bearbeiten**. Drei Tabs teilen sich eine Textarea, damit nichts verloren
geht:

- **Code** — Monaco-Editor mit HTML-/Plaintext-Syntax-Highlighting
  und Autovervollständigung für ``{resolver["…"]}``-Platzhalter.
- **Visual** — TinyMCE-WYSIWYG (nur im HTML-Feld).
- **Preview** — server-seitig gerenderte Vorschau im iframe mit
  Beispiel-Werten für ``{sender}``, ``{recipient}`` und einigen
  Resolver-Attributen, damit du siehst wie die Signatur aussieht.

### Platzhalter-Chips

Unter dem Editor: klickbare Pills zum Einfügen am Cursor.

- **Umschlag** — ``{sender}``, ``{recipient}``
- **Header** — ``{header["subject"]}``, ``{header["from"]}``, …
- **Common fields** — ``Name``, ``Telefon``, ``E-Mail``, ``Adresse``
  (mappen auf die kanonischen LDAP-Attribute ``cn``,
  ``telephoneNumber``, ``mail``, ``streetAddress``, damit du nicht
  raten musst).
- **Verzeichnis-Attribute** — alle Attribute, die die konfigurierten
  DirectoryServer über den Vocabulary-Endpoint melden.

Klick auf einen Chip → Platzhalter wird am Cursor des aktiven Editors
eingefügt. Tab-Wechsel synchronisiert die zugrundeliegende Textarea.

### Bilder-Picker

Unter den Chips: Thumbnail-Grid aller hochgeladenen ``SignatureImage``s.
Klick auf ein Thumbnail fügt ``{image["slug"]}`` am Cursor ein.

Der **+ Hochladen**-Button nimmt direkt eine Datei und legt einen
neuen ``SignatureImage``-Eintrag an — der Slug wird aus dem Dateinamen
abgeleitet (mit Numeric-Suffix bei Kollision). Bilder leben im
``media``-Docker-Volume und werden über ``MEDIA_BASE_URL``
ausgeliefert.

## Platzhalter-Referenz

| Token | Wird zu |
|---|---|
| ``{sender}`` | Envelope-From-Adresse |
| ``{recipient}`` | Envelope-To-Adresse |
| ``{header["X"]}`` | Wert des Mail-Headers ``X`` (Key case-insensitive) |
| ``{resolver["attr"]}`` | LDAP-Attribut ``attr`` des Sender-Eintrags |
| ``{image["slug"]}`` | ``<img>``-Tag (HTML-Disclaimer) oder reine URL (Plaintext) für das SignatureImage mit dem Slug |

### „Resolver-Tag"-Wrapper

Einen Block, der wegfallen soll wenn sein Resolver-Tag nicht aufgelöst
werden kann, in ``{rt}…{/rt}`` wrappen:

```text
Mit freundlichen Grüßen
{resolver["cn"]}
{rt}Tel.: {resolver["telephoneNumber"]}{/rt}
```

Hat der Sender keine ``telephoneNumber`` in LDAP, fällt die ganze
„Tel.:"-Zeile raus, statt einen wörtlichen ``{resolver["…"]}`` in der
Mail zu hinterlassen.

### Fail-Modus

Ist die Option **Fehler wenn Platzhalter nicht aufgelöst werden kann**
am Disclaimer aktiv und ein Resolver-Tag kann nicht gefüllt werden,
wird die Action **übersprungen** — die Mail verlässt den Milter
unverändert. Sinnvoll für hochsensible Signaturen, wo eine leere Stelle
schlimmer wäre als gar keine Signatur.

## Regeln und Actions

Eine **Rule** ist ein Container; das eigentliche Filtern passiert in
ihren **Requirement**-Inlines. Default-Werte sind weit
(``.*`` / ``0.0.0.0/0``), eine Regel mit einer Default-Requirement und
einer Action feuert also auf jede Mail.

Requirement enger ziehen, um die Regel zu skopen:

- **Sender** — Regex gegen Envelope-From. ``.*@acme\.com`` matcht nur
  Mails von ``acme.com``.
- **Empfänger** — Regex gegen Envelope-To.
- **Header-Filter** — Regex gegen alle Header-Zeilen, mit Newlines
  verbunden.
- **Body-Filter** — Regex gegen den Mail-Body.
- **Sender-IP** — IP / CIDR des sendenden Hosts.

Jede Requirement hat zusätzlich ein **Action**-Feld: *Akzeptieren*
oder *Ablehnen*. Eine *Ablehnen*-Requirement deaktiviert die ganze
Regel für diese Mail.

Das **Action**-Inline wählt die Signatur und wie sie eingefügt wird:

- **Add a disclaimer string to the body** — hängt an den Body an. Bei
  HTML-Mails wird der Disclaimer geparst und vor ``</body>`` eingefügt.
- **Replace a tag in the body with a disclaimer string** — praktisch
  für Templates, in denen der User einen wörtlichen ``#DISCLAIMER#``-
  Marker im Mail-Entwurf platziert.
- **Add the disclaimer using an additional MIME part** — wickelt die
  Original-Mail in ``multipart/mixed`` und hängt den Disclaimer als
  separaten Part an. Sinnvoll wenn die Original-Mail binär oder
  signiert ist.

Ist das **Resolve sender**-Flag der Action aktiv, fragt der Milter
die verknüpften DirectoryServer (oder die des Tenants, siehe
[Tenants](../tenants/)) ab, bevor Platzhalter ersetzt werden.

## Eine Regel testen, bevor sie deployed wird

Über **Signaturen → Signaturtest** beliebige Mails durch die **echte**
Regel-Pipeline schicken, ohne Postfix. Formularfelder:

- Absender / Empfänger / Betreff / Sender-IP / Inhaltstyp / Mail-Inhalt

Das Ergebnis-Panel zeigt:

- Banner mit den gegriffenen Regeln,
- den **modifizierten Body** (gerenderte HTML-Vorschau für
  ``text/html``, einfaches ``<pre>`` für ``text/plain``),
- die Header-Diff (add/change/delete) aus dem Workflow,
- die vollständige RFC-822-Mail nach der Pipeline,
- ein zugeklapptes View der Eingabe-Mail.
