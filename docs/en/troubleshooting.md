# Troubleshooting

Symptoms first, then diagnoses. ``docker compose logs web`` and
``docker compose logs milter`` are your friends — most issues land a
clear traceback there.

## "Bad Request (400)" on the admin

```
django.core.exceptions.DisallowedHost: Invalid HTTP_HOST header: '192.168.x.x:8000'
```

Your hostname/IP isn't in ``DJANGO_ALLOWED_HOSTS``. Add it to ``.env``:

```dotenv
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,signatures.example.com,192.168.x.x
```

Then ``docker compose up -d``.

## Admin renders without CSS

Probably ``DJANGO_DEBUG=False`` (correctly) but the static files
weren't collected. The entrypoint runs ``collectstatic`` automatically —
if you're seeing this in dev, ``docker compose up --build`` should fix
it. WhiteNoise serves the result; no nginx required.

## ``relation "disclaimrwebadmin_…" does not exist``

The disclaimrwebadmin app's migrations weren't applied. The Dockerfile
runs ``makemigrations`` at build time and the entrypoint runs
``migrate`` at boot — make sure you're on a recent build:

```bash
git pull
docker compose up -d --build
```

If you've recently added a model field by hand (working copy edit), run:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

## Signaturtest hangs / 500s

Two likely causes:

1. **Bad regex in a Requirement.** A pattern like ``*example.com``
   (instead of ``.*example\.com``) makes ``re.compile`` raise — the
   pipeline now catches that and shows a friendly banner. Edit the
   offending Requirement (Sender / Recipient / Header / Body field).
2. **Unreachable LDAP server.** Connections now have a 5 s timeout
   per URL, but if all URLs are bad you'll wait up to N×5 s. Check
   the configured Directory server URLs.

## ``denied`` when starting the stack

```
Error response from daemon: pull access denied for ghcr.io/...
```

The published image isn't public yet (or you're on an air-gapped
host). The compose files use ``pull_policy: build`` so a fresh
checkout builds locally — just run:

```bash
docker compose up -d --build
```

## Milter container restarts in a loop

Check ``docker compose logs milter``. Common ones:

- ``relation "disclaimrwebadmin_requirement" does not exist`` — see
  above.
- ``ldap.SERVER_DOWN`` — your DirectoryServer URL is wrong; the
  milter retries every few seconds.
- ``Address already in use`` — port 5000 is taken on the host. Map
  to another port via ``compose.yml``.

## Signature didn't show up on the actual mail

1. Run **Signature test** with the sender / recipient / body of a
   mail that should have triggered it. The result panel tells you
   immediately whether a rule matched.
2. If the test says "no rule matched" but you expected one — open the
   Rule and check the Sender regex. ``alice@example.com`` does NOT
   match ``example\.com`` — you need ``.*@example\.com``.
3. If the test says it matched but the real mail didn't get the
   signature — check Postfix:
   - ``postconf smtpd_milters`` — points at the right host:port?
   - ``postconf milter_default_action`` — should be ``accept`` (so
     mail still flows when the milter is down) but **not**
     ``no-action`` (which skips milters altogether for some events).
   - ``mailq`` and ``cat /var/log/mail.log`` — any
     ``milter-reject`` / connection errors?

## Reset the admin password

```bash
docker compose exec web python manage.py bootstrap_admin --reset
```

Banner-printed in ``docker compose logs web``.

## Where do uploaded images go?

Docker named volume ``media`` by default. To bind-mount a host path:

```dotenv
MEDIA_HOST_PATH=/srv/disclaimrng/media
```

Files live at ``signatures/<slug>/<filename>``. Re-uploading under the
same slug doesn't delete the old file — old versions stay on disk
until you remove them manually.
