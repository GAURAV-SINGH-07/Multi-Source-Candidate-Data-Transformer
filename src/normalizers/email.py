"""
Email normalizer — converts raw email strings to a canonical lowercase form.

Normalization steps:
    1. Strip surrounding whitespace.
    2. Lowercase the entire string.
    3. Validate format via a strict-but-practical regex.
    4. Detect and warn about suspicious patterns (e.g., multiple @).

A separate ``deduplicate_emails`` helper removes case-variant duplicates
from a list while preserving insertion order — used by the Merge Engine.
"""

import re
from .result import NormalizationResult

# RFC 5322-inspired regex; intentionally permissive on local-part to avoid
# false negatives on real-world addresses with tags and dots.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def normalize_email(raw: str) -> NormalizationResult:
    """Normalize *raw* email to lowercase and validate its format.

    Args:
        raw: Raw email string.

    Returns:
        :class:`NormalizationResult`. ``factor=1.0`` for a clean valid email,
        ``factor=0.50`` for a lowercase-normalizable but suspicious address,
        ``factor=0.0`` for clearly invalid input.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None,
            success=False,
            factor=0.0,
            method="empty_input",
            original=raw,
            warning="Empty email string",
        )

    stripped = raw.strip()
    normalized = stripped.lower()

    # Sanity check: exactly one '@' character
    if normalized.count("@") != 1:
        return NormalizationResult(
            value=normalized,
            success=False,
            factor=0.30,
            method="malformed_multiple_at_signs",
            original=raw,
            warning=f"Email contains {normalized.count('@')} '@' characters: '{stripped}'",
        )

    if not _EMAIL_RE.match(normalized):
        return NormalizationResult(
            value=normalized,
            success=False,
            factor=0.50,
            method="format_invalid_kept_lowercased",
            original=raw,
            warning=f"Email did not pass format validation: '{normalized}'",
        )

    # Check if we actually did any normalization
    method = "lowercased" if stripped != normalized else "already_lowercase"

    return NormalizationResult(
        value=normalized,
        success=True,
        factor=1.0,
        method=method,
        original=raw,
        warning=None,
    )


def deduplicate_emails(emails: list[str]) -> list[str]:
    """Remove case-variant duplicates from *emails*, preserving insertion order.

    Args:
        emails: List of already-normalized (lowercase) email strings.

    Returns:
        Deduplicated list with original order maintained.
    """
    seen: set[str] = set()
    result: list[str] = []
    for email in emails:
        key = email.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(email)
    return result
