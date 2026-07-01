"""
NormalizationResult — the uniform return type for all normalizers.

Every normalizer returns this dataclass rather than a bare value, giving the
Confidence Engine everything it needs to compute a field score without knowing
which normalizer ran or how.

Fields:
    value:    The normalized value (or original if normalization failed).
    success:  True if the normalizer produced a clean canonical form.
    factor:   Normalization quality score, 0.0–1.0. Feeds into FieldConfidence.
              Rules of thumb:
                  1.00 — perfect canonical form via exact/structured parsing
                  0.85 — normalized via fallback region/assumption
                  0.70 — year-only date, partial phone, etc.
                  0.50 — raw value kept as-is (unrecognized format)
                  0.30 — known-bad value kept to avoid data loss
    method:   Short description of the normalization path taken.
    original: The raw input value, preserved for provenance.
    warning:  Non-fatal issue message; None if normalization was clean.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizationResult:
    """Uniform return type for all field normalizers."""

    value: Any
    success: bool
    factor: float          # 0.0 – 1.0
    method: str
    original: Any
    warning: str | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.factor <= 1.0):
            raise ValueError(f"NormalizationResult.factor must be in [0, 1], got {self.factor}")
