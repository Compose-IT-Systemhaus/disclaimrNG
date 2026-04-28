# disclaimrNG documentation

disclaimrNG is a modernised, dockerized fork of [dploeger/disclaimr][upstream] —
a [milter](https://www.milter.org/) daemon that automatically appends
signatures (also called disclaimers or footers) to outgoing email,
optionally pulling per-user data (name, title, phone, …) from LDAP or
Active Directory.

[upstream]: https://github.com/dploeger/disclaimr

## What's in this guide

1. **[Installation](installation/)** — Docker Compose, Traefik example,
   environment variables.
2. **[Configuration](configuration/)** — first-boot admin, Django
   settings, MEDIA / static files.
3. **[Tenants](tenants/)** — multi-tenant setup; one signature scheme
   per customer / domain.
4. **[Directory servers](directory-servers/)** — LDAP / AD setup,
   attribute discovery, query templates.
5. **[Signatures & rules](signatures/)** — the editor, image picker,
   resolver placeholders, requirements, actions.
6. **[Walkthrough — domain signature](walkthrough/)** — step-by-step:
   "Configure a signature for ``@example.com`` that pulls the sender's
   name and phone from AD."
7. **[Troubleshooting](troubleshooting/)** — common errors and how to
   read the logs.

## Quick links

- **Admin UI**: this server's admin (you're logged in as a staff user
  if you can read this page).
- **Source code**: <https://github.com/Compose-IT-Systemhaus/disclaimrNG>
- **Issue tracker**: <https://github.com/Compose-IT-Systemhaus/disclaimrNG/issues>

## Architecture in one diagram

```
                    ┌────────────────────┐
   outgoing mail ── │  Postfix / Sendmail│ ── milter (5000) ──┐
                    └────────────────────┘                    │
                                                              ▼
   ┌──────────┐         ┌──────────────┐         ┌────────────────────┐
   │  LDAP /  │ ◄────── │   milter     │ ◄─────► │   PostgreSQL       │
   │   AD     │         │   daemon     │         │  (rules, templates)│
   └──────────┘         └──────────────┘         └────────────────────┘
                                                              ▲
                                                              │
                                              ┌──────────────────┐
                                              │  Django web UI   │ ── browser
                                              │  (admin + editor)│
                                              └──────────────────┘
```

The **web container** runs the admin you're using right now. The
**milter container** is what your MTA (Postfix, Sendmail) connects to
on port 5000 to apply signatures. Both share the same database and
configuration; the milter is read-only against it.
