# SMS bank-alert ingest (v1)

User-authorized ingest of bank/UPI SMS from the user's Android device into a
new `sms_messages` table. This is the **ingest boundary only**:

- **In scope**: storing what arrived, deduping replays, and running it
  through a small set of explicit v1 parser templates.
- **Out of scope** (follow-on work, see bottom): writing
  `ledger_transactions`, mapping to accounts, any LLM/ML categorization,
  and deleting/exporting synced rows.

Mobile-side consent and privacy are covered in
`fin-mobile/PRIVACY-SMS.md`.

## Data model — `sms_messages`

`fin-backend/app/models/sms_message.py`,
migration `alembic/versions/0003_sms_messages.py`.

| Column | Notes |
| --- | --- |
| `id` | UUID PK |
| `user_id` | FK `users.id` (CASCADE), indexed — every other table follows this user-scoping pattern (see `ledger_transactions`, `financial_accounts`) |
| `source` | `"sms"` today; left open for e.g. `"email"` later without a migration |
| `sender` | raw sender as reported by the device (e.g. `"AD-HDFCBK"`) |
| `sender_key` | normalized (`A-Z0-9` only, uppercased) — `normalize_sender_key()` |
| `device_msg_id` | device SMS-provider id, if available |
| `received_at` | client-reported timestamp (subject to clock skew — see below) |
| `body` | normalized (whitespace-collapsed) body, truncated to 1600 chars for storage |
| `body_length` | length of the *normalized, untruncated* body — lets ops see how oversized a rejected message was |
| `body_hash` | sha256 of the normalized (untruncated) body |
| `fingerprint` | sha256 dedupe key — see below. `UNIQUE (user_id, fingerprint)` |
| `parse_status` | `"parsed"` \| `"unparsed"` \| `"rejected"` |
| `parser_template` | name of the matching template, if `parsed` |
| `parsed_payload` | JSON (JSONB on Postgres) — see "Parsed payload shape" below |
| `reject_reason` | `"body_too_long"` \| `"invalid_sender"` \| `null` |
| `ledger_transaction_id` | **unused placeholder** FK → `ledger_transactions.id` (`SET NULL`) for a follow-on feature; nothing in this slice reads or writes it |
| `created_at` / `updated_at` | server clock |
| `deleted_at` | soft-delete column, mirrors `ledger_transactions` (unused by any endpoint yet, but `list_for_user`/`get_for_user` already filter it out so soft-delete can be added later without an API change) |

Indexes: `user_id`, `sender_key`, `(user_id, received_at)`, `deleted_at`,
plus the `(user_id, fingerprint)` unique constraint.

### Why `postgresql.UUID` + `JSON().with_variant(JSONB(), "postgresql")`

Every other model in this codebase uses `postgresql.UUID` and
`postgresql.JSONB` directly (see `AuditEvent`). `postgresql.UUID` happens to
compile fine on SQLite, but plain `postgresql.JSONB` does not. Using
`JSON().with_variant(JSONB(), "postgresql")` for `parsed_payload` keeps
production on native `jsonb` while letting `tests/conftest.py` run the full
FastAPI app (session auth + CSRF) against an in-memory SQLite DB — no
Postgres needed for the integration test suite.

### Dedupe fingerprint

```
fingerprint = sha256(f"{user_id}:{sender_key}:{device_msg_id or ''}:{body_hash}")
```

`(user_id, fingerprint)` is a unique constraint. Re-syncing the same SMS
(e.g. the device re-reads its SMS provider from scratch) is a no-op: the
service tries the insert inside a `SAVEPOINT`; on `IntegrityError` it
re-selects the existing row and reports `duplicate: true` with the same
`id`. This is also the concurrency-safe path if two sync requests race.

`received_at` is **not** part of the fingerprint — see "Clock skew" below.

## API

`fin-backend/app/api/v1/sms_messages.py`, prefix `/v1/sms-messages`. Same
auth/CSRF/CORS stack as every other `/v1/*` route
(`require_session_user_id`, `CsrfProtectMiddleware`).

