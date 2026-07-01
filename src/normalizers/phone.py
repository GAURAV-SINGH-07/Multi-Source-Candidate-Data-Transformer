"""
Phone normalizer — converts raw phone strings to E.164 format.

Strategy:
    1. Try parsing without a region (works for numbers with explicit
       country codes like ``+91 98765 43210``).
    2. If that fails, retry with the configured default country.
    3. If that fails, try a small list of common countries.
    4. If all attempts fail, return the stripped original with a warning
       and a low normalization factor.

The ``phonenumbers`` library handles all formatting variants (spaces,
hyphens, dots, parentheses) so we do not need to pre-clean the string.
"""

import re
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException

from src.config.settings import settings
from .result import NormalizationResult

# Ordered list of fallback regions to try when no country code is present.
# The default_country from settings is prepended at call time.
_FALLBACK_REGIONS = ["IN", "US", "GB", "AU", "CA", "SG", "AE"]


def normalize_phone(
    raw: str,
    default_country: str | None = None,
) -> NormalizationResult:
    """Normalize *raw* phone string to E.164 format.

    Args:
        raw:            Raw phone string in any format.
        default_country: ISO Alpha-2 country code used as fallback region
                         when the number has no explicit country code.
                         Defaults to ``settings.default_country``.

    Returns:
        :class:`NormalizationResult` with E.164 value on success.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None,
            success=False,
            factor=0.0,
            method="empty_input",
            original=raw,
            warning="Empty phone string",
        )

    stripped = raw.strip()
    country = (default_country or settings.default_country).upper()

    # Build the region list: configured default first, then general fallbacks
    regions: list[str | None] = [None, country] + [
        r for r in _FALLBACK_REGIONS if r != country
    ]

    for region in regions:
        result = _try_parse(stripped, region)
        if result is not None:
            e164, parsed_region = result
            if region is None:
                # Parsed without a hint → had explicit country code → highest confidence
                factor = 1.0
                method = "e164_explicit_country_code"
            elif region == country:
                factor = 0.85
                method = f"e164_assumed_region({country})"
            else:
                factor = 0.70
                method = f"e164_fallback_region({region})"
            return NormalizationResult(
                value=e164,
                success=True,
                factor=factor,
                method=method,
                original=raw,
                warning=None,
            )

    return NormalizationResult(
        value=stripped,
        success=False,
        factor=0.30,
        method="unparseable_kept_as_is",
        original=raw,
        warning=f"Could not parse phone number: '{stripped}'",
    )


def _try_parse(raw: str, region: str | None) -> tuple[str, str | None] | None:
    """Attempt to parse *raw* with the given *region*.

    Returns:
        ``(e164_string, region)`` on success, ``None`` on failure.

    Raises:
        Any exception other than :class:`~phonenumbers.NumberParseException`
        propagates to the caller.  ``NumberParseException`` is the only
        documented failure mode of ``phonenumbers.parse()`` for invalid
        input; all other exceptions indicate a bug and should be visible.
    """
    try:
        parsed = phonenumbers.parse(raw, region)
        if phonenumbers.is_valid_number(parsed):
            e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
            return e164, region
    except NumberParseException:
        # Expected: the string is not a valid phone number for this region.
        # Try the next region in the fallback list.
        pass
    return None
