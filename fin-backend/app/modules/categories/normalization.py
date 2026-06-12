"""Shared category-slug normalization.

Both ``ledger_transactions.category_slug`` and ``budget_rules.category_slug``
are free-form strings tied together only by string equality. Without a shared
canonical form, "Food", "food ", and "FOOD" would silently be three different
categories — spend would split across them and a budget rule for "food" would
never match "Food".

This normalizes to a single canonical form: lowercase, trimmed, internal
whitespace/punctuation collapsed to single hyphens, restricted to
``[a-z0-9_-]``. It is applied at write time (transaction and budget rule
schemas) and defensively at read time (aggregation query) so pre-existing,
un-normalized rows still match.
"""

import re

_WHITESPACE_RE = re.compile(r"\s+")
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
_REPEATED_DASH_RE = re.compile(r"-{2,}")

MAX_CATEGORY_SLUG_LENGTH = 64


def normalize_category_slug(value: str) -> str:
    """Return the canonical form of a category slug.

    Raises ``ValueError`` if the result would be empty (e.g. input was only
    whitespace/punctuation).
    """
    s = value.strip().lower()
    s = _WHITESPACE_RE.sub("-", s)
    s = _INVALID_CHARS_RE.sub("-", s)
    s = _REPEATED_DASH_RE.sub("-", s)
    s = s.strip("-_")
    if not s:
        raise ValueError("category_slug must contain at least one alphanumeric character")
    return s[:MAX_CATEGORY_SLUG_LENGTH]
