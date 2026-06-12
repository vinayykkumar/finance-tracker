# SMS bank alerts — privacy note (v1)

This feature is **opt-in, user-authorized ingest** of bank/UPI transaction
SMS — not background scraping. It is off by default and can be turned off
at any time from **Settings → SMS bank alerts**.

## What never leaves the device

- **Anything, while the feature is off.** No SMS are read unless the user
  has explicitly enabled sync (Settings toggle) and granted Android's
  `READ_SMS` permission.
- **Messages that look like one-time codes or credentials.** Any message
  whose body matches OTP / PIN / CVV / password / "do not share" patterns is
  excluded by the on-device prefilter
  (`src/features/smsSync/prefilter.ts`) before anything is sent, even if it
  came from a bank sender.
- **Messages from senders that don't look like banks** (personal contacts,
  delivery notifications, etc.) — the prefilter requires a DLT-style or
  short alphanumeric sender ID (e.g. `AD-HDFCBK`, `SBIUPI`).
- **Anything not in the scanned window.** Sync reads a bounded recent
  window (default 30 days, capped at 200 messages per scan) and the user
  sees a count *before* confirming — see `SmsSyncScreen`.

## What is sent, when enabled

For each message that passes the prefilter **and** the user confirms the
sync prompt:

- The sender address/ID
- The full message body
- The device-reported timestamp and a device-local message id (for dedupe)

This is sent over the same authenticated, cookie + CSRF-protected session
used for the rest of the app, to `POST /v1/sms-messages/sync`.

## What the backend does with it

- Stores it as a raw ingest row (`sms_messages` table) tied to the signed-in
  user — see `fin-backend/docs/sms-ingest.md` for the schema and API.
- Runs it through a small set of explicit parser templates to extract
  amount/direction/merchant *if* the body matches a known bank SMS shape.
  An unmatched body is stored as `parse_status: "unparsed"` — never guessed.
- Deduplicates by a fingerprint of (user, sender, device message id, body),
  so re-syncing the same SMS is a no-op.
- **Does not** create ledger transactions, map to accounts, or run any
  ML/LLM categorization. This table is an ingest boundary only; those are
  follow-on features that read from it.

## Logging

The mobile app never logs SMS body content. Sync status shown to the user
and any client-side error reporting is limited to counts (scanned, included,
created, duplicate, parsed, unparsed, rejected) and short error strings —
see `describeError()` in `SmsSyncScreen.tsx`.

## Turning it off

Settings → SMS bank alerts → toggle off. This clears the local "last
synced" cursor; nothing further is read from the device. Already-synced
rows remain in your account (consistent with how the rest of your data
works) — deleting synced SMS rows server-side is a follow-on (see
`fin-backend/docs/sms-ingest.md`).
