"""Normalizers sub-package — pure, stateless transformation functions.

All normalizers return a :class:`NormalizationResult` carrying:
    - The normalized value (or original on failure)
    - A ``factor`` in [0.0, 1.0] for the Confidence Engine
    - The normalization method used
    - Any non-fatal warning

This uniform contract means the Merge Engine never needs to inspect
normalizer internals.
"""

from .result import NormalizationResult
from .phone import normalize_phone
from .email import normalize_email, deduplicate_emails
from .date import normalize_date
from .name import normalize_name
from .url import normalize_url, infer_platform
from .country import normalize_country
from .skill import normalize_skill, SkillNormalizer

__all__ = [
    "NormalizationResult",
    "normalize_phone",
    "normalize_email",
    "deduplicate_emails",
    "normalize_date",
    "normalize_name",
    "normalize_url",
    "infer_platform",
    "normalize_country",
    "normalize_skill",
    "SkillNormalizer",
]
