"""
FieldConfidence — explainable, decomposed confidence score for one field.

The score is the product of three independent factors, each bounded [0, 1]:

    score = source_reliability × normalization_factor × corroboration_bonus

This decomposition keeps the formula auditable: you can read back exactly
why a field scored 0.72 rather than 0.9, without magic numbers.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldConfidence(BaseModel):
    """Decomposed confidence score for a single canonical field.

    Attributes:
        source_reliability:    Reliability weight of the highest-priority
                               source that contributed this value (0 – 1.0).
        normalization_factor:  1.0 if normalization succeeded cleanly,
                               <1.0 if heuristics or fallbacks were used,
                               0.5 if the raw value was kept as-is.
        corroboration_bonus:   Multiplier applied when multiple sources
                               agree. Starts at 1.0 and increases by 0.05
                               per additional agreeing source, capped at 1.2.
        score:                 Final computed score. Auto-computed by the
                               validator; do not set manually.
        explanation:           Human-readable breakdown of how the score
                               was derived, suitable for the explanation tab.
    """

    model_config = ConfigDict(frozen=True)

    source_reliability: float = Field(..., ge=0.0, le=1.0)
    normalization_factor: float = Field(..., ge=0.0, le=1.0)
    corroboration_bonus: float = Field(..., ge=1.0, le=1.5)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str = Field(..., description="Human-readable score breakdown")

    @model_validator(mode="after")
    def compute_score(self) -> "FieldConfidence":
        """Compute and cap the final score after all factors are set."""
        computed = round(
            min(
                self.source_reliability
                * self.normalization_factor
                * self.corroboration_bonus,
                1.0,
            ),
            4,
        )
        # Pydantic v2: must use object.__setattr__ because the model is frozen
        object.__setattr__(self, "score", computed)
        return self
