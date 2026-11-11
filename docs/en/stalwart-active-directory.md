# Runbook — disclaimrNG with Stalwart 1.0 and Active Directory

Step by step: outgoing mail that users submit through **Stalwart 1.0** gets a
signature with data from **Active Directory**. Stalwart and disclaimrNG run as
Docker containers on the **same host**.

> **Status.** Tested on 11 Nov 2026 with Stalwart 1.0, an Active Directory with
> LDAPS and an internal CA, and real mailboxes (disclaimrNG 0.3.3). Still run the
> acceptance test in [Step 8](#step-8-acceptance-test) on your setup. If a menu or
> field name differs in a newer Stalwart, check the
> [Stalwart docs](https://stalw.art/docs/).

## 0. Overview

```
 Mail client ──465 (login)──► Stalwart ──DATA stage──► disclaimrNG milter
                                 │   │                  (disclaimrng-milter:5000)
                  LDAPS 636      │   │                          │  LDAPS 636
              (login, recipients)│   └─ queue: DKIM signature,  │  (sender data)
                                 ▼      then delivery           ▼
                              Active Directory  ◄───────────────┘
```

What you need to know:

- Stalwart has **no filter stage for outbound delivery**. Milters run when mail is
  **submitted** (also for authenticated sessions on port 465/587). disclaimrNG
  appends the signature there; **afterwards** Stalwart DKIM-signs the message. The
  signature is therefore part of the DKIM-signed message.
- The milter is only consulted at the **DATA stage**. Stalwart opens one
  connection and sends connection data, EHLO, sender, recipients, headers and body
  in one go — all disclaimrNG needs.
- Stalwart sends no queue ID at the DATA stage. That is harmless: disclaimrNG only
  uses it for log lines.
- **Two** AD connections with **two** service accounts: Stalwart (user login,
  recipient lookup) and disclaimrNG (sender data for the signature).

Placeholders used below — replace them with your own values:

| Placeholder | Example |
|---|---|
| Mail domain | `example.com` |
| Stalwart mail hostname | `mail.example.com` |
| AD domain / base DN | `corp.example.com` / `DC=corp,DC=example,DC=com` |
| Domain controllers | `dc1.corp.example.com`, `dc2.corp.example.com` |
| Directory on the Docker host | `/opt/disclaimrng` (disclaimrNG), `/opt/stalwart` (Stalwart) |
| Docker network shared by both stacks | `mailnet` |

## 1. Prerequisites

| Check | How |
|---|---|
| Docker Engine with the Compose plugin on the host | `docker compose version` |
| Host reaches the domain controllers on **636/tcp** (LDAPS) | `openssl s_client -connect dc1.corp.example.com:636 </dev/null` |
| LDAPS is enabled on the DCs (certificate present) | see [Step 1](#step-1-prepare-active-directory) |
| Users have the **`mail`** attribute set in AD | see [Step 1](#step-1-prepare-active-directory) |
| Stalwart 1.0 is running or installed (mail DNS, MX, certificate) | [Stalwart: Docker](https://stalw.art/docs/install/platform/docker/) |
| The disclaimrNG admin on port 8000 must **not** be publicly reachable | access via VPN or SSH tunnel |

> Stalwart takes ports 25, 465, 993, 995, 4190 and **443** on the host.
> disclaimrNG's `compose.traefik.yml` (also 443) is therefore not an option on
> this host; use `compose.yml`.

## Step 1: Prepare Active Directory

### 1.1 Create two service accounts

Both accounts only need **read access** (any authenticated user may read AD by
default). On a domain controller, in PowerShell:

```powershell
$ou = "OU=Service Accounts,DC=corp,DC=example,DC=com"

foreach ($name in "svc-stalwart", "svc-disclaimr") {
    New-ADUser -Name $name -SamAccountName $name `
        -UserPrincipalName "$name@corp.example.com" -Path $ou `
        -AccountPassword (Read-Host -AsSecureString "Password for $name") `
        -Enabled $true -PasswordNeverExpires $true -CannotChangePassword $true
}
```

Two separate accounts so passwords can be rotated independently and the AD log
shows who is asking. Do **not** add the accounts to groups with write access.

### 1.2 Check the e-mail attribute

disclaimrNG looks up the sender by the envelope address, Stalwart looks up
recipients by `mail`. Users without `mail` get neither data in the signature nor
mail in Stalwart.

```powershell
# Find users WITHOUT a mail attribute
Get-ADUser -Filter 'Enabled -eq $true' -Properties mail |
    Where-Object { -not $_.mail } | Select-Object SamAccountName

# Set a missing attribute
Set-ADUser jdoe -EmailAddress "jdoe@example.com"
```

For the signature, `displayName`, `title`, `telephoneNumber` (and whatever else
you show) should be maintained too.

### 1.3 Check LDAPS and export the CA certificate

disclaimrNG and Stalwart both use **LDAPS (636)**. Plain LDAP is not an option:
disclaimrNG does not support STARTTLS, and domain controllers usually require
LDAPS or signing for simple binds.

1. Export the **root CA certificate** that issued the DC certificates,
   Base-64 encoded (PEM), e.g. via `certlm.msc` → *Trusted Root Certification
   Authorities* → certificate → *All Tasks → Export*. If there are intermediate
   CAs, append them to the same file. Alternative in PowerShell on the CA server
   (the quotes matter, PowerShell splits `-ca.cert` otherwise):
   `certutil '-ca.cert' C:\Temp\ca.cer`, or on any domain member
   `certutil -store Root "<CA name>" C:\Temp\ca.cer`; then
   `certutil -encode C:\Temp\ca.cer C:\Temp\ad-ca.pem`. It has to be the **CA's**
   certificate (issuer of the DC certificate), not the DC certificate itself — the
   most common mistake in the live test.
2. Put the file on the Docker host:

   ```bash
   sudo mkdir -p /opt/disclaimrng/certs
   sudo cp ad-ca.pem /opt/disclaimrng/certs/ad-ca.pem
   ```
3. Check the chain from the host:

   ```bash
   openssl s_client -connect dc1.corp.example.com:636 \
       -CAfile /opt/disclaimrng/certs/ad-ca.pem </dev/null 2>&1 | grep "Verify return code"
   ```

   Expected: `Verify return code: 0 (ok)`. The name in the certificate must match
   the host name you use in the URL later (`dc1.corp.example.com`, not the IP).

## Step 2: Shared Docker network

Stalwart only reaches the milter if both containers are in the same Docker
network. (`127.0.0.1` on the host does not help: the milter port is only visible
to processes on the host there, not from another container.)

```bash
docker network create mailnet
```

Attach the Stalwart container to it — in Stalwart's compose file:

```yaml
services:
  stalwart:
    # ... existing settings ...
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

The name `stalwart` must appear in the output. (`docker network connect mailnet
stalwart` also works but does not survive re-creating the container.)

## Step 3: Stalwart with the AD directory

The installation of Stalwart itself (wizard, DNS, certificate) is described in the
[Stalwart Docker guide](https://stalw.art/docs/install/platform/docker/). Only what
matters for this setup is covered here.

### 3.1 Wizard: choose the internal directory

In the wizard (screen 3) choose **"Use the internal directory"**. That creates the
administrator account `admin@example.com` you sign in with. AD is attached as the
directory afterwards.

### 3.2 Recovery administrator as a safety net

Once an external directory is active, accounts only appear at their first sign-in,
and an AD account does not automatically get admin rights. So set a recovery
administrator while you switch (details:
[Docker guide, *Special cases › External directory*](https://stalw.art/docs/install/platform/docker/#external-directory)):

```yaml
    environment:
      STALWART_RECOVERY_ADMIN: "admin:<long-password>"
      LDAP_BIND_PASSWORD: "<password of svc-stalwart>"
```

The password of `svc-stalwart` goes into the container's environment as well, so
it is not stored in Stalwart's configuration. Re-create the container
(`docker compose up -d`). Remove `STALWART_RECOVERY_ADMIN` again **after** Step 3.

### 3.3 Create the directory

WebUI: `https://mail.example.com/admin` → **Settings › Authentication ›
Directories** → new directory of type **Ldap**. As an object (JSON form used by
the Stalwart docs, [LDAP Server](https://stalw.art/docs/auth/backend/ldap/)):

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

Explained:

- `filterLogin` allows sign-in with the **e-mail address or the UPN** and excludes
  **disabled** accounts (`userAccountControl` bit 2). Stalwart clients sign in
  with the full e-mail address.
- `urlFailover` (second DC) is a Stalwart **Enterprise** feature. In the Community
  edition drop that line and set only `url`.
- AD never reveals password hashes, hence `bindAuthentication: true` (the default).

Then select the directory as the authentication directory (**Settings ›
Authentication**, field *Directory* / `directoryId`).

### 3.4 Trusting the AD CA

Stalwart has to trust the domain controllers' certificate. How Stalwart picks up a
**private CA** is not described in the Stalwart docs. Proceed in this order:

1. **CA in the container's trust store.** Mount the CA file and set
   `SSL_CERT_FILE` to a bundle of the public root certificates **plus** your AD CA.
   A bundle containing only the AD CA would break Stalwart's connections to
   Let's Encrypt and GitHub.

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
2. Test a sign-in with an AD user (Step 3.5). If Stalwart reports a certificate
   error (a `store.ldap-…` event in `docker logs stalwart`), this variant does not
   work.
3. **For testing only:** `allowInvalidCerts: true` on the directory turns the check
   off. Do not leave it on — passwords travel over this connection.

### 3.5 Test sign-in and assign an administrator

1. Sign in with an AD user (`https://mail.example.com/account`, user name =
   `jdoe@example.com`). The first time, Stalwart creates the local account.
2. Sign in as the recovery administrator and give the account of your future
   administrator an administrator role (Docker guide, section *Special cases ›
   External directory*).
3. Remove `STALWART_RECOVERY_ADMIN` from the compose file, `docker compose up -d`.

## Step 4: Install disclaimrNG

```bash
cd /opt
git clone https://github.com/Compose-IT-Systemhaus/disclaimrNG.git disclaimrng
cd disclaimrng
git checkout v0.3.3            # the latest release tag
cp .env.example .env
chmod 600 .env
```

`ad-ca.pem` is already in `/opt/disclaimrng/certs/` (Step 1.3); Compose mounts that
directory.

Set at least the following in `.env` (replace the examples, generate passwords
yourself, e.g. `openssl rand -base64 33`):

```dotenv
DJANGO_SECRET_KEY=<openssl rand -base64 48>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000
DJANGO_TIME_ZONE=Europe/Berlin
DJANGO_LANGUAGE_CODE=en

POSTGRES_PASSWORD=<password>
DATABASE_URL=postgres://disclaimr:<password>@db:5432/disclaimr

# Admin UI local only: reach it through an SSH tunnel (ssh -L 8000:127.0.0.1:8000 host)
WEB_BIND=127.0.0.1

# Declare the tenant and Active Directory
TENANTS=example
TENANT_EXAMPLE_NAME=Example
TENANT_EXAMPLE_DOMAINS=example.com

LDAP_SERVERS=ad
LDAP_SERVER_AD_NAME=Active Directory
LDAP_SERVER_AD_FLAVOR=ad
LDAP_SERVER_AD_BASE_DN=DC=corp,DC=example,DC=com
LDAP_SERVER_AD_URL=ldaps://dc1.corp.example.com,ldaps://dc2.corp.example.com
LDAP_SERVER_AD_BIND_DN=CN=svc-disclaimr,OU=Service Accounts,DC=corp,DC=example,DC=com
LDAP_SERVER_AD_BIND_PASSWORD=<password of svc-disclaimr>
LDAP_SERVER_AD_TENANT=example
```

The variables are described in [Directory servers](../directory-servers/) and
[Tenants](../tenants/). The tenant maps the sender domain to the AD; otherwise you
would have to pick the directory in every action.

> disclaimrNG's default AD search filter is
> `(|(mail=%s)(userPrincipalName=%s))`. If your users have alias addresses
> (`proxyAddresses`), set `LDAP_SERVER_AD_SEARCH_QUERY` to
> `(|(mail=%s)(userPrincipalName=%s)(proxyAddresses=smtp:%s))`.

### 4.1 The compose overlay for Stalwart

The repository contains `compose.stalwart.yml`. It puts the **milter** into the
`mailnet` network under the name `disclaimrng-milter`. The AD CA needs no overlay:
`compose.yml` mounts the `./certs` directory into `web` and `milter`, and the
entrypoint sets `LDAPTLS_CACERT` automatically as soon as `ad-ca.pem` is there
(Step 1.3). The log then shows `LDAPS: trusting the CA in /etc/ssl/ad/ad-ca.pem`.
Alternatively, upload the CA on the directory server in the admin (field *CA certificate
file*); it then applies to that server only and needs no mount.

```bash
docker compose -f compose.yml -f compose.stalwart.yml up -d --build
docker compose -f compose.yml -f compose.stalwart.yml ps
```

Expected: `db`, `web` and `milter` with status `healthy`. On the first start,
`docker compose logs web | grep -A3 -i password` shows the admin password.

> From now on use both `-f` files for **all** compose commands (or put
> `COMPOSE_FILE=compose.yml:compose.stalwart.yml` into `.env`).

Check that Stalwart's network sees the milter:

```bash
docker run --rm --network mailnet python:3.12-slim python -c \
  "import socket; socket.create_connection(('disclaimrng-milter', 5000), 3).close(); print('milter reachable')"
```

## Step 5: Signature and rule in disclaimrNG

Open the admin through the SSH tunnel (`http://localhost:8000/`), sign in as
`admin` and change the password. Under **Settings → Directory servers → Active
Directory** press **Test connection**: expected `bind + base search ok` for both
URLs. Then **Discover attributes** — it fills the placeholder editor with real AD
attributes.

Build the signature, rule and action as in the [Walkthrough](../walkthrough/)
(steps 3 to 6). These values apply to this setup:

| Field | Value |
|---|---|
| Requirement → Sender | `@example\.com$` |
| Requirement → Recipient | `.*` (or only external recipients, see below) |
| Requirement → Sender IP | `0.0.0.0` / netmask `0` (any client; Stalwart does the restricting) |
| Action → Resolve sender | on (and "fail when unable to resolve" as you prefer) |
| Action → Directory servers | empty — the tenant `example` supplies the AD |

Example signature (text):

```
{resolver["displayName"]}
{resolver["title"]}
{rt}Phone: {resolver["telephoneNumber"]}{/rt}
```

With `{rt}…{/rt}` the line disappears when the attribute is empty.

> **Only mail to outside recipients?** The `recipient` regex has to match **at
> least one** recipient. "Only if someone is external": requirement Recipient
> `^(?!.*@example\.com$)` — it matches as soon as **one** recipient is not
> internal. Mail to any number of internal recipients plus one external gets the
> signature.

Check the rule on the **Signature test** page (sender `jdoe@example.com`,
external recipient). The result matches what the milter does in production.

## Step 6: Add the milter in Stalwart

WebUI: **Settings › MTA › Filters › Milters** → new milter
([Stalwart: Milter filters](https://stalw.art/docs/mta/filter/milter/)):

| Field | Value | Why |
|---|---|---|
| `host` | `disclaimrng-milter` | network alias from `compose.stalwart.yml` |
| `port` | `5000` | |
| `stages` | `data` only | disclaimrNG does not need the early stages |
| `enable` | `authenticated_as != ''` | only **submitted** mail from signed-in users; inbound mail from the internet is left alone |
| `useTls` | off | internal Docker network |
| `protocolVersion` | `v6` (default) | |
| `tempFailOnError` | on (default) — see below | |
| Timeouts | defaults (30 s / 30 s / 60 s) | |

As a JSON object:

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

**`tempFailOnError`:** if the milter is unreachable or crashes, Stalwart answers
`451 4.3.5`; the client retries later and **no mail leaves without a signature**.
With it off, mail keeps flowing **unsigned** during a milter outage. If the
signature is a legal requirement, leave it on. An AD outage does not stop mail —
only the AD part of the signature is missing (the whole signature, depending on
"fail when unable to resolve").

## Step 7: Secure the network and operations

- The milter port is **not** reachable from the internet: `compose.yml` publishes
  it on `127.0.0.1` only; Stalwart reaches it through the internal network
  `mailnet`.
- disclaimrNG's admin only via SSH tunnel/VPN (`WEB_BIND=127.0.0.1`).
- `.env` with `chmod 600`; the passwords of `svc-disclaimr` and `svc-stalwart` live
  only there and in the Stalwart container's environment.
- Backups: the Postgres volume `pgdata` and the media volume of disclaimrNG, plus
  Stalwart's `stalwart-etc` and `stalwart-data` volumes.

## Step 8: Acceptance test

1. **Network:** the test from Step 4.1 prints `milter reachable`.
2. **Send mail:** with a mail client (server `mail.example.com`, port 465,
   SSL/TLS, user `jdoe@example.com`) send a mail to an **external** address.
3. **Check the signature:** at the recipient, the signature must show name,
   title and phone number **from AD**.
4. **Logs:**

   ```bash
   docker compose -f compose.yml -f compose.stalwart.yml logs --tail=50 milter
   ```

   Expected: a line `Adding Disclaimer (Action: … | Rule: … | Disclaimer: …)`.
5. **DKIM:** the headers of the received mail show `dkim=pass` — the signature
   must not have broken DKIM.
6. **Display:** open the mail in a second client (line breaks, umlauts in the
   signature, HTML and text part).
7. **Outage test:** `docker compose … stop milter`, send again. With
   `tempFailOnError` on, the client reports `451`/delivery later; after
   `start milter` the mail goes through with its signature.
8. **Inbound mail:** a mail from outside to a user gets **no** signature (the
   milter is only active for signed-in sessions).

## Operations

| Task | How |
|---|---|
| Update disclaimrNG | `git fetch --tags && git checkout vX.Y.Z`, then `docker compose -f compose.yml -f compose.stalwart.yml up -d --build`. Migrations run on start. |
| Update Stalwart | pull tag `v1` (`docker compose pull && docker compose up -d`); for bigger jumps see the [Stalwart docs](https://stalw.art/docs/). |
| Change the password of `svc-disclaimr` | change it in AD, update `LDAP_SERVER_AD_BIND_PASSWORD` in `.env`, `docker compose … up -d` (the sync writes it to the DB on start). |
| AD CA was renewed | replace `certs/ad-ca.pem`, `docker compose … restart web milter`; rebuild the CA bundle for Stalwart. |
| Switch the signature off quickly | disable the milter in Stalwart (or set `enable` to `false`); mail flows unsigned immediately. |
| Logs | `docker compose … logs -f milter`, `docker logs -f stalwart` |

## Troubleshooting

| Symptom | Cause and remedy |
|---|---|
| Client gets `451 4.3.5` when sending | Milter unreachable or crashed. `docker compose … ps` (healthy?), the network test from Step 4.1, `host` in Stalwart = `disclaimrng-milter`? Check `docker compose … logs milter` for `Unhandled error`. |
| Mail goes through but **without** a signature | (1) Milter not active in Stalwart: `enable` only matches signed-in sessions. (2) No rule matches: try the **Signature test** with sender/recipient. (3) The recipient regex matches no recipient. (4) "fail when unable to resolve" is on and the AD lookup failed. |
| Signature without AD data (empty fields) | The sender is not found in AD: is `mail` set on the user? Alias address? Then extend `SEARCH_QUERY` (Step 4). In the milter log: `Cannot resolve email …`. Before 0.3.2 a base DN on the domain root (`DC=…,DC=…`) always gave empty fields (`Multiple results found` in the log) — update. |
| **Test connection**: `certificate not trusted` | The uploaded/mounted file is not the certificate of the CA that issued the DC certificate (Step 1.3). |
| **Test connection**: `the certificate is not issued for …` | *Hosts* holds the IP address or a short name; enter the FQDN from the DC certificate (`dc1.corp.example.com`). |
| **Test connection**: `unreachable` / `ldap error` (before 0.3.2 also for certificate problems) | Network/port 636, host name in the certificate, CA not trusted. Check `docker compose … logs web \| grep LDAPS` (must show `trusting the CA`) and `docker compose … exec web ls -l /etc/ssl/ad` (is `ad-ca.pem` there? exact file name, readable for user 1000?). |
| **Test connection**: `invalid credentials` | Bind DN/password of `svc-disclaimr`; quote special characters in the password in `.env` if needed. |
| Stalwart: sign-in with an AD user fails | `filterLogin` too strict (account disabled, no `mail`/UPN?), wrong `bindDn`/password, CA not trusted (Step 3.4). `docker logs stalwart` shows the LDAP message. |
| After switching to AD nobody gets into the WebUI as admin | Set a recovery administrator (`STALWART_RECOVERY_ADMIN`, see Step 3.2) and give the AD account the administrator role. |

## Further reading

- [Installation](../installation/), [Configuration](../configuration/)
- [Directory servers](../directory-servers/), [Tenants](../tenants/)
- [Signatures & rules](../signatures/), [Walkthrough](../walkthrough/)
- Stalwart: [Milter filters](https://stalw.art/docs/mta/filter/milter/),
  [filter overview](https://stalw.art/docs/mta/filter/),
  [LDAP Server](https://stalw.art/docs/auth/backend/ldap/),
  [Docker](https://stalw.art/docs/install/platform/docker/)
