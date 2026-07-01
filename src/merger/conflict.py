"""
ConflictResolver — deterministic conflict resolution for merged field values.

When two sources provide different values for the same field, the resolver
picks the winner based on source priority (lower number = higher authority)
and records a structured ConflictDecision for the decision log and
explainability output.

All decisions are deterministic: given the same inputs in any order, the
same value will always win because candidates are sorted by priority before
comparison.
"""

from dataclasses import dataclass, field
from typing import Any

from src.models.source_type import SourceType
from src.config.source_priority import get_priority
from src.normalizers.result import NormalizationResult
from src.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ValueCandidate:
    """A normalized field value from one data source.

    Attributes:
        value:       The normalized value (post-normalization).
        source:      Which source produced this value.
        norm_result: The full NormalizationResult (carries factor + method).
        priority:    Source priority for deterministic ordering.
    """

    value: Any
    source: SourceType
    norm_result: NormalizationResult
    priority: int  # lower = higher authority


@dataclass(frozen=True)
class ConflictDecision:
    """Record of a conflict resolution event for one field.

    Attributes:
        field:         Canonical field name.
        winner:        The ValueCandidate that was chosen.
        losers:        All other candidates that were not chosen.
        had_conflict:  True if there were genuinely different values.
        agreed_sources: Number of sources that provided the winning value.
        reason:        Human-readable explanation of the decision.
    """

    field: str
    winner: ValueCandidate
    losers: list[ValueCandidate]
    had_conflict: bool
    agreed_sources: int
    reason: str


class ConflictResolver:
    """Resolves multi-source field conflicts using deterministic priority rules.

    Algorithm:
        1. Filter out candidates with None values.
        2. Sort by source priority (ascending = highest authority first).
        3. Group by normalized string representation to detect agreement.
        4. If all non-None values agree → unanimous, highest-priority source wins.
        5. If values differ → conflict, highest-priority source wins.
        6. Always produce a :class:`ConflictDecision` for audit purposes.
    """

    def resolve(
        self,
        field: str,
        candidates: list[ValueCandidate],
    ) -> ConflictDecision | None:
        """Resolve the winning value for *field* from *candidates*.

        Args:
            field:      Canonical field name (e.g., ``"full_name"``).
            candidates: All normalized value candidates for this field,
                        one per source. May contain None values (skipped).

        Returns:
            A :class:`ConflictDecision`, or ``None`` if no candidate has a
            non-None value (field is absent in all sources).
        """
        valid = [c for c in candidates if c.value is not None]
        if not valid:
            return None

        # Deterministic sort: primary = priority (asc), secondary = source name
        sorted_candidates = sorted(valid, key=lambda c: (c.priority, c.source.value))
        winner = sorted_candidates[0]
        losers = sorted_candidates[1:]

        # Check for conflict: do all non-None values represent the same thing?
        unique_values = {self._normalize_for_comparison(c.value) for c in valid}
        had_conflict = len(unique_values) > 1

        # Count how many sources agree with the winner
        winner_repr = self._normalize_for_comparison(winner.value)
        agreed_sources = sum(
            1 for c in valid
            if self._normalize_for_comparison(c.value) == winner_repr
        )

        reason = self._build_reason(field, winner, losers, had_conflict, agreed_sources)

        if had_conflict:
            log.info(
                "Conflict on field '%s': %d sources disagree. "
                "Chose '%s' from %s (priority=%d).",
                field, len(unique_values), winner.value, winner.source.value, winner.priority,
            )

        return ConflictDecision(
            field=field,
            winner=winner,
            losers=losers,
            had_conflict=had_conflict,
            agreed_sources=agreed_sources,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_for_comparison(value: Any) -> str:
        """Produce a canonical string for value comparison.

        Lowercases strings, stringifies numbers. This ensures that
        "Python" and "python" are treated as the same value when
        checking for cross-source agreement.
        """
        if isinstance(value, str):
            return value.lower().strip()
        return str(value).strip()

    @staticmethod
    def _build_reason(
        field: str,
        winner: ValueCandidate,
        losers: list[ValueCandidate],
        had_conflict: bool,
        agreed_sources: int,
    ) -> str:
        """Build a human-readable explanation of the resolution decision."""
        all_sources = [winner] + losers
        source_names = [c.source.value for c in all_sources]

        if not had_conflict:
            if len(all_sources) == 1:
                return (
                    f"Single source '{winner.source.value}' provided this value. "
                    f"No conflict to resolve."
                )
            return (
                f"All {len(all_sources)} sources agree on this value "
                f"({', '.join(source_names)}). "
                f"Chose from highest-priority source '{winner.source.value}'."
            )

        loser_summary = "; ".join(
            f"'{c.source.value}' → '{c.value}'" for c in losers
        )
        return (
            f"Conflict detected across {len(all_sources)} sources. "
            f"Chose '{winner.value}' from '{winner.source.value}' "
            f"(priority={winner.priority}). "
            f"Discarded: {loser_summary}. "
            f"Priority order is deterministic per SOURCE_PRIORITY config."
        )
