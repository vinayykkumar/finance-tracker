"""v1 SMS parser templates — explicit, data-driven, honest about match vs no-match.

This is intentionally a small set of named templates rather than open-ended
regex soup. Each template is a ``(sender hint, body regex, field mapping)``
tuple. ``parse_sms`` tries each template in order and returns the first
match as a :class:`ParsedSms`, or ``None`` if nothing matches — callers
persist that as ``parse_status="unparsed"`` rather than guessing.

## How to add template N+1

1. Pick a short, stable name, e.g. ``"sbi_debit_v1"``. This string is stored
   in ``sms_messages.parser_template`` for every row it matches, so don't
   rename or reuse names once shipped.
2. Add a fixture file ``tests/fixtures/sms/<name>.json`` with at least one
   real-shaped (anonymized) SMS body and the exact expected parsed payload
   (or ``"expected": null`` for a deliberately-unparsed fixture).
3. Write a ``re.compile(...)`` pattern with named groups drawn from
   :class:`ParsedSms`'s fields (``amount``, ``account``, ``date``,
   ``merchant``, ``balance``; ``currency`` optional).
4. Append an ``SmsTemplate(...)`` entry to ``TEMPLATES``. Order matters —
   first match wins, so put more specific patterns earlier.
5. Run ``pytest tests/test_sms_parsers.py``; it is fixture-driven and will
   automatically pick up the new file.

Templates are matched against a *normalized* body: collapsed whitespace,
case preserved (matching is case-insensitive). Amounts are returned as
plain decimal strings (commas stripped). Dates are returned verbatim as the
SMS wrote them (no timezone-bearing parse is attempted here — that is a
follow-on once a v1 set of date formats is observed in the wild).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

Direction = Literal["debit", "credit"]


@dataclass(frozen=True)
class ParsedSms:
    """Stable shape persisted into ``sms_messages.parsed_payload``."""

    template: str
    direction: Direction
    amount: str
    currency: str
    account_tail: str | None = None
    merchant: str | None = None
    balance_after: str | None = None
    txn_date: str | None = None

    def to_payload(self) -> dict[str, str]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _norm_amount(raw: str) -> str:
    cleaned = raw.replace(",", "").strip()
    try:
        return str(Decimal(cleaned))
    except InvalidOperation:
        return cleaned


def _norm_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip(" .,-")
    return cleaned or None


@dataclass(frozen=True)
class SmsTemplate:
    name: str
    direction: Direction
    pattern: re.Pattern[str]
    default_currency: str = "INR"

    def try_match(self, body: str) -> ParsedSms | None:
        m = self.pattern.search(body)
        if not m:
            return None
        groups = m.groupdict()
        amount = groups.get("amount")
        if not amount:
            return None
        return ParsedSms(
            template=self.name,
            direction=self.direction,
            amount=_norm_amount(amount),
            currency=(groups.get("currency") or self.default_currency).upper(),
            account_tail=_norm_text(groups.get("account")),
            merchant=_norm_text(groups.get("merchant")),
            balance_after=_norm_amount(groups["balance"]) if groups.get("balance") else None,
            txn_date=_norm_text(groups.get("date")),
        )


_AMOUNT = r"(?P<amount>[\d,]+\.\d{2})"
_BALANCE = r"(?P<balance>[\d,]+\.\d{2})"
_DATE = r"(?P<date>\d{1,2}[-/][A-Za-z0-9]{2,4}[-/]\d{2,4})"
_ACCOUNT = r"(?P<account>\d{2,6})"
_MERCHANT = r"[A-Za-z0-9@.&\-_ ]+?"
# "Avl Bal" / "Avail. Bal" / "Available Bal" — the optional trailing balance clause.
_BAL_HINT = r"(?:Avl\.?|Avail\.?|Available)\.?\s*Bal"

TEMPLATES: tuple[SmsTemplate, ...] = (
    # "Rs.500.00 debited from A/c XX1234 on 12-06-26 to VPA shop@okhdfcbank.
    #  Avl Bal Rs.9,500.00"  (balance clause and merchant/date are optional)
    SmsTemplate(
        name="generic_debit_inr_v1",
        direction="debit",
        pattern=re.compile(
            r"(?:Rs\.?|INR)\s*" + _AMOUNT + r"\s*"
            r"(?:has\s+been\s+|is\s+|was\s+)?debited\s+"
            r"(?:from\s+)?(?:your\s+)?(?:A/?c|Acct|Account)\.?\s*(?:No\.?)?\s*[Xx*]*" + _ACCOUNT
            + r"(?:\s+on\s+" + _DATE + r")?"
            + r"(?:\s+to\s+(?P<merchant>" + _MERCHANT + r"))?"
            + r"(?=[.,]?\s*" + _BAL_HINT + r"|[.,]?\s*$)"
            + r"(?:[.,]?\s*" + _BAL_HINT + r"\.?:?\s*(?:Rs\.?|INR)?\s*" + _BALANCE + r")?",
            re.IGNORECASE,
        ),
    ),
    # "INR 1,200.00 credited to your A/c XX5678 on 12-Jun-2026 from ABC CORP.
    #  Avail Bal: INR 45,000.00"
    SmsTemplate(
        name="generic_credit_inr_v1",
        direction="credit",
        pattern=re.compile(
            r"(?:Rs\.?|INR)\s*" + _AMOUNT + r"\s*"
            r"(?:has\s+been\s+|is\s+|was\s+)?credited\s+"
            r"(?:to\s+)?(?:your\s+)?(?:A/?c|Acct|Account)\.?\s*(?:No\.?)?\s*[Xx*]*" + _ACCOUNT
            + r"(?:\s+on\s+" + _DATE + r")?"
            + r"(?:\s+(?:from|by)\s+(?P<merchant>" + _MERCHANT + r"))?"
            + r"(?=[.,]?\s*" + _BAL_HINT + r"|[.,]?\s*$)"
            + r"(?:[.,]?\s*" + _BAL_HINT + r"\.?:?\s*(?:Rs\.?|INR)?\s*" + _BALANCE + r")?",
            re.IGNORECASE,
        ),
    ),
    # "You have spent Rs 250.00 from account ending 1234 to Big Bazaar on
    #  12-06-2026. UPI Ref No 123456789012"
    SmsTemplate(
        name="upi_spent_v1",
        direction="debit",
        pattern=re.compile(
            r"spent\s+(?:Rs\.?|INR)\s*" + _AMOUNT + r"\s*"
            r"(?:from\s+)?(?:your\s+)?account\s+ending\s+" + _ACCOUNT
            + r"(?:\s+to\s+(?P<merchant>" + _MERCHANT + r"))?"
            + r"(?:\s+on\s+" + _DATE + r")?"
            + r"(?=[.,]|\s+UPI|$)",
            re.IGNORECASE,
        ),
    ),
)


def parse_sms(body: str) -> ParsedSms | None:
    """Run ``body`` through the v1 templates, returning the first match.

    ``body`` should already be whitespace-normalized by the caller.
    """
    for template in TEMPLATES:
        parsed = template.try_match(body)
        if parsed is not None:
            return parsed
    return None
