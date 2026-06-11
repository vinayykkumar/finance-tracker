"""SMS template parsers — v1.

Design principles
-----------------
* **Explicit templates, not open-ended regex soup.**  Each bank variant is a named
  ``SmsTemplate`` in the ``TEMPLATES`` list.  Adding template N+1 means appending
  one more ``SmsTemplate(...)`` entry — nothing else changes.
* **Short-circuit on obvious non-financial signals** (OTPs, promos) before any
  template is tried.
* **Parsed payload is structured** (dict with typed keys) — downstream consumers do
  not need to parse strings further.

How to add template N+1
-----------------------
1. Give it a unique key, e.g. ``'kotak_credit_v1'``.
2. Write a ``sender_re`` that matches the normalized sender (uppercase, alphanum only).
3. Write a ``body_re`` with at least a named group ``amount``.  Optional groups:
   ``account_mask``, ``merchant``, ``bank_ref``.
4. Append ``SmsTemplate(key=..., tx_type=..., sender_re=..., body_re=...)`` to ``TEMPLATES``.
5. Add a golden-fixture test in ``tests/sms_ingest/test_parser.py``.

The golden-fixture table at the bottom of ``test_parser.py`` shows the expected shape.
"""

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal


ParseStatus = Literal["parsed", "unparsed"]


@dataclass(frozen=True)
class ParsedPayload:
    template_key: str
    tx_type: Literal["debit", "credit"]
    currency: str
    # Amount as a canonical decimal string, e.g. "5000.00"
    amount: str
    account_mask: str | None
    merchant: str | None
    bank_ref: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_amount(raw: str) -> str:
    """'5,000.00' → '5000.00';  '5000' → '5000';  strips currency prefixes."""
    s = re.sub(r"[^\d.,]", "", raw)          # keep only digits, comma, dot
    s = s.replace(",", "")                   # drop thousands separators
    try:
        d = Decimal(s)
        # Always produce at least two decimal places for consistency
        return format(d, "f")
    except InvalidOperation:
        return s  # best-effort — caller stores whatever we return


@dataclass
class SmsTemplate:
    """A single bank / message-type variant."""

    key: str
    tx_type: Literal["debit", "credit"]
    # Matched against the normalized sender (uppercase, alphanum only)
    sender_re: re.Pattern
    # Named groups: ``amount`` required; ``account_mask``, ``merchant``, ``bank_ref`` optional
    body_re: re.Pattern
    currency: str = "INR"

    def try_match(self, sender_key: str, body: str) -> ParsedPayload | None:
        """Return a ``ParsedPayload`` if both sender and body patterns match; else None."""
        if not self.sender_re.search(sender_key):
            return None
        m = self.body_re.search(body)
        if not m:
            return None
        groups = m.groupdict()
        amount_raw = groups.get("amount", "")
        return ParsedPayload(
            template_key=self.key,
            tx_type=self.tx_type,
            currency=self.currency,
            amount=_clean_amount(amount_raw),
            account_mask=groups.get("account_mask") or None,
            merchant=groups.get("merchant") or None,
            bank_ref=groups.get("bank_ref") or None,
        )


# ---------------------------------------------------------------------------
# Template registry — order matters: first match wins.
# ---------------------------------------------------------------------------

TEMPLATES: list[SmsTemplate] = [
    # ------ State Bank of India ------
    SmsTemplate(
        key="sbi_debit_v1",
        tx_type="debit",
        sender_re=re.compile(r"SBI", re.I),
        body_re=re.compile(
            r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"(?:\s+(?:is\s+)?(?:debited|Debited)|[^\n]*debited)",
            re.I,
        ),
    ),
    SmsTemplate(
        key="sbi_credit_v1",
        tx_type="credit",
        sender_re=re.compile(r"SBI", re.I),
        body_re=re.compile(
            r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"(?:\s+(?:is\s+)?(?:credited|Credited)|[^\n]*credited)",
            re.I,
        ),
    ),
    # ------ HDFC Bank ------
    SmsTemplate(
        key="hdfc_debit_v1",
        tx_type="debit",
        sender_re=re.compile(r"HDFC", re.I),
        body_re=re.compile(
            r"(?:Rs\.?|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"[^\n]*(?:debited|Debited)",
            re.I,
        ),
    ),
    SmsTemplate(
        key="hdfc_credit_v1",
        tx_type="credit",
        sender_re=re.compile(r"HDFC", re.I),
        body_re=re.compile(
            r"(?:Rs\.?|INR)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"[^\n]*(?:credited|Credited)",
            re.I,
        ),
    ),
    # ------ ICICI Bank ------
    SmsTemplate(
        key="icici_debit_v1",
        tx_type="debit",
        sender_re=re.compile(r"ICICI", re.I),
        body_re=re.compile(
            r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"[^\n]*(?:debited|has been debited|Debited)",
            re.I,
        ),
    ),
    SmsTemplate(
        key="icici_credit_v1",
        tx_type="credit",
        sender_re=re.compile(r"ICICI", re.I),
        body_re=re.compile(
            r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"[^\n]*(?:credited|has been credited|Credited)",
            re.I,
        ),
    ),
    # ------ Axis Bank ------
    SmsTemplate(
        key="axis_debit_v1",
        tx_type="debit",
        sender_re=re.compile(r"AXIS", re.I),
        body_re=re.compile(
            r"(?:INR|Rs\.?)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)"
            r"[^\n]*(?:debited|Debited)",
            re.I,
        ),
    ),
]

# ---------------------------------------------------------------------------
# Short-circuit guards — checked BEFORE any template, client-side style.
# ---------------------------------------------------------------------------

# OTP / auth messages — never financial transaction alerts
_OTP_RE = re.compile(
    r"\b(?:OTP|one.?time.?(?:password|pass(?:code)?|code)|passcode|verification\s+code)\b",
    re.I,
)
# Must contain at least one of these for us to bother parsing
_FINANCIAL_RE = re.compile(
    r"\b(?:debited|credited|debit|credit|payment|transaction|transfer|INR|Rs\.?|balance)\b",
    re.I,
)


def normalize_sender(raw: str) -> str:
    """Strip non-alphanumeric characters and uppercase.

    '  +91-SBI-INB ' → 'SBIINB',  '9876543210' → '9876543210'
    """
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def try_parse(sender_key: str, body: str) -> tuple[ParsedPayload | None, ParseStatus]:
    """Attempt template matching; return (payload, status).

    ``status`` is either ``'parsed'`` (a template matched) or ``'unparsed'``
    (no match or short-circuited).  Callers must never see ``'rejected'`` from
    here — rejection happens in the service layer before parse is attempted.
    """
    # Guard: OTP / auth codes → skip silently
    if _OTP_RE.search(body):
        return None, "unparsed"
    # Guard: no financial keywords at all → not worth storing
    if not _FINANCIAL_RE.search(body):
        return None, "unparsed"

    for tmpl in TEMPLATES:
        result = tmpl.try_match(sender_key, body)
        if result is not None:
            return result, "parsed"

    # Financial keywords present but no template matched — store as unparsed
    # so operators can see volume and prioritise new template work.
    return None, "unparsed"
