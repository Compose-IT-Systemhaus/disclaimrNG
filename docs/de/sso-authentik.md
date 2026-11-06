# Single Sign-on (OpenID Connect)

Benutzer können sich an der Weboberfläche über einen Identity Provider wie
[Authentik](https://goauthentik.io/) anmelden, statt oder neben einem lokalen Passwort. Die
erste Anmeldung legt das Konto an, und die Gruppen des Providers werden auf die lokalen Gruppen
*Admins*, *Editor* und *Reader* abgebildet (siehe *Benutzer und Rollen* unter Konfiguration).

## Was bei der Anmeldung passiert

- **Erste Anmeldung:** Das Konto wird automatisch angelegt (Benutzername aus dem
  ``preferred_username`` des Providers, E-Mail und Name wie gesendet). Es hat kein lokales Passwort.
- **Jede Anmeldung:** Die vom Provider gemeldeten Gruppen werden über die Liste *SSO-Gruppen*
  (*Einstellungen › SSO-Gruppen*) auf lokale Gruppen abgebildet. Eine Gruppe, die beim Provider
  wegfällt, fällt bei der nächsten Anmeldung auch hier weg. Von Hand vergebene Gruppen bleiben.
- **Keine gemappte Gruppe:** Der Benutzer wird *Reader*.
- **Admins** sind Superuser (und verlieren das wieder, wenn die Gruppe wegfällt) und sehen
  deshalb auch das Mail-Log und die Dashboard-Statistik. Wer sich per SSO anmeldet, kommt in den
  Admin (*Mitarbeiter-Status* wird gesetzt).
- **Lokale Konten werden nie verknüpft oder übernommen.** Sendet der Provider den Benutzernamen
  ``admin``, bekommt das SSO-Konto einen anderen Namen (``admin1``); das lokale ``admin`` mit seinem
  Passwort funktioniert weiter. Lokale Konten, die nie SSO genutzt haben, fasst der Gruppen-Abgleich nicht an.
- **Abmelden** beendet nur die Sitzung hier, nicht beim Provider.

## 1. Provider einrichten (Authentik)

1. *Applications › Providers › Create › OAuth2/OpenID Provider*:
   - *Client type*: confidential. *Client ID* und *Client Secret* notieren.
   - *Redirect URIs/Origins*, **strict**: ``https://signatures.example.com/accounts/oidc/sso/login/callback/``
     (Ihre öffentliche Adresse; Schema und abschließender Schrägstrich müssen exakt passen).
   - *Signing Key*: ein Zertifikat wählen (RS256). Ohne Signing Key signiert Authentik mit dem
     Client Secret, das disclaimrNG nicht prüfen kann.
   - *Scopes*: ``openid``, ``email``, ``profile`` (Standard). Authentik legt die Gruppen des Benutzers
     in den Claim ``groups`` des Scopes ``profile``.
2. *Applications › Applications › Create*: einen *Slug* (``disclaimrng``) und den Provider wählen.
   Unter *Policy / Group / User Bindings* die Benutzer oder Gruppen binden, die sich anmelden dürfen —
   Authentik entscheidet, wer überhaupt zu disclaimrNG kommt.

## 2. disclaimrNG konfigurieren

In ``.env`` eintragen und neu starten (``docker compose up -d``):

```dotenv
OIDC_SERVER_URL=https://authentik.example.com/application/o/disclaimrng/
OIDC_CLIENT_ID=<Client ID>
OIDC_CLIENT_SECRET=<Client Secret>
OIDC_NAME=Authentik
```

| Variable | Bedeutung |
|---|---|
| ``OIDC_SERVER_URL`` | Der *OpenID Configuration Issuer* der Application (``…/application/o/<slug>/``). |
| ``OIDC_CLIENT_ID`` / ``OIDC_CLIENT_SECRET`` | Vom Provider. |
| ``OIDC_NAME`` | Beschriftung des Buttons auf der Login-Seite (Standard ``SSO``). |
| ``OIDC_SCOPES`` | Scopes, kommagetrennt (Standard ``openid,profile,email``). |
| ``OIDC_GROUPS_CLAIM`` | Claim mit den Gruppen (Standard ``groups``). |

SSO ist aus, solange nicht die ersten drei gesetzt sind. Hinter einem Reverse Proxy muss der
Web-Container HTTPS sehen (``DJANGO_SECURE_COOKIES=true``, ``DJANGO_CSRF_TRUSTED_ORIGINS`` mit Ihrer
Adresse, wie in ``compose.traefik.yml``), sonst wird die Redirect-Adresse mit ``http://`` gebaut.

## 3. Gruppen zuordnen

*Einstellungen › SSO-Gruppen › Hinzufügen*: der Name einer Gruppe beim Provider (genau wie gesendet,
Groß-/Kleinschreibung zählt) und die lokale Gruppe, die sie vergibt, zum Beispiel ``disclaimr-admins`` →
*Admins*, ``disclaimr-editors`` → *Editor*. Mehrere Provider-Gruppen können auf eine lokale zeigen.

## 4. Ausprobieren

Die Login-Seite öffnen: unter dem Passwort-Formular steht ein Button *Mit Authentik anmelden*. Nach der
ersten Anmeldung erscheint der Benutzer unter *Benutzer* (ohne Passwort) mit den zugeordneten Gruppen.
Das lokale Konto ``admin`` bleibt als Zugang, falls der Provider ausfällt.

## Fehlersuche

| Symptom | Ursache |
|---|---|
| Der Provider meldet *redirect_uri mismatch* | Die Redirect-URI beim Provider weicht von ``https://<Adresse>/accounts/oidc/sso/login/callback/`` ab (Schema, Host, Schrägstrich) oder der Container baut ``http://`` (siehe oben). |
| *Anmeldung mit … fehlgeschlagen* auf der Login-Seite | ``docker compose logs web`` zeigt ``SSO login failed``. Oft eine falsche ``OIDC_SERVER_URL`` (sie muss auf den Application-Slug enden) oder ein falsches Secret. |
| Der Benutzer ist nur *Reader* | Der Gruppenname beim Provider weicht von dem in *SSO-Gruppen* ab (Schreibweise), oder der Claim ``groups`` fehlt: Scope-Mapping beim Provider und ``OIDC_GROUPS_CLAIM`` prüfen. |
| *Dieses Konto ist deaktiviert* | Das Konto wurde unter *Benutzer* deaktiviert; dort wieder aktivieren. |
