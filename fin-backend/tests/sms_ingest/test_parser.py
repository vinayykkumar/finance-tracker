"""Parser unit tests — zero I/O, zero DB.

Golden-fixture format
---------------------
Each fixture is a tuple: (label, sender, body, expected_status, expected_template, expected_amount)

``expected_template`` is None when ``expected_status == 'unparsed'``.
``expected_amount`` is None when ``expected_status == 'unparsed'``.

How to add a new golden fixture for template N+1
-------------------------------------------------
1. Implement the template in ``app/modules/sms_ingest/parser.py``.
2. Append a row to ``GOLDEN_FIXTURES`` below with a real SMS body from that bank.
3. Run ``pytest tests/sms_ingest/test_parser.py -v`` — the new case should go green.
"""

import pytest

from app.modules.sms_ingest.parser import normalize_sender, try_parse


# ---------------------------------------------------------------------------
# Golden fixtures: (label, raw_sender, body, exp_status, exp_template, exp_amount)
# ---------------------------------------------------------------------------

GOLDEN_FIXTURES = [
    # ── Happy paths ─────────────────────────────────────────────────────────
    (
        "sbi_debit_simple",
        "SBIINB",
        "INR 5,000.00 debited from SBI a/c XX1234 on 10-06-2026. Avl bal INR 12,345.00.",
        "parsed",
        "sbi_debit_v1",
        "5000.00",
    ),
    (
        "sbi_debit_no_decimal",
        "SBI",
        "Rs.2500 debited from your SBI account ending 5678. Ref 987654321.",
        "parsed",
        "sbi_debit_v1",
        "2500",
    ),
    (
        "hdfc_debit",
        "HDFCBK",
        "Rs.1,200.50 debited from your HDFC Bank account XX4321 for purchase at Amazon.",
        "parsed",
        "hdfc_debit_v1",
        "1200.50",
    ),
    (
        "icici_debit",
        "ICICIB",
        "INR 3,000 has been debited from your ICICI Bank account ending XX9012. Ref: TXN123.",
        "parsed",
        "icici_debit_v1",
        "3000",
    ),
    (
        "axis_debit",
        "AXISBK",
        "INR 750.00 Debited from your Axis Bank account XX6789 on 10-Jun-2026.",
        "parsed",
        "axis_debit_v1",
        "750.00",
    ),
    (
        "sbi_credit",
        "SBIINB",
        "INR 10,000.00 credited to SBI a/c XX1234 on 10-06-2026. Avl bal INR 22,345.00.",
        "parsed",
        "sbi_credit_v1",
        "10000.00",
    ),
    # ── Unparsed — financial keywords present but no template matches ────────
    (
        "unknown_bank_debit",
        "YESBNK",
        "INR 500 debited from your Yes Bank account. Check app for details.",
        "unparsed",
        None,
        None,
    ),
    # ── OTP / auth — short-circuit before template matching ─────────────────
    (
        "otp_message",
        "SBIINB",
        "Your OTP for SBI NetBanking is 987654. Valid for 10 minutes. Do not share.",
        "unparsed",
        None,
        None,
    ),
    (
        "one_time_password",
        "HDFCBK",
        "Your one time password for HDFC NetBanking login is 123456.",
        "unparsed",
        None,
        None,
    ),
    # ── Non-financial — no financial keywords ────────────────────────────────
    (
        "delivery_notification",
        "AMAZON",
        "Your Amazon order #123-456 has been shipped. Expected delivery: 12 June 2026.",
        "unparsed",
        None,
        None,
    ),
    # ── Edge: sender looks like bank, body fails to match template pattern ───
    (
        "sbi_promo_no_amount",
        "SBIINB",
        "Dear customer, exciting new loan offers await you! Visit sbi.co.in for details.",
        "unparsed",
        None,
        None,
    ),
]


@pytest.mark.parametrize(
    "label,raw_sender,body,exp_status,exp_template,exp_amount",
    GOLDEN_FIXTURES,
    ids=[f[0] for f in GOLDEN_FIXTURES],
)
def test_parser_golden(
    label: str,
    raw_sender: str,
    body: str,
    exp_status: str,
    exp_template: str | None,
    exp_amount: str | None,
) -> None:
    sender_key = normalize_sender(raw_sender)
    payload, status = try_parse(sender_key, body)

    assert status == exp_status, f"[{label}] expected status={exp_status!r}, got {status!r}"

    if exp_status == "parsed":
        assert payload is not None, f"[{label}] expected payload, got None"
        assert payload.template_key == exp_template, (
            f"[{label}] expected template={exp_template!r}, got {payload.template_key!r}"
        )
        assert payload.amount == exp_amount, (
            f"[{label}] expected amount={exp_amount!r}, got {payload.amount!r}"
        )
        assert payload.currency == "INR"
    else:
        assert payload is None, f"[{label}] expected None payload, got {payload}"


def test_normalize_sender_strips_non_alphanum() -> None:
    assert normalize_sender("+91-SBI-INB") == "91SBIINB"


def test_normalize_sender_uppercases() -> None:
    assert normalize_sender("hdfcbk") == "HDFCBK"


def test_parsed_payload_to_dict_is_serializable() -> None:
    """ParsedPayload.to_dict() must produce a plain dict (for JSONB storage)."""
    sender_key = normalize_sender("SBIINB")
    body = "INR 100.00 debited from SBI a/c XX1111."
    payload, status = try_parse(sender_key, body)
    assert status == "parsed"
    assert payload is not None
    d = payload.to_dict()
    assert isinstance(d, dict)
    assert d["template_key"] == "sbi_debit_v1"
    assert d["amount"] == "100.00"
    assert d["tx_type"] == "debit"
