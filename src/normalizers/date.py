"""
Date normalizer — converts raw date strings to YYYY-MM format.

Uses ``python-dateutil`` for broad format support, then formats the result
as YYYY-MM. Special cases:
    - "Present" / "Current" / "Now" → returns None (caller interprets as ongoing)
    - Year-only strings ("2019") → "2019-01" with a reduced confidence factor
    - Unparseable strings → original value with warning

``python-dateutil`` defaults ambiguous dates to today's date components,
so ``parse("March 2021")`` correctly yields ``2021-03-01`` (not today's day).
"""

import re
from datetime import datetime, timezone

from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from .result import NormalizationResult

# Strings that mean "the position/education is ongoing"
_PRESENT_ALIASES = frozenset({
    "present", "current", "now", "ongoing", "till date", "till now",
    "to date", "today", "—", "-",
})

# Match bare four-digit years
_YEAR_ONLY_RE = re.compile(r"^\d{4}$")


def normalize_date(raw: str) -> NormalizationResult:
    """Normalize *raw* date string to ``YYYY-MM`` format.

    Args:
        raw: Any date-like string (e.g., ``"March 2021"``, ``"2021-03-15"``,
             ``"03/2021"``, ``"Present"``, ``"2019"``).

    Returns:
        :class:`NormalizationResult`:
            - ``value="YYYY-MM"`` on success
            - ``value=None`` for "present/current" indicators
            - ``value=raw`` on failure with warning
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None,
            success=False,
            factor=0.0,
            method="empty_input",
            original=raw,
            warning="Empty date string",
        )

    stripped = raw.strip()

    # Handle "present" / "current" markers
    if stripped.lower() in _PRESENT_ALIASES:
        return NormalizationResult(
            value=None,
            success=True,
            factor=1.0,
            method="present_marker",
            original=raw,
            warning=None,
        )

    # Year-only: coerce to January of that year with reduced confidence
    if _YEAR_ONLY_RE.match(stripped):
        return NormalizationResult(
            value=f"{stripped}-01",
            success=True,
            factor=0.70,
            method="year_only_defaulted_to_january",
            original=raw,
            warning=f"Only year provided; defaulted to {stripped}-01",
        )

    # Full dateutil parse — use a fixed default date so ambiguous parts
    # (missing month/day) default to January 1st, not today.
    _DEFAULT_DATE = datetime(datetime.now(timezone.utc).year, 1, 1)
    try:
        parsed = dateutil_parser.parse(stripped, default=_DEFAULT_DATE)
        formatted = parsed.strftime("%Y-%m")

        # If the original string contained only month+year, factor stays 1.0.
        # If it had a full day (day is explicit in input), still 1.0.
        return NormalizationResult(
            value=formatted,
            success=True,
            factor=1.0,
            method="dateutil_parse",
            original=raw,
            warning=None,
        )
    except (ParserError, OverflowError, ValueError):
        pass

    return NormalizationResult(
        value=stripped,
        success=False,
        factor=0.30,
        method="unparseable_kept_as_is",
        original=raw,
        warning=f"Could not parse date: '{stripped}'",
    )
