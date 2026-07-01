"""
SourceType enum — the authoritative list of all supported data sources.

This is the single source of truth for source identifiers. Every extractor,
merger, and provenance record references this enum rather than bare strings,
preventing silent typos from propagating through the pipeline.

Adding a new source (e.g., LINKEDIN) requires only adding an entry here and
creating a new extractor — nothing else changes.
"""

from enum import Enum


class SourceType(str, Enum):
    """Enumeration of all supported candidate data sources.

    Inheriting from ``str`` allows instances to be used directly as JSON
    strings (e.g., ``SourceType.RECRUITER_CSV == "recruiter_csv"`` is True),
    which simplifies serialization without a custom encoder.
    """

    RECRUITER_CSV = "recruiter_csv"
    RESUME_PDF = "resume_pdf"
    RECRUITER_NOTES = "recruiter_notes"  # Reserved — not yet implemented
    ATS_JSON = "ats_json"                # Reserved — not yet implemented
    LINKEDIN = "linkedin"                # Reserved — not yet implemented
    GITHUB = "github"                    # Reserved — not yet implemented
    MANUAL = "manual"                    # For hand-corrected values

