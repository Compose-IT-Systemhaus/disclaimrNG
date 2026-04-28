# Walkthrough — signature for ``@example.com``

End-to-end recipe: configure disclaimrNG so every mail leaving
``@example.com`` gets a signature with the sender's **name**,
**title** and **phone number** pulled from Active Directory, plus
your company logo.

This page assumes you already have:

- disclaimrNG running (see [Installation](../installation/)),
- access to an Active Directory under e.g. ``dc=example,dc=com``,
- a service account that can read AD (read-only is fine — bind
  + ``search_s`` is all the milter does),
- a PNG logo to embed.

The whole walkthrough takes ~10 minutes.

---

## Step 1 — Create a tenant

Tenants tie a sender domain to its directory server, so the milter
knows where to look up the sender.

1. Sidebar **Settings → Tenants → Add tenant**.
2. Fill in:
   - **Name**: ``Example Inc.``
   - **Slug**: ``example`` (auto-filled from the name)
3. In the **Tenant domains** inline at the bottom, add one row:
   - **Domain**: ``example.com``
4. Save.

You can add more domains later (``example.de``, ``example.org``) — the
milter matches whichever domain owns the sender's address.

## Step 2 — Add the Active Directory

1. Sidebar **Settings → Directory servers → Add directory server**.
2. Fill in:
   - **Tenant**: ``Example Inc.`` (the one you just created)
   - **Name**: ``Example AD``
   - **Enabled**: ✓
3. Connection block:
   - **Flavour**: *Active Directory* (auto-fills the search query)
   - **Base DN**: ``dc=example,dc=com``
   - **Auth method**: *Simple*
   - **User-DN**: ``CN=disclaimr,OU=Service,DC=example,DC=com``
   - **Password**: (your service account password)
4. Query block — leave the AD defaults
   (``(userPrincipalName=%s)``).
5. URL inline:
   - **URL**: ``ldaps://dc1.example.com``
   - Add a second URL for failover: ``ldaps://dc2.example.com``
6. Save.
7. On the change page, click **Test connection** at the top — both
   URLs should report ``bind + base search ok``.
8. Click **Discover attributes** — this samples a few real entries
   and lists what AD actually has. Copy the relevant attribute names
   (``cn``, ``displayName``, ``title``, ``telephoneNumber``,
   ``mobile``, ``mail``, ``streetAddress``, ``company``,
   ``department``) into **Attribute vocabulary** so they show up in
   the editor's autocomplete.
9. Save again.

## Step 3 — Upload the company logo

1. Sidebar **Signatures → Images → Add image**.
2. Fill in:
   - **Slug**: ``example-logo`` (this is what you'll write in the
     template)
   - **Name**: ``Example Inc. logo``
   - **Image**: pick the PNG from disk
   - **Alt text**: ``Example Inc.``
   - **Display width**: ``180`` (or leave empty for the natural size)
3. Save.

You can also upload directly from the disclaimer editor in step 4.

## Step 4 — Write the disclaimer

1. Sidebar **Signatures → Manage signatures → Add signature**.
2. Fill in:
   - **Tenant**: ``Example Inc.``
   - **Name**: ``Example Inc. — default``
   - **Description**: ``Standard footer for @example.com mail``
3. **Plaintext part** tab → switch to **Code** if you're not there
   already:

   ```text
   --
   {resolver["displayName"]}
   {rt}{resolver["title"]}{/rt}
   Example Inc.
   {rt}Phone: {resolver["telephoneNumber"]}{/rt}
   {rt}Mobile: {resolver["mobile"]}{/rt}
   Web: https://example.com
   ```

   The ``{rt}…{/rt}`` wrappers make the *Phone:* / *Mobile:* lines
   disappear cleanly if the AD entry doesn't have those attributes.
4. **HTML part** tab → tick **Use text part** *off* (we want a
   richer HTML version). Click the **Visual** tab and use the
   toolbar — or stay in **Code**:

   ```html
   <p style="font-family: sans-serif; font-size: 13px; color: #333;">
     <strong>{resolver["displayName"]}</strong>
     {rt}<br>{resolver["title"]}{/rt}<br>
     Example Inc.<br>
     {rt}Phone: <a href="tel:{resolver["telephoneNumber"]}">{resolver["telephoneNumber"]}</a><br>{/rt}
     <a href="https://example.com">example.com</a>
   </p>
   {image["example-logo"]}
   ```

   You can also click on the **Common fields** chips
   (Name / Phone / Email / Address) underneath the editor instead
   of typing the placeholders — they insert the right
   ``{resolver["…"]}`` token at the cursor.
5. Make sure **Use template tags** is on for both parts.
6. Save.

## Step 5 — Wire it up with a rule

1. Sidebar **Signatures → Rules → Add rule**.
2. Fill in:
   - **Tenant**: ``Example Inc.``
   - **Name**: ``Example Inc. — default footer``
   - **Position**: ``0`` (first rule to be evaluated)
3. **Requirements** inline → add one row:
   - **Sender**: ``.*@example\.com``
   - leave the rest at their defaults (``.*``, ``0.0.0.0/0``)
   - **Action**: *Accept rule*
4. **Actions** inline → add one row:
   - **Position**: ``0``
   - **Name**: ``Append default footer``
   - **Action**: *Add a disclaimer string to the body*
   - **Disclaimer**: ``Example Inc. — default``
   - **Resolve sender**: ✓
   - **Directory servers**: leave empty (the milter falls back to
     the tenant's ``Example AD``)
5. Save.

## Step 6 — Test it

1. Sidebar **Signatures → Signature test**.
2. Fill in:
   - **Sender**: ``alice@example.com`` (must be an existing AD user
     for the resolver to find anything)
   - **Recipient**: ``bob@external.tld``
   - **Subject**: ``Hello``
   - **Body**: a couple of lines, anything
3. Click **Run test**.

Expected outcome:

- Green banner: ``1 rule matched``.
- **Matched rules**: ``Example Inc. — default footer``.
- **Modified mail body**: your original lines + the rendered
  signature with ``displayName`` / ``title`` / ``telephoneNumber``
  filled in from AD.
- **Full mail after pipeline** shows the on-the-wire form.

If a placeholder is empty, double-check that the AD attribute name
matches exactly (AD attribute names are case-sensitive in the
template — ``displayName``, not ``displayname``).

## Step 7 — Point Postfix at the milter

In ``main.cf``:

```
smtpd_milters = inet:disclaimrng:5000
non_smtpd_milters = inet:disclaimrng:5000
milter_default_action = accept
milter_protocol = 6
```

``systemctl reload postfix`` and send a real mail from
``alice@example.com`` to your own external address. The signature
should appear at the bottom.

---

## Variations

### Different signatures per department

Add another rule with a tighter ``Header filter`` (``X-Department:
Sales``) or — cleaner — split the AD into separate
DirectoryServer rows by ``base_dn`` (one per OU) and map each to a
different tenant.

### Two domains, same signature

Just add a second domain to the same tenant
(*Settings → Tenants → Example Inc.* → add ``example.de`` to the
domains inline). One rule, one signature, both domains.

### Two domains, different signatures

Create two tenants, each with its own domain. Configure each tenant's
DirectoryServer + Disclaimer + Rule independently. The milter routes
by sender domain at runtime.
