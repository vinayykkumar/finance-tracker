"""Fixture-driven parser tests.

Every file in ``tests/fixtures/sms/*.json`` is a golden fixture:
``{"sender": ..., "body": ..., "expected": <ParsedSms.to_payload() | null>}``.
A null ``expected`` asserts the body is honestly reported as *unparsed*
(no template guesses).
"""

import json
from pathlib import Path

import pytest
from app.modules.sms_messages.parsers import parse_sms
from app.modules.sms_messages.service import normalize_body

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sms"
FIXTURE_PATHS = sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda p: p.stem)
def test_sms_fixture(fixture_path: Path) -> None:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    body = normalize_body(data["body"])
    parsed = parse_sms(body)

    if data["expected"] is None:
        assert parsed is None, f"{fixture_path.name}: expected no template match, got {parsed}"
    else:
        assert parsed is not None, f"{fixture_path.name}: expected a template match, got None"
        assert parsed.to_payload() == data["expected"]


def test_at_least_one_happy_and_one_unparsed_fixture() -> None:
    """Sanity check that the golden set covers both match and no-match cases."""
    statuses = []
    for fixture_path in FIXTURE_PATHS:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        statuses.append(data["expected"] is not None)
    assert any(statuses), "no happy-path fixture found"
    assert not all(statuses), "no unparsed fixture found"
