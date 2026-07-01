"""
CanonicalCandidate — the normalized, merged, confidence-scored candidate profile.

This model is the central artifact of the entire pipeline. It is constructed
once by the Merge Engine and is immutable thereafter. Every downstream stage
(Projection, Validation, Report) reads from it — nothing writes to it.

Design notes:
    - ``model_config = ConfigDict(frozen=True)`` enforces immutability.
    - All collection fields default to empty lists (never None) so consumers
      can always iterate without None-guards.
    - ``provenance`` maps canonical field names → list of ProvenanceRecord,
      preserving the full history even for fields with one source.
    - ``confidence`` maps canonical field names → FieldConfidence, allowing
      per-field score inspection.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .field_confidence import FieldConfidence
from .provenance import ProvenanceRecord
from .sub_models import (
    EducationEntry,
    ExperienceEntry,
    Link,
    Location,
    SkillEntry,
)

# Increment this when the canonical schema changes in a breaking way.
_PIPELINE_VERSION = "1.0.0"


class CanonicalCandidate(BaseModel):
    """Fully merged, normalized, and confidence-scored candidate profile.

    Attributes:
        candidate_id:       Deterministic UUID derived from the candidate's
                            primary email (or a random UUID if none found).
        full_name:          Title-cased full name.
        emails:             Deduplicated, lowercase-normalized email list.
        phones:             Deduplicated, E.164-formatted phone list.
        location:           Parsed location sub-model.
        links:              Normalized professional links.
        headline:           Professional headline / current role summary.
        years_experience:   Total years of professional experience.
        skills:             Deduplicated list of canonical skill entries.
        experience:         Chronological work history (newest first).
        education:          Education records (newest first).
        provenance:         Field → list of ProvenanceRecord audit trail.
        confidence:         Field → FieldConfidence scores.
        overall_confidence: Weighted average across all field confidences.
        warnings:           Non-fatal issues encountered during processing
                            (e.g., unparseable phone, unknown skill).
        pipeline_version:   Schema version tag for forward-compatibility.
        created_at:         UTC timestamp of profile creation.
    """

    model_config = ConfigDict(frozen=True)

    # ── Identity ──────────────────────────────────────────────────────────
    candidate_id: str = Field(..., description="Deterministic UUID")
    full_name: str | None = Field(default=None, description="Title-cased full name")

    # ── Contact ───────────────────────────────────────────────────────────
    emails: list[str] = Field(
        default_factory=list,
        description="Lowercase, deduplicated email addresses",
    )
    phones: list[str] = Field(
        default_factory=list,
        description="E.164 formatted, deduplicated phone numbers",
    )

    # ── Profile ───────────────────────────────────────────────────────────
    location: Location | None = None
    links: list[Link] = Field(default_factory=list)
    headline: str | None = None
    years_experience: float | None = Field(
        default=None,
        ge=0.0,
        description="Total professional experience in years",
    )

    # ── Qualifications ────────────────────────────────────────────────────
    skills: list[SkillEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)

    # ── Quality metadata ──────────────────────────────────────────────────
    provenance: dict[str, list[ProvenanceRecord]] = Field(
        default_factory=dict,
        description="Per-field audit trail",
    )
    confidence: dict[str, FieldConfidence] = Field(
        default_factory=dict,
        description="Per-field confidence scores",
    )
    overall_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Weighted average confidence across all fields",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal processing warnings",
    )

    # ── System metadata ───────────────────────────────────────────────────
    pipeline_version: str = Field(default=_PIPELINE_VERSION)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
