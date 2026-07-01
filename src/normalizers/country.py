"""
Country normalizer — converts raw country strings to ISO 3166-1 Alpha-2 codes.

Lookup strategy (in order of confidence):
    1. Direct Alpha-2 code match (e.g., ``"IN"`` → ``"IN"``)
    2. Direct Alpha-3 code match (e.g., ``"IND"`` → ``"IN"``)
    3. Exact country name match via ``pycountry``
    4. Known alias lookup (handles "USA", "UK", "UAE", etc.)
    5. Common city → country lookup for partial location strings
    6. Fuzzy match via ``pycountry.countries`` with rapidfuzz
"""

import re
import pycountry
from rapidfuzz import process as fuzz_process, fuzz

from .result import NormalizationResult

# Hand-curated aliases not covered well by pycountry
_COUNTRY_ALIASES: dict[str, str] = {
    "usa": "US", "u.s.a": "US", "u.s.a.": "US",
    "united states": "US", "united states of america": "US",
    "uk": "GB", "u.k": "GB", "u.k.": "GB", "great britain": "GB",
    "uae": "AE", "u.a.e": "AE", "u.a.e.": "AE",
    "south korea": "KR", "north korea": "KP",
    "russia": "RU", "czech republic": "CZ",
    "taiwan": "TW", "hong kong": "HK",
    "iran": "IR", "syria": "SY", "vietnam": "VN",
}

# Major tech-hub cities → country (for parsing "Bangalore, India" etc.)
_CITY_TO_COUNTRY: dict[str, str] = {
    "bangalore": "IN", "bengaluru": "IN", "mumbai": "IN", "delhi": "IN",
    "hyderabad": "IN", "chennai": "IN", "pune": "IN", "kolkata": "IN",
    "new delhi": "IN", "noida": "IN", "gurgaon": "IN", "gurugram": "IN",
    "san francisco": "US", "new york": "US", "seattle": "US",
    "austin": "US", "boston": "US", "chicago": "US", "los angeles": "US",
    "london": "GB", "manchester": "GB", "edinburgh": "GB",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "berlin": "DE", "munich": "DE", "frankfurt": "DE",
    "paris": "FR", "amsterdam": "NL", "stockholm": "SE",
    "singapore": "SG", "sydney": "AU", "melbourne": "AU",
    "dubai": "AE", "abu dhabi": "AE",
    "tokyo": "JP", "osaka": "JP", "beijing": "CN", "shanghai": "CN",
    "bangkok": "TH", "jakarta": "ID", "kuala lumpur": "MY",
}

# Build pycountry name → alpha_2 lookup once at import time
_PYCOUNTRY_NAMES: dict[str, str] = {
    c.name.lower(): c.alpha_2 for c in pycountry.countries
}


def normalize_country(raw: str) -> NormalizationResult:
    """Normalize *raw* to an ISO 3166-1 Alpha-2 country code.

    Args:
        raw: Country name, code, or location string (e.g., ``"India"``,
             ``"IN"``, ``"Bangalore, India"``, ``"USA"``).

    Returns:
        :class:`NormalizationResult` with a 2-letter ISO code on success.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None, success=False, factor=0.0,
            method="empty_input", original=raw, warning="Empty country string",
        )

    stripped = raw.strip()
    lower = stripped.lower()

    # 1. Direct Alpha-2 match
    upper = stripped.upper()
    if re.match(r"^[A-Z]{2}$", upper):
        try:
            country = pycountry.countries.get(alpha_2=upper)
            if country:
                return _ok(upper, "direct_alpha2", raw)
        except KeyError:
            pass

    # 2. Alpha-3 match
    if re.match(r"^[A-Za-z]{3}$", stripped):
        try:
            country = pycountry.countries.get(alpha_3=stripped.upper())
            if country:
                return _ok(country.alpha_2, "alpha3_to_alpha2", raw)
        except (KeyError, AttributeError):
            pass

    # 3. Exact pycountry name match
    if lower in _PYCOUNTRY_NAMES:
        return _ok(_PYCOUNTRY_NAMES[lower], "exact_country_name", raw)

    # 4. Alias lookup
    if lower in _COUNTRY_ALIASES:
        return _ok(_COUNTRY_ALIASES[lower], "alias_lookup", raw)

    # 5. Location string — try splitting on comma and checking each part
    for part in re.split(r"[,/|]+", stripped):
        part_lower = part.strip().lower()
        if part_lower in _PYCOUNTRY_NAMES:
            return NormalizationResult(
                value=_PYCOUNTRY_NAMES[part_lower],
                success=True,
                factor=0.90,
                method="location_string_split",
                original=raw,
                warning=f"Extracted country from location string: '{part.strip()}'",
            )
        if part_lower in _COUNTRY_ALIASES:
            return NormalizationResult(
                value=_COUNTRY_ALIASES[part_lower],
                success=True,
                factor=0.90,
                method="location_string_alias",
                original=raw,
                warning=None,
            )
        # City lookup
        if part_lower in _CITY_TO_COUNTRY:
            return NormalizationResult(
                value=_CITY_TO_COUNTRY[part_lower],
                success=True,
                factor=0.75,
                method="city_to_country_inference",
                original=raw,
                warning=f"Inferred country from city: '{part.strip()}'",
            )

    # 6. Fuzzy match against all pycountry country names
    all_names = list(_PYCOUNTRY_NAMES.keys())
    result = fuzz_process.extractOne(
        lower, all_names, scorer=fuzz.WRatio, score_cutoff=85
    )
    if result:
        match_name, score, _ = result
        alpha2 = _PYCOUNTRY_NAMES[match_name]
        return NormalizationResult(
            value=alpha2,
            success=True,
            factor=0.65,
            method=f"fuzzy_country_match(score={score:.1f})",
            original=raw,
            warning=f"Fuzzy-matched '{stripped}' → '{match_name}' ({alpha2})",
        )

    return NormalizationResult(
        value=None,
        success=False,
        factor=0.0,
        method="no_match_found",
        original=raw,
        warning=f"Could not resolve country from: '{stripped}'",
    )


def _ok(alpha2: str, method: str, original: str) -> NormalizationResult:
    return NormalizationResult(
        value=alpha2, success=True, factor=1.0,
        method=method, original=original, warning=None,
    )
