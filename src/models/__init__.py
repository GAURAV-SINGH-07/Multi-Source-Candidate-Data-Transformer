"""
Models sub-package — all Pydantic domain models.

Intentionally contains no business logic. Pure data contracts.

Import graph (no cycles):
    source_type  ←  provenance, raw
    sub_models   ←  candidate
    field_confidence ← candidate
    provenance   ← candidate
    raw          (standalone)
    candidate    (top-level; imports all above)
"""

from .source_type import SourceType
from .provenance import ProvenanceRecord
from .field_confidence import FieldConfidence
from .sub_models import (
    Location,
    Link,
    SkillEntry,
    ExperienceEntry,
    EducationEntry,
)
from .raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from .candidate import CanonicalCandidate

__all__ = [
    "SourceType",
    "ProvenanceRecord",
    "FieldConfidence",
    "Location",
    "Link",
    "SkillEntry",
    "ExperienceEntry",
    "EducationEntry",
    "RawCandidateData",
    "RawExperienceEntry",
    "RawEducationEntry",
    "CanonicalCandidate",
]
