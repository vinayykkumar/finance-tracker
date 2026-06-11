# SMS Ingest — Design & Operations Guide

_Written: 2026-06-11 | Branch: feature/sms-ingest_

---

## Overview

This slice adds **user-authorized bank SMS ingest**: an Android user explicitly
consents to Fin reading their SMS inbox, the app filters and uploads bank
transaction alerts, and the backend stores structured ingest records for
downstream consumption (ledger categorisation, duplicate detection, etc.).

**Explicitly out of scope for this slice:**
- Writing `ledger_transactions` from ingest rows (follow-on task).
- Mapping ingest rows to accounts.
- Any ML or LLM categorisation.

---

## Backend

### Table: `sms_ingest_items`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `user_id` | UUID FK→users | Scoped per user; CASCADE on delete |
| `source` | TEXT | Always `'sms'` in v1; reserved for other channels |
| `sender_key` | TEXT | Normalized sender: uppercase, alphanumeric only |
| `raw_body_hash` | TEXT | SHA-256 hex of raw body — body never stored |
| `device_message_id` | TEXT | Android `_id` field — opaque device identifier |
| `received_at` | TIMESTAMPTZ | Device timestamp |
| `ingested_at` | TIMESTAMPTZ | Server timestamp (auto) |
| `parsed_payload` | JSONB | Structured extraction or NULL |
| `parse_status` | TEXT | `'parsed'` or `'unparsed'` |
| `template_key` | TEXT | Which template matched, e.g. `'sbi_debit_v1'` |
| `dedupe_fingerprint` | TEXT | SHA-256 of `user_id|sender_key|device_message_id` |
| `ledger_tx_id` | UUID FK→ledger_transactions NULL | Placeholder for follow-on |

**Unique constraint:** `(user_id, dedupe_fingerprint)` — guarantees at-most-once
ingest per physical message per user.

### Deduplication

Fingerprint = `SHA-256(user_id | sender_key | device_message_id)`.

If `device_message_id` is empty, the body hash is used instead:
`SHA-256(user_id | sender_key | body_hash)`.

Insert uses `ON CONFLICT DO NOTHING` — safe to retry the same batch.

### Clock skew policy

| Scenario | Behaviour |
|---|---|
| `received_at` > 30 days old | `rejected` → `reason: received_at_too_old` |
| `received_at` > 5 min in future | `rejected` → `reason: received_at_future` |
| `received_at` within ±5 min of now | Accepted (clock skew tolerance) |

### API

```
POST /v1/sms-ingest/batch
Authorization: session cookie
Content-Type: application/json

{
  "items": [
    {
      "device_message_id": "msg_12345",
      "sender": "SBIINB",
      "body": "INR 5,000 debited from SBI a/c XX1234...",
      "received_at": "2026-06-10T14:30:00+05:30"
    }
  ]
}

→ 200
{
  "accepted": 1,
  "duplicates": 0,
  "rejected": []
}
```

Rate limiting: batch max 100 items. No per-minute rate limit in v1 (add
middleware if needed at the reverse proxy layer).

---

## Parser — v1 Templates

Templates live in `fin-backend/app/modules/sms_ingest/parser.py` in the
`TEMPLATES` list.  Order matters: first match wins.

### Current templates

| Key | Bank | tx_type | Sender pattern |
|---|---|---|---|
| `sbi_debit_v1` | SBI | debit | `/SBI/i` |
| `sbi_credit_v1` | SBI | credit | `/SBI/i` |
| `hdfc_debit_v1` | HDFC | debit | `/HDFC/i` |
| `hdfc_credit_v1` | HDFC | credit | `/HDFC/i` |
| `icici_debit_v1` | ICICI | debit | `/ICICI/i` |
| `icici_credit_v1` | ICICI | credit | `/ICICI/i` |
| `axis_debit_v1` | Axis | debit | `/AXIS/i` |

### `parsed_payload` shape

```json
{
  "template_key": "sbi_debit_v1",
  "tx_type": "debit",
  "currency": "INR",
  "amount": "5000.00",
  "account_mask": null,
  "merchant": null,
  "bank_ref": null
}
```

Fields `account_mask`, `merchant`, `bank_ref` are populated when the body
pattern includes named groups (`(?P<account_mask>...)` etc.) and the message
contains those fragments.

### How to add template N+1

1. Open `fin-backend/app/modules/sms_ingest/parser.py`.
2. Add one `SmsTemplate(...)` entry to the `TEMPLATES` list:

```python
SmsTemplate(
    key="kotak_debit_v1",
    tx_type="debit",
    sender_re=re.compile(r"KOTAK", re.I),
    body_re=re.compile(
        r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
        r"[^\n]*(?:debited|Debited)",
        re.I,
    ),
),
```

3. Add a golden-fixture row to `tests/sms_ingest/test_parser.py`:

```python
(
    "kotak_debit",
    "KOTAKB",
    "INR 2,000 debited from Kotak Bank a/c XX5678. Avl Bal INR 15,000.",
    "parsed",
    "kotak_debit_v1",
    "2000",
),
```

4. Run `pytest tests/sms_ingest/test_parser.py` — should go green.

No other files need changing for a new template.

---

## Android — SMS Consent Flow

```
Settings tab
  └── Settings screen  (shows "Bank SMS Sync" card)
        └── SmsSyncScreen  (full-page consent + sync)
              ├── Consent copy (shown before any dialog)
              ├── [Sync Bank SMS] → requestSmsReadPermission()
              │     ├── GRANTED → read inbox → prefilter → upload → show counts
              │     ├── DENIED  → error state, can retry
              │     └── BLOCKED → error state, deep link to App Settings
              └── Success / error card with counts
```

### Prefilter heuristics (client-side, before upload)

| Condition | Action |
|---|---|
| Body contains OTP keyword | Skip (not uploaded) |
| Body has no financial keywords | Skip |
| Body shorter than 20 chars | Skip |
| Passes all checks | Upload |

### Permission revocation mid-sync

Android cannot revoke a permission while the app is in the foreground.
Mid-sync revocation is handled on the next app launch: `checkSmsReadPermission()`
returns false, sync does not start.  No partial upload state to clean up.

---

## Follow-on tasks

1. **Ledger linkage**: a background job that reads `parse_status='parsed'` rows
   and creates `ledger_transactions`, then sets `ledger_tx_id`.
2. **New templates**: Yes Bank, Kotak, PNB, etc. — follow the N+1 guide above.
3. **Unparsed monitoring**: expose a count of `parse_status='unparsed'` rows to
   ops so they can prioritise template work.
4. **Rate limiting**: add a per-user rate limit on `/v1/sms-ingest/batch` at the
   app or proxy layer.
5. **iOS**: Apple does not expose an inbox-reading API; consider a mail-forwarding
   or push-notification path for bank alerts on iOS.
