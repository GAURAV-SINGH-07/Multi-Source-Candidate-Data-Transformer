"""
Skill normalizer — maps raw skill strings to canonical names.

Uses a two-stage lookup:
    1. Exact match against the synonym dictionary (O(1) hash lookup).
       Handles case-insensitive matches and known abbreviations.
    2. Fuzzy match via ``rapidfuzz.fuzz.WRatio`` against all known aliases.
       Applied only when exact lookup fails; controlled by ``threshold``.

The ``SkillNormalizer`` class is initialized once with the synonym dictionary
and reused across all normalization calls — building the reverse lookup on
every call would be wasteful.

The module-level ``normalize_skill`` function uses a default singleton
instance backed by ``SKILL_SYNONYMS`` from ``src.config``.
"""

from dataclasses import dataclass, field
from rapidfuzz import process as fuzz_process, fuzz

from src.config.skill_synonyms import SKILL_SYNONYMS
from src.config.settings import settings
from .result import NormalizationResult


@dataclass
class SkillNormalizer:
    """Stateful normalizer built from a synonym dictionary.

    Args:
        synonyms:  Dict mapping canonical name → list of known aliases.
        threshold: Minimum rapidfuzz score (0–100) for fuzzy matching.
                   Strings below this score are kept as-is.

    Attributes:
        _exact:   Flat dict of ``{lowercase_alias: canonical_name}``.
        _choices: List of all lowercase aliases (used by rapidfuzz).
    """

    synonyms: dict[str, list[str]] = field(default_factory=lambda: SKILL_SYNONYMS)
    threshold: float = field(default_factory=lambda: settings.skill_fuzzy_threshold)

    # Internal state (populated in __post_init__)
    _exact: dict[str, str] = field(init=False, default_factory=dict)
    _choices: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        """Build the reverse lookup from the synonym dictionary."""
        for canonical, aliases in self.synonyms.items():
            # The canonical name itself is an alias for an exact match
            self._exact[canonical.lower()] = canonical
            for alias in aliases:
                self._exact[alias.lower()] = canonical
        self._choices = list(self._exact.keys())

    def normalize(self, raw: str) -> NormalizationResult:
        """Normalize a single skill string.

        Args:
            raw: Raw skill string (any case, any format).

        Returns:
            :class:`NormalizationResult`:
                - ``factor=1.00`` for exact synonym match
                - ``factor=0.85–0.95`` for fuzzy match (scales with score)
                - ``factor=0.60`` for unknown skill (kept as-is, title-cased)
        """
        if not raw or not raw.strip():
            return NormalizationResult(
                value=None, success=False, factor=0.0,
                method="empty_input", original=raw, warning="Empty skill string",
            )

        stripped = raw.strip()
        lower = stripped.lower()

        # Stage 1: exact synonym lookup
        if lower in self._exact:
            canonical = self._exact[lower]
            return NormalizationResult(
                value=canonical,
                success=True,
                factor=1.0,
                method="exact_synonym_match",
                original=raw,
                warning=None,
            )

        # Stage 2: fuzzy match
        result = fuzz_process.extractOne(
            lower,
            self._choices,
            scorer=fuzz.WRatio,
            score_cutoff=self.threshold,
        )
        if result:
            match_alias, score, _ = result
            canonical = self._exact[match_alias]
            # Scale factor: threshold maps to 0.85, 100 maps to 0.95
            factor = round(
                0.85 + (score - self.threshold) / (100.0 - self.threshold) * 0.10,
                3,
            )
            return NormalizationResult(
                value=canonical,
                success=True,
                factor=min(factor, 0.95),
                method=f"fuzzy_match(score={score:.1f}, alias='{match_alias}')",
                original=raw,
                warning=None,
            )

        # Stage 3: unknown skill — keep title-cased original
        title_cased = stripped.title()
        return NormalizationResult(
            value=title_cased,
            success=False,
            factor=0.60,
            method="unknown_skill_kept_as_is",
            original=raw,
            warning=f"Skill '{stripped}' not in synonym dictionary; kept as '{title_cased}'",
        )

    def normalize_list(self, raw_skills: list[str]) -> list[NormalizationResult]:
        """Normalize a list of skill strings, preserving order."""
        return [self.normalize(skill) for skill in raw_skills]

    def canonical_names(self, raw_skills: list[str]) -> list[str]:
        """Return just the canonical name strings for a list of raw skills.

        Deduplicates by canonical name (preserves first occurrence order).
        """
        seen: set[str] = set()
        result: list[str] = []
        for res in self.normalize_list(raw_skills):
            if res.value and res.value not in seen:
                seen.add(res.value)
                result.append(res.value)
        return result


# ---------------------------------------------------------------------------
# Module-level singleton and convenience function
# ---------------------------------------------------------------------------

_default_normalizer: SkillNormalizer | None = None


def _get_default() -> SkillNormalizer:
    """Lazily initialize the default SkillNormalizer singleton."""
    global _default_normalizer
    if _default_normalizer is None:
        _default_normalizer = SkillNormalizer()
    return _default_normalizer


def normalize_skill(raw: str) -> NormalizationResult:
    """Normalize a single skill using the default synonym dictionary.

    This is the module-level convenience function. For bulk normalization
    or custom synonym sets, instantiate :class:`SkillNormalizer` directly.

    Args:
        raw: Raw skill string.

    Returns:
        :class:`NormalizationResult`.
    """
    return _get_default().normalize(raw)
