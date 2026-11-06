# Mail logs

Under **Settings → Logs** you can see which mails passed through the milter and
which signature was added. The page is visible to **administrators only**
(superusers) — staff users with individual model permissions do not see it, not
even by URL.

## What the list shows

| Column | Meaning |
|---|---|
| Time | When the milter received the end of the mail body. |
| Sender / Recipient | Envelope addresses. With several recipients, the first one a requirement matched, otherwise the first recipient. |
| Subject | Value of the ``Subject`` header. |
| Signature added | Ticked when at least one action changed the mail. |
| Applied signatures | One ``rule → action → signature`` line per action. |

The detail page also shows the MTA's queue ID (if it sends one — Stalwart does
not) and the IP of the submitting client.

Rule, action and signature are stored **as text**, so an entry stays readable
even if you later rename or delete the signature.

## Hiding unprocessed mails

**Every** mail the milter sees is logged — including those no rule matched
(box empty, no signature line). By default the list shows both. Use the filter
**Signature added → Yes** in the right-hand column to hide the unprocessed
mails; **No** shows only those, for instance to find out why a mail got no
signature.

Search covers sender, recipient, subject, queue ID and the applied signatures;
the date navigation above the list narrows down to a year, month or day.

## Retention

Entries are deleted automatically after **30 days**. Set the period in
``.env``:

```dotenv
MAIL_LOG_RETENTION_DAYS=30   # 0 = keep forever
```

Then run ``docker compose up -d`` (web and milter read the variable at start).
Cleanup is done by the **milter container** at startup and then at most once an
hour; while it is not running, old entries stay. As an administrator you can
also delete entries by hand in the list (select → "Delete selected logs").

## Limits

- Only what the **milter** sees is logged. Mails the MTA does not hand to the
  milter (for example Stalwart without the milter enabled for that submission,
  see the runbook) do not appear.
- Aborted connections and mails the MTA drops before the end of the body have
  no entry.
- Entries contain **mail addresses and subject lines in clear text**, which is
  personal data. Choose the retention period to fit your data protection
  rules.
- Every mail that reaches the milter creates one database row. At very high
  mail volume choose a shorter period.
