"""
RawCandidateData — the extractor output envelope.

This is the intermediate data structure that each extractor produces.
It is intentionally loose: every field is optional because different
sources provide wildly different levels of completeness. The Normalization
Engine tightens this into sub-models; the Merge Engine combines multiple
RawCandidateData instances into one CanonicalCandidate.

Design notes:
    - Uses ``model_config = ConfigDict(extra="allow")`` so that extractors
      can attach source-specific metadata without subclassing.
    - All fields are Optional to reflect the reality of messy source data.
    - ``raw_text`` carries the full PDF text for PDF sources; used by the
      Explainability Engine to show extraction context.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .source_type import SourceType


class RawExperienceEntry(BaseModel):
    """Loosely typed experience entry from an extractor."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    company: str | None = None
    start_date: str | None = None  # Any format — normalizer handles it
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None
    location: str | None = None


class RawEducationEntry(BaseModel):
    """Loosely typed education entry from an extractor."""

    model_config = ConfigDict(extra="allow")

    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: float | None = None


class RawCandidateData(BaseModel):
    """Raw, un-normalized data envelope produced by one extractor run.

    Attributes:
        source:          Which source this data came from.
        source_file:     Path or filename of the source file.
        extracted_at:    UTC timestamp of extraction.
        full_name:       Raw name string.
        emails:          Raw email strings (may have duplicates).
        phones:          Raw phone strings (any format).
        location:        Raw location string.
        links:           Raw URL strings.
        headline:        Raw headline / title string.
        years_experience: Raw years value (may be a string like "5+").
        skills:          Raw skill strings.
        experience:      List of loosely-typed experience entries.
        education:       List of loosely-typed education entries.
        raw_text:        Full extracted text (PDF sources only).
        metadata:        Extractor-specific bag of additional data.
    """

    model_config = ConfigDict(extra="allow")

    # ── Provenance ────────────────────────────────────────────────────────
    source: SourceType
    source_file: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Raw fields ────────────────────────────────────────────────────────
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: str | None = None
    links: list[str] = Field(default_factory=list)
    headline: str | None = None
    years_experience: Any = None  # Could be int, float, str, None

    # ── Structured lists ──────────────────────────────────────────────────
    skills: list[str] = Field(default_factory=list)
    experience: list[RawExperienceEntry] = Field(default_factory=list)
    education: list[RawEducationEntry] = Field(default_factory=list)

    # ── Source-specific extras ────────────────────────────────────────────
    raw_text: str | None = Field(
        default=None,
        description="Full text content (PDF sources only)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extractor-specific additional data",
    )
