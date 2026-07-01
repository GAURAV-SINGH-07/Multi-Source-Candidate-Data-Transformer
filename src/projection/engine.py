"""
ProjectionEngine — config-driven, non-destructive output shaper.

Takes the immutable CanonicalCandidate and a ProjectionConfig, produces
a plain Python dict that can be serialised to JSON. The canonical model
is never modified — the engine only reads from it.

Output dict contract:
    - Keys are the (possibly renamed) field names.
    - Values are JSON-serialisable Python primitives / dicts / lists.
    - Missing values follow the missing_value_policy.
    - If include_confidence=True, each field key gains a sibling
      ``_confidence`` block containing the FieldConfidence breakdown.
    - If include_provenance=True, each field key gains a sibling
      ``_provenance`` block with the full audit trail.

Design: The engine uses a dispatch table (_FIELD_EXTRACTORS) that maps
canonical field names to extractor callables. This avoids a long if/elif
chain and makes it trivial to add new fields — just add an entry to
the table.
"""

import re
from datetime import datetime
from typing import Any

from src.models.candidate import CanonicalCandidate
from src.models.field_confidence import FieldConfidence
from src.models.provenance import ProvenanceRecord
from src.utils.logging_config import get_logger
from .config import ProjectionConfig

log = get_logger(__name__)

# Sentinel for "field has no value" — distinct from None (which is a valid value)
_MISSING = object()


class ProjectionEngine:
    """Projects a CanonicalCandidate to a custom output dict.

    The engine is stateless and thread-safe. Instantiate once and call
    ``project()`` as many times as needed.
    """

    def project(
        self,
        candidate: CanonicalCandidate,
        config: ProjectionConfig | None = None,
    ) -> dict[str, Any]:
        """Project *candidate* to a JSON-serialisable output dict.

        Args:
            candidate: The immutable canonical profile.
            config:    Projection config. Defaults to
                       :meth:`ProjectionConfig.default` (all fields included).

        Returns:
            A plain dict ready for ``json.dumps()``.

        Raises:
            ValueError: If ``missing_value_policy="error"`` and a required
                        field is absent/empty.
        """
        cfg = config or ProjectionConfig.default()
        output: dict[str, Any] = {}
        policy = cfg.missing_value_policy

        for canonical_name, extractor in _FIELD_EXTRACTORS.items():
            if not cfg.is_included(canonical_name):
                continue

            raw_value = extractor(candidate)
            output_key = cfg.output_key_for(canonical_name)

            # Detect "missing" (None / empty list / empty dict)
            is_missing = self._is_missing(raw_value)

            if is_missing:
                if policy == "error":
                    raise ValueError(
                        f"Field '{canonical_name}' is required but has no value "
                        f"(missing_value_policy='error')."
                    )
                elif policy == "omit":
                    continue
                else:  # "null"
                    output[output_key] = None
                    continue

            output[output_key] = self._serialize(raw_value)

        # Optionally append per-field confidence and provenance sections
        if cfg.include_confidence and candidate.confidence:
            output["_confidence"] = self._serialize_confidences(
                candidate.confidence, cfg
            )

        if cfg.include_provenance and candidate.provenance:
            output["_provenance"] = self._serialize_provenance(
                candidate.provenance, cfg
            )

        log.debug(
            "Projected candidate %s → %d output keys (confidence=%s, provenance=%s)",
            candidate.candidate_id,
            len(output),
            cfg.include_confidence,
            cfg.include_provenance,
        )
        return output

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _serialize(self, value: Any) -> Any:
        """Recursively convert *value* to a JSON-serialisable form."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        # Pydantic models → dict via model_dump
        if hasattr(value, "model_dump"):
            return self._serialize(value.model_dump())
        # Enums → their .value
        if hasattr(value, "value"):
            return value.value
        return str(value)

    def _serialize_confidences(
        self,
        confidences: dict[str, FieldConfidence],
        cfg: ProjectionConfig,
    ) -> dict[str, Any]:
        """Serialise confidence scores for all included, renamed fields."""
        result: dict[str, Any] = {}
        for canonical_name, fc in confidences.items():
            if not cfg.is_included(canonical_name):
                continue
            output_key = cfg.output_key_for(canonical_name)
            result[output_key] = {
                "score": round(fc.score, 4),
                "source_reliability": fc.source_reliability,
                "normalization_factor": fc.normalization_factor,
                "corroboration_bonus": fc.corroboration_bonus,
                "explanation": fc.explanation,
            }
        return result

    def _serialize_provenance(
        self,
        provenance: dict[str, list[ProvenanceRecord]],
        cfg: ProjectionConfig,
    ) -> dict[str, Any]:
        """Serialise provenance records for all included, renamed fields."""
        result: dict[str, Any] = {}
        for canonical_name, records in provenance.items():
            if not cfg.is_included(canonical_name):
                continue
            output_key = cfg.output_key_for(canonical_name)
            result[output_key] = [
                {
                    "source": rec.source.value,
                    "value": self._serialize(rec.value),
                    "method": rec.method,
                    "confidence": round(rec.confidence, 4),
                    "timestamp": rec.timestamp.isoformat(),
                    "notes": rec.notes,
                }
                for rec in records
            ]
        return result

    @staticmethod
    def _is_missing(value: Any) -> bool:
        """Return True if *value* represents an absent field."""
        if value is None:
            return True
        if isinstance(value, (list, dict)) and len(value) == 0:
            return True
        return False


# ---------------------------------------------------------------------------
# Dispatch table: canonical field name → extractor callable
# ---------------------------------------------------------------------------
# Keeping this as a module-level dict (not inside a method) makes it trivial
# to inspect, extend, and test independently of the engine class.

_FIELD_EXTRACTORS: dict[str, Any] = {
    "candidate_id":     lambda c: c.candidate_id,
    "full_name":        lambda c: c.full_name,
    "emails":           lambda c: c.emails,
    "phones":           lambda c: c.phones,
    "location":         lambda c: c.location,
    "links":            lambda c: c.links,
    "headline":         lambda c: c.headline,
    "years_experience": lambda c: c.years_experience,
    "skills":           lambda c: c.skills,
    "experience":       lambda c: c.experience,
    "education":        lambda c: c.education,
    "overall_confidence": lambda c: c.overall_confidence,
    "warnings":         lambda c: c.warnings,
    "pipeline_version": lambda c: c.pipeline_version,
    "created_at":       lambda c: c.created_at,
}
