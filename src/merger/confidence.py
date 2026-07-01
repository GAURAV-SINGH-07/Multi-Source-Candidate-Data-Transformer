"""
ConfidenceEngine — computes per-field and overall confidence scores.

Formula (per field):
    score = source_reliability × normalization_factor × corroboration_bonus

Where:
    source_reliability   = SOURCE_RELIABILITY[winning_source]  (0.0 – 1.0)
    normalization_factor = NormalizationResult.factor          (0.0 – 1.0)
    corroboration_bonus  = 1.0 + (agreeing_sources - 1) × per_source_bonus
                           capped at settings.corroboration_bonus_cap

Overall confidence is a weighted average across all scored fields. Fields
with higher semantic importance (name, email) are weighted more heavily than
supplementary fields (links, headline).
"""

from src.config.settings import settings
from src.config.source_priority import get_reliability
from src.models.field_confidence import FieldConfidence
from src.models.source_type import SourceType
from src.normalizers.result import NormalizationResult
from src.utils.logging_config import get_logger

log = get_logger(__name__)

# Importance weights for overall confidence calculation.
# Fields absent from this map use weight 1.0.
_FIELD_WEIGHTS: dict[str, float] = {
    "full_name":        1.5,
    "emails":           1.5,
    "phones":           1.2,
    "location":         1.0,
    "headline":         0.8,
    "years_experience": 1.0,
    "skills":           1.2,
    "experience":       1.2,
    "education":        1.0,
    "links":            0.8,
}


class ConfidenceEngine:
    """Computes explainable per-field and overall confidence scores.

    Args:
        per_source_bonus: Confidence bonus added per additional agreeing source.
                          Defaults to ``settings.corroboration_bonus_per_source``.
        bonus_cap:        Maximum corroboration multiplier.
                          Defaults to ``settings.corroboration_bonus_cap``.
    """

    def __init__(
        self,
        per_source_bonus: float | None = None,
        bonus_cap: float | None = None,
    ) -> None:
        self._per_source_bonus = per_source_bonus or settings.corroboration_bonus_per_source
        self._bonus_cap = bonus_cap or settings.corroboration_bonus_cap

    def compute(
        self,
        field: str,
        winning_source: SourceType,
        norm_result: NormalizationResult,
        agreed_sources: int,
    ) -> FieldConfidence:
        """Compute :class:`FieldConfidence` for one canonical field.

        Args:
            field:          Canonical field name (for explanation labelling).
            winning_source: The source whose value was chosen.
            norm_result:    The NormalizationResult from the winning value.
            agreed_sources: Number of sources that agreed on the winning value
                            (including the winner itself). Minimum 1.

        Returns:
            A frozen :class:`FieldConfidence` with auto-computed ``score``.
        """
        reliability = get_reliability(winning_source)
        norm_factor = norm_result.factor
        corroboration = self._corroboration_bonus(agreed_sources)

        explanation = self._build_explanation(
            field, winning_source, reliability, norm_factor,
            corroboration, agreed_sources, norm_result.method,
        )

        return FieldConfidence(
            source_reliability=reliability,
            normalization_factor=norm_factor,
            corroboration_bonus=corroboration,
            explanation=explanation,
        )

    def compute_overall(
        self,
        field_confidences: dict[str, FieldConfidence],
    ) -> float:
        """Compute a weighted-average overall confidence score.

        Fields with higher semantic importance receive more weight.
        Fields with a score of 0.0 are excluded from the average (they
        represent absent data, not bad data).

        Args:
            field_confidences: Per-field FieldConfidence objects.

        Returns:
            Weighted average score rounded to 4 decimal places.
        """
        if not field_confidences:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for field, fc in field_confidences.items():
            if fc.score <= 0.0:
                continue  # Field absent — don't drag down the average
            weight = _FIELD_WEIGHTS.get(field, 1.0)
            weighted_sum += fc.score * weight
            total_weight += weight

        if total_weight == 0.0:
            return 0.0

        return round(weighted_sum / total_weight, 4)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _corroboration_bonus(self, agreed_sources: int) -> float:
        """Compute corroboration multiplier from *agreed_sources* count."""
        bonus = 1.0 + max(0, agreed_sources - 1) * self._per_source_bonus
        return round(min(bonus, self._bonus_cap), 4)

    @staticmethod
    def _build_explanation(
        field: str,
        source: SourceType,
        reliability: float,
        norm_factor: float,
        corroboration: float,
        agreed_sources: int,
        norm_method: str,
    ) -> str:
        """Build a human-readable score breakdown string."""
        raw_score = round(min(reliability * norm_factor * corroboration, 1.0), 4)
        corroboration_note = (
            f"{agreed_sources} source(s) agree → bonus={corroboration:.2f}"
            if agreed_sources > 1
            else "single source, no corroboration bonus"
        )
        return (
            f"field='{field}' | score={raw_score} = "
            f"reliability({reliability:.2f}) × "
            f"norm_factor({norm_factor:.2f}) × "
            f"corroboration({corroboration:.2f}) | "
            f"source='{source.value}' | method='{norm_method}' | "
            f"{corroboration_note}"
        )
