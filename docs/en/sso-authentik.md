# Single sign-on (OpenID Connect)

Users can sign in to the web interface through an identity provider such as
[Authentik](https://goauthentik.io/) instead of (or next to) a local password. The first
sign-in creates the account, and the groups of the provider are mapped onto the local
groups *Admins*, *Editor* and *Reader* (see *Users and roles* under Configuration).

## What happens at sign-in

- **First sign-in:** the account is created automatically (user name from the provider's
  ``preferred_username``, e-mail and name as sent). It has no local password.
- **Every sign-in:** the groups the provider reports are mapped onto local groups with the
  *SSO groups* list (*Settings › SSO groups*). A group removed at the provider is removed
  here at the next sign-in. Groups you assigned by hand stay.
- **No mapped group:** the user becomes a *Reader*.
- **Admins** are superusers (and lose that again when the group is gone), so they also see the
  mail log and the dashboard statistics. Everybody who signs in through SSO can enter the admin
  (*Staff status* is set).
- **Local accounts are never linked or taken over.** If the provider sends the user name
  ``admin``, the SSO account gets another name (``admin1``); the local ``admin`` and its password
  keep working. Local accounts that never used SSO are not touched by the group sync.
- **Sign-out** only ends the session here, not at the provider.

## 1. Set up the provider (Authentik)

1. *Applications › Providers › Create › OAuth2/OpenID Provider*:
   - *Client type*: confidential. Note the *Client ID* and *Client Secret*.
   - *Redirect URIs/Origins*, **strict**: ``https://signatures.example.com/accounts/oidc/sso/login/callback/``
     (your public address; scheme and trailing slash have to match exactly).
   - *Signing Key*: pick a certificate (RS256). Without a signing key Authentik signs with the
     client secret, which disclaimrNG cannot verify.
   - *Scopes*: ``openid``, ``email``, ``profile`` (the default). Authentik puts the user's groups
     into the ``groups`` claim of the ``profile`` scope.
2. *Applications › Applications › Create*: choose a *slug* (``disclaimrng``) and the provider.
   Bind the users or groups who may sign in under *Policy / Group / User Bindings* — Authentik
   decides who reaches disclaimrNG at all.

## 2. Configure disclaimrNG

Add to ``.env`` and restart (``docker compose up -d``):

```dotenv
OIDC_SERVER_URL=https://authentik.example.com/application/o/disclaimrng/
OIDC_CLIENT_ID=<client id>
OIDC_CLIENT_SECRET=<client secret>
OIDC_NAME=Authentik
```

| Variable | Meaning |
|---|---|
| ``OIDC_SERVER_URL`` | The *OpenID Configuration Issuer* of the application (``…/application/o/<slug>/``). |
| ``OIDC_CLIENT_ID`` / ``OIDC_CLIENT_SECRET`` | From the provider. |
| ``OIDC_NAME`` | Label of the button on the login page (default ``SSO``). |
| ``OIDC_SCOPES`` | Comma-separated scopes (default ``openid,profile,email``). |
| ``OIDC_GROUPS_CLAIM`` | Claim that holds the groups (default ``groups``). |

SSO is off as long as the first three are not all set. Behind a reverse proxy the web container
has to see HTTPS (``DJANGO_SECURE_COOKIES=true``, ``DJANGO_CSRF_TRUSTED_ORIGINS`` with your
address, as in ``compose.traefik.yml``), otherwise the redirect address is built with ``http://``.

## 3. Map the groups

*Settings › SSO groups › Add*: the name of a group at the provider (exactly as sent, case
matters) and the local group it gives, for example ``disclaimr-admins`` → *Admins*,
``disclaimr-editors`` → *Editor*. Several provider groups can map to one local group.

## 4. Try it

Open the login page: below the password form there is a button *Sign in with Authentik*. After
the first sign-in the user appears under *Users* (without a password) with the mapped groups.
Keep the local ``admin`` account as a way in if the provider is down.

## Troubleshooting

| Symptom | Cause |
|---|---|
| The provider reports *redirect_uri mismatch* | The redirect URI at the provider differs from ``https://<address>/accounts/oidc/sso/login/callback/`` (scheme, host, trailing slash), or the container builds ``http://`` (see above). |
| *Sign-in with … failed* on the login page | ``docker compose logs web`` shows ``SSO login failed``. Often a wrong ``OIDC_SERVER_URL`` (it has to end in the application slug) or a wrong secret. |
| The user is only a *Reader* | The group name at the provider differs from the one in *SSO groups* (case), or the ``groups`` claim is missing: check the scope mapping at the provider and ``OIDC_GROUPS_CLAIM``. |
| *This account is disabled* | The account was deactivated in *Users*; reactivate it there. |
