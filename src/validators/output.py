"""
Output validator — validates the projected output dict against the expected schema.

Validation runs after the ProjectionEngine produces its output dict and before
the dict is written to disk. It catches:
    - Missing required fields
    - Type violations (e.g., emails is not a list)
    - Value range violations (confidence outside [0, 1])
    - Structural anomalies (empty candidate_id)

Returns structured :class:`ValidationResult` objects — never raises. Callers
decide whether to abort, warn, or continue based on ``is_valid``.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.logging_config import get_logger

log = get_logger(__name__)

# E.164 pattern used for phone validation
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

# UUID4/UUID5 pattern
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[45][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationError:
    """A single validation failure.

    Attributes:
        field:    Output field key where the problem was found.
        message:  Human-readable description of the issue.
        severity: ``"error"`` (output is unusable) or ``"warning"`` (output
                  is usable but has quality issues).
    """

    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationResult:
    """Aggregated result of a validation pass.

    Attributes:
        is_valid: True only if no ``"error"``-severity issues were found.
        errors:   All validation issues (both errors and warnings).
    """

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if no error-severity issues exist."""
        return not any(e.severity == "error" for e in self.errors)

    @property
    def warnings(self) -> list[ValidationError]:
        return [e for e in self.errors if e.severity == "warning"]

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "error")

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def add_error(self, field_name: str, message: str) -> None:
        self.errors.append(ValidationError(field=field_name, message=message, severity="error"))

    def add_warning(self, field_name: str, message: str) -> None:
        self.errors.append(ValidationError(field=field_name, message=message, severity="warning"))

    def summary(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        return (
            f"[{status}] {self.error_count} error(s), {self.warning_count} warning(s)"
        )


def validate_output(output: dict[str, Any]) -> ValidationResult:
    """Validate a projected output dict.

    Checks for structural correctness and known value constraints. Does not
    re-run business logic — only validates the shape and types of the output.

    Args:
        output: Dict produced by :class:`~src.projection.engine.ProjectionEngine`.

    Returns:
        :class:`ValidationResult` with all errors and warnings found.
    """
    result = ValidationResult()

    # ── candidate_id ─────────────────────────────────────────────────────
    _validate_candidate_id(output, result)

    # ── emails ────────────────────────────────────────────────────────────
    _validate_list_of_strings(output, "emails", result)
    for email in output.get("emails") or []:
        if "@" not in str(email):
            result.add_warning("emails", f"Suspicious email value: '{email}'")

    # ── phones ────────────────────────────────────────────────────────────
    _validate_list_of_strings(output, "phones", result)
    for phone in output.get("phones") or []:
        if not _E164_RE.match(str(phone)):
            result.add_warning(
                "phones",
                f"Phone '{phone}' does not appear to be in E.164 format.",
            )

    # ── full_name / name ──────────────────────────────────────────────────
    for key in ("full_name", "name"):
        if key in output:
            val = output[key]
            if val is not None and not isinstance(val, str):
                result.add_error(key, f"Expected str, got {type(val).__name__}")

    # ── years_experience / experience_years ───────────────────────────────
    for key in ("years_experience", "experience_years"):
        if key in output and output[key] is not None:
            val = output[key]
            if not isinstance(val, (int, float)):
                result.add_error(key, f"Expected numeric, got {type(val).__name__}: {val!r}")
            elif val < 0 or val > 70:
                result.add_warning(key, f"Unusual years_experience value: {val}")

    # ── overall_confidence ────────────────────────────────────────────────
    if "overall_confidence" in output and output["overall_confidence"] is not None:
        val = output["overall_confidence"]
        if not isinstance(val, (int, float)):
            result.add_error("overall_confidence", f"Expected float, got {type(val).__name__}")
        elif not (0.0 <= float(val) <= 1.0):
            result.add_error("overall_confidence", f"Must be in [0, 1], got {val}")

    # ── location ─────────────────────────────────────────────────────────
    if "location" in output and output["location"] is not None:
        loc = output["location"]
        if not isinstance(loc, dict):
            result.add_error("location", f"Expected dict, got {type(loc).__name__}")
        else:
            cc = loc.get("country_code")
            if cc is not None and not re.match(r"^[A-Z]{2}$", str(cc)):
                result.add_warning("location", f"country_code '{cc}' is not ISO Alpha-2")

    # ── skills ────────────────────────────────────────────────────────────
    if "skills" in output and output["skills"] is not None:
        skills = output["skills"]
        if not isinstance(skills, list):
            result.add_error("skills", f"Expected list, got {type(skills).__name__}")
        else:
            for i, skill in enumerate(skills):
                if isinstance(skill, dict) and not skill.get("name"):
                    result.add_warning("skills", f"Skill at index {i} has no 'name'")

    # ── confidence block ──────────────────────────────────────────────────
    if "_confidence" in output:
        _validate_confidence_block(output["_confidence"], result)

    log.debug(
        "Validation complete: %s (%d errors, %d warnings)",
        result.summary(), result.error_count, result.warning_count,
    )
    return result


def validate_candidate_id(candidate_id: str | None) -> list[ValidationError]:
    """Standalone validator for the candidate_id field."""
    if not candidate_id:
        return [ValidationError("candidate_id", "candidate_id is missing or empty")]
    if not _UUID_RE.match(candidate_id):
        return [ValidationError("candidate_id", f"Not a valid UUID: '{candidate_id}'", "warning")]
    return []


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _validate_candidate_id(output: dict, result: ValidationResult) -> None:
    cid = output.get("candidate_id")
    if not cid:
        result.add_error("candidate_id", "candidate_id is required but missing or empty")
        return
    if not isinstance(cid, str):
        result.add_error("candidate_id", f"candidate_id must be a string, got {type(cid).__name__}")
        return
    if not _UUID_RE.match(cid):
        result.add_warning("candidate_id", f"candidate_id '{cid}' does not match UUID format")


def _validate_list_of_strings(
    output: dict, key: str, result: ValidationResult
) -> None:
    val = output.get(key)
    if val is None:
        return
    if not isinstance(val, list):
        result.add_error(key, f"Expected list, got {type(val).__name__}")
        return
    for i, item in enumerate(val):
        if not isinstance(item, str):
            result.add_error(key, f"Item at index {i} is not a string: {item!r}")


def _validate_confidence_block(block: Any, result: ValidationResult) -> None:
    if not isinstance(block, dict):
        result.add_error("_confidence", f"Expected dict, got {type(block).__name__}")
        return
    for field_key, score_obj in block.items():
        if isinstance(score_obj, dict):
            score = score_obj.get("score")
            if score is not None and not (0.0 <= float(score) <= 1.0):
                result.add_error(
                    f"_confidence.{field_key}",
                    f"Confidence score must be in [0, 1], got {score}",
                )
