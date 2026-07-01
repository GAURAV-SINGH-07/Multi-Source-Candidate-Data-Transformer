"""
Source priority and reliability constants.

These constants drive the Merge Engine's deterministic decision-making.
Changing source priority requires editing only this file — no pipeline
logic changes are needed.

``SOURCE_PRIORITY``:
    Lower number = higher priority. Used to pick the winning value when
    sources conflict. The recruiter CSV is considered most authoritative
    because it has been explicitly curated by a human recruiter.

``SOURCE_RELIABILITY``:
    Float in [0.0, 1.0]. Represents the expected accuracy of a source
    and feeds directly into the FieldConfidence formula. A value of 1.0
    means "this source is almost always correct for the fields it provides".
"""

from src.models.source_type import SourceType

# Lower = higher priority (1 = highest)
SOURCE_PRIORITY: dict[SourceType, int] = {
    SourceType.RECRUITER_CSV:   1,
    SourceType.RESUME_PDF:      2,
    SourceType.RECRUITER_NOTES: 3,
    SourceType.ATS_JSON:        4,
    SourceType.LINKEDIN:        5,
    SourceType.GITHUB:          6,
    SourceType.MANUAL:          0,  
}

# Expected field-level accuracy for each source
SOURCE_RELIABILITY: dict[SourceType, float] = {
    SourceType.RECRUITER_CSV:   1.00,  # Human-curated structured data
    SourceType.RESUME_PDF:      0.85,  # Self-reported; regex extraction
    SourceType.RECRUITER_NOTES: 0.70,  # Unstructured; interpretation needed
    SourceType.ATS_JSON:        0.80,  # System-generated; usually reliable
    SourceType.LINKEDIN:        0.75,  # Self-reported; public profile
    SourceType.GITHUB:          0.90,  # Code-derived; highly reliable for skills
    SourceType.MANUAL:          1.00,  # Human override
}


def get_priority(source: SourceType) -> int:
    """Return the numeric priority for *source*. Lower is better."""
    return SOURCE_PRIORITY.get(source, 99)


def get_reliability(source: SourceType) -> float:
    """Return the reliability weight for *source* (0.0 – 1.0)."""
    return SOURCE_RELIABILITY.get(source, 0.5)