### `POST /v1/sms-messages/sync`

Request:

```json
{
  "messages": [
    {
      "sender": "AD-HDFCBK",
      "body": "Rs.500.00 debited from A/c XX1234 on 12-06-26 to VPA shop@okhdfcbank. Avl Bal Rs.9,500.00",
      "received_at": "2026-06-11T10:00:00Z",
      "device_msg_id": "12345"
    }
  ]
}
```

- `messages`: 1–50 items (`MAX_BATCH_SIZE`). Empty or >50 → `422`.
- `body`: 1–6000 chars at the schema layer (`MAX_INGEST_BODY_LEN`, a hard
  guard against absurd payloads). Bodies over **1600** chars
  (`MAX_BODY_STORAGE_LEN` — realistic max for a 10-segment concatenated SMS)
  are truncated for storage and the row is persisted with
  `parse_status="rejected"`, `reject_reason="body_too_long"` — still
  recorded (so the client doesn't retry forever) but never parsed.
- `sender`: 1–64 chars. If it normalizes to nothing (e.g. `"!!!"`), the row
  is persisted with `parse_status="rejected"`, `reject_reason="invalid_sender"`.

Response: per-item results plus summary counts.

```json
{
  "results": [
    {
      "id": "...", "device_msg_id": "12345", "fingerprint": "...",
      "duplicate": false, "parse_status": "parsed",
      "parser_template": "generic_debit_inr_v1", "reject_reason": null
    }
  ],
  "received": 1, "created": 1, "duplicates": 0,
  "parsed": 1, "unparsed": 0, "rejected": 0
}
```

### Rate limit

`app/modules/sms_messages/throttle.py` mirrors the existing
`app/auth/login_throttle.py` pattern: max 6 sync calls per user per 60s,
in-process (not multi-replica safe — same caveat as login throttling, swap
for Redis before scaling out). Combined with the 50-message batch cap this
bounds a single user to ~300 messages/minute. Over the limit → `429`.

### `GET /v1/sms-messages` / `GET /v1/sms-messages/{id}`

List (paginated via `limit`/`offset`, optional `parse_status` filter) and
get-by-id, both scoped to `require_session_user_id` like every other
resource (`accounts`, `transactions`, ...). 404 if the id belongs to another
user or doesn't exist.

## Parsing — v1 templates

`app/modules/sms_messages/parsers.py`. Three explicit, named, regex-based
templates (data-driven, not "regex soup" — each is a
`(name, direction, compiled pattern)` tuple with named capture groups):

1. `generic_debit_inr_v1` — "Rs.500.00 debited from A/c XX1234 on 12-06-26
   to VPA shop@okhdfcbank. Avl Bal Rs.9,500.00" (balance/date/merchant all
   optional)
2. `generic_credit_inr_v1` — "INR 1,200.00 credited to your A/c XX5678 on
   12-Jun-2026 from ABC CORP. Avail Bal: INR 45,000.00"
3. `upi_spent_v1` — "You have spent Rs 250.00 from account ending 1234 to
   Big Bazaar on 12-06-2026. UPI Ref No 123456789012"

`parse_sms(body)` tries each in order and returns the first match, or
`None`. `None` is persisted as `parse_status="unparsed"` — **never guessed**.
Golden fixtures live in `tests/fixtures/sms/*.json`
(`tests/test_sms_parsers.py` is fixture-driven), including:

- `generic_debit_inr_v1_happy.json` / `..._no_balance.json` — happy path,
  with and without the optional balance clause
- `generic_credit_inr_v1_happy.json`, `upi_spent_v1_happy.json`
- `unparsed_otp.json` — an OTP message must never be parsed as a transaction
- `unparsed_bank_promo.json` — a bank-sender promo that mentions "Rs"/"a/c"
  but isn't a transaction alert; honest no-match, not a misfire

### Parsed payload shape

```json
{
  "template": "generic_debit_inr_v1",
  "direction": "debit",
  "amount": "500.00",
  "currency": "INR",
  "account_tail": "1234",
  "merchant": "VPA shop@okhdfcbank",
  "balance_after": "9500.00",
  "txn_date": "12-06-26"
}
```

