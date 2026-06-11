# Privacy — Bank SMS Sync

_Last updated: 2026-06-11_

## What we read

When you enable Bank SMS Sync, Fin requests the Android `READ_SMS` permission
and reads messages from your inbox that arrived in the last 30 days (maximum
200 messages per sync).

## What stays on your device

The following are filtered **locally on your device** and are **never
transmitted**:

| Filtered out | Reason |
|---|---|
| OTPs and one-time passcodes | Detected by keyword (`OTP`, `one time password`, `passcode`, etc.) |
| Messages with no financial keywords | No `debited`, `credited`, `INR`, `Rs.`, `payment`, etc. |
| Messages shorter than 20 characters | Too short to carry useful structure |

## What is sent to our servers

For each message that passes the local filter, we upload:

| Field | What it is |
|---|---|
| `device_message_id` | The Android content-provider `_id` — opaque to us |
| `sender` | Normalized sender key (e.g. `SBIINB`), not a raw phone number |
| `body` | **The full message body** — read by the server to extract structured data, then stored only as a SHA-256 hash. The plaintext is discarded immediately after parsing. |
| `received_at` | Device-reported timestamp |

### What the server stores

| Stored | Not stored |
|---|---|
| SHA-256 hash of message body | Raw message body |
| Parsed amount, type (debit/credit), account mask | Account number in full |
| Sender key | Full phone number or personal contact name |
| Device message ID | Any other message metadata |

## Why we need `READ_SMS`

Bank transaction alerts arrive as regular SMS messages.  There is no bank-specific
API on Android that provides these alerts without this permission.

## Revoking access

You can disable SMS sync at any time:

1. Open **Settings** on your device.
2. Tap **Apps** → **Fin** → **Permissions**.
3. Revoke **SMS** access.

After revocation, Fin will no longer read new messages.  Data already synced
remains in your account; contact support to delete it.

## Google Play policy

`READ_SMS` is classified under the **SMS or Call Log** Sensitive App
Permissions policy.  Fin uses it solely for reading bank transaction alerts
with explicit user consent.  It is not used for advertising, analytics, or
any purpose other than the feature described above.

## Data retention

SMS ingest rows are scoped to your user account and deleted when you delete
your account.  There is no separate retention schedule for ingest rows in v1.
