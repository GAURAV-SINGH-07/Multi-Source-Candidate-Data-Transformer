"""
URL normalizer — standardizes raw URL strings and infers platform.

Normalization steps:
    1. Strip whitespace.
    2. Add ``https://`` if no scheme is present.
    3. Normalize ``www.`` prefix (retain it for display but standardize).
    4. Strip trailing slashes.
    5. Infer platform (``linkedin``, ``github``, ``portfolio``, ``other``).

The ``infer_platform`` helper is exposed separately because it is also used
by the PDF extractor when categorizing extracted URLs.
"""

import re
from urllib.parse import urlparse, urlunparse

from .result import NormalizationResult

# Platform detection: ordered from most-specific to least-specific
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("linkedin", re.compile(r"linkedin\.com", re.IGNORECASE)),
    ("github", re.compile(r"github\.com", re.IGNORECASE)),
    ("gitlab", re.compile(r"gitlab\.com", re.IGNORECASE)),
    ("twitter", re.compile(r"twitter\.com|x\.com", re.IGNORECASE)),
    ("stackoverflow", re.compile(r"stackoverflow\.com", re.IGNORECASE)),
    ("medium", re.compile(r"medium\.com", re.IGNORECASE)),
    ("behance", re.compile(r"behance\.net", re.IGNORECASE)),
    ("dribbble", re.compile(r"dribbble\.com", re.IGNORECASE)),
    ("kaggle", re.compile(r"kaggle\.com", re.IGNORECASE)),
]

_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def normalize_url(raw: str) -> NormalizationResult:
    """Normalize *raw* URL to a canonical ``https://`` form.

    Args:
        raw: Raw URL string (with or without scheme).

    Returns:
        :class:`NormalizationResult` with a standardized URL and platform.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None,
            success=False,
            factor=0.0,
            method="empty_input",
            original=raw,
            warning="Empty URL string",
        )

    stripped = raw.strip()
    had_scheme = bool(_SCHEME_RE.match(stripped))

    # Add scheme if missing
    url_with_scheme = stripped if had_scheme else f"https://{stripped}"

    try:
        parsed = urlparse(url_with_scheme)
        # Validate that we have at least a netloc
        if not parsed.netloc:
            raise ValueError(f"No hostname found in URL: '{url_with_scheme}'")

        # Normalize: lowercase scheme + host, remove trailing slash from path
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "",
            parsed.params,
            parsed.query,
            "",  # strip fragment — fragments are client-side only
        ))

        platform = infer_platform(normalized)
        factor = 1.0 if had_scheme else 0.90

        return NormalizationResult(
            value=normalized,
            success=True,
            factor=factor,
            method="url_normalized" if had_scheme else "url_scheme_added",
            original=raw,
            warning=None if had_scheme else f"Added 'https://' scheme to '{stripped}'",
        )

    except Exception as exc:
        return NormalizationResult(
            value=stripped,
            success=False,
            factor=0.30,
            method="url_parse_failed",
            original=raw,
            warning=f"URL parse error: {exc}",
        )


def infer_platform(url: str) -> str:
    """Infer the platform name from *url*.

    Args:
        url: A normalized URL string.

    Returns:
        Platform name string: ``"linkedin"``, ``"github"``, etc., or
        ``"other"`` if no known pattern matches.
    """
    for platform, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return platform
    return "other"