All fields except `template`, `direction`, `amount`, `currency` are
optional and omitted (not `null`-filled) when the SMS didn't include them.
`amount`/`balance_after` are decimal strings (commas stripped, two decimal
places preserved). `txn_date` is the date **as written in the SMS** —
no timezone-bearing parse is attempted in v1 (see follow-ons).

### Adding template N+1

See the docstring in `parsers.py` for the full checklist: pick a stable
`name` (stored permanently in `parser_template`), add a fixture under
`tests/fixtures/sms/<name>.json` with a real (anonymized) body and the exact
expected payload (or `"expected": null` for an unparsed fixture), write the
regex with named groups, append it to `TEMPLATES` (order matters — first
match wins), run `pytest tests/test_sms_parsers.py`.

## Edge cases

| Case | Behavior | Test |
| --- | --- | --- |
| Duplicate upload of the same SMS (separate sync calls) | Second call returns `duplicate: true`, same `id`/`fingerprint`; no new row | `test_duplicate_upload_does_not_double_insert` |
| Duplicate within the same batch | First item created, second reported as `duplicate: true` with the same id; one row total | `test_duplicate_within_same_batch_does_not_double_insert` |
| Clock skew (device clock far ahead/behind server) | `received_at` is stored as reported (naive timestamps assumed UTC); not part of the fingerprint, so dedupe and ingestion are unaffected. Server `created_at` is the authoritative receipt time. | `test_clock_skew_received_at_is_tolerated` |
| Message over size limits | Body > 1600 chars (normalized) is truncated for storage; row persisted with `parse_status="rejected"`, `reject_reason="body_too_long"`, `body_length` retains the original size | `test_oversized_body_is_truncated_and_rejected` |
| User revokes permission mid-sync | Mobile-side: `SmsSyncScreen` re-checks permission before scanning and catches a revoke during the native read, turns the local toggle off, and reports how many of the batch (if any) were already sent — already-sent items are durable (idempotent by fingerprint), so a retry after re-enabling won't double up. API-side: an empty/undersized batch is simply rejected by validation (`messages` requires ≥1 item) | `test_empty_batch_is_rejected` (API); `SmsSyncScreen.onSyncNow` (mobile) |
| Unparsed template | Body doesn't match any of the 3 v1 templates → `parse_status="unparsed"`, `parser_template=null`, `parsed_payload=null` — stored, not discarded, for a future template/iteration to revisit | `test_otp_message_is_unparsed_not_guessed`, `unparsed_otp`/`unparsed_bank_promo` fixtures |
| Sender that looks like a bank but fails validation | `sender` normalizes to an empty `sender_key` (e.g. `"!!!"`) → `parse_status="rejected"`, `reject_reason="invalid_sender"`, regardless of body content | `test_invalid_sender_is_rejected` |

## Out of scope / follow-ons

- **Ledger linking**: `ledger_transaction_id` exists as an unused nullable
  FK. A follow-on feature reads `parse_status="parsed"` rows and creates
  `ledger_transactions`, setting this column.
- **Account mapping**: matching `account_tail`/`sender` to a specific
  `financial_accounts` row.
- **LLM/ML categorization**: assigning `category_slug` from
  `parsed_payload.merchant` — explicitly not attempted here.
- **Deleting synced rows** / a "forget my SMS data" endpoint — `deleted_at`
  is already there for it.
- **Server-side consent record**: v1 consent (toggle + permission) is local
  to the device (`fin-mobile/src/features/smsSync/storage.ts`). A follow-on
  could persist an opt-in timestamp server-side for audit/compliance.
- **More templates**: SBI, Axis, PayTM, etc. — additive via the checklist
  above; no schema changes needed.
- **Timezone-aware `txn_date` parsing** once a representative set of date
  formats is collected from real fixtures.
- **Multi-replica rate limiting**: both `login_throttle` and the new
  `sms sync throttle` are in-process; move to Redis if/when the API runs
  more than one process.
