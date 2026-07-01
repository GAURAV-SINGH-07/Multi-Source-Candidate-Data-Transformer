"""
Application-wide settings.

All runtime configuration lives here as typed class attributes. Values
can be overridden via environment variables using the ``EIGHTFOLD_``
prefix if needed, but sensible defaults handle the common case.

Pydantic's BaseSettings is intentionally NOT used here to avoid the
optional ``python-dotenv`` dependency — these are build-time constants,
not secrets.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration.

    Attributes:
        project_root:       Absolute path to the project root directory.
        output_dir:         Directory where pipeline outputs are written.
        default_country:    Fallback country code for phone normalization
                            when no country hint is available in the source.
        pdf_max_pages:      Maximum pages to read from a resume PDF.
                            Avoids processing accidentally large files.
        skill_fuzzy_threshold: Minimum rapidfuzz similarity score (0–100)
                            for a skill string to be matched to a canonical
                            name. Values below this are kept as-is and flagged.
        corroboration_bonus_per_source: Added to the corroboration multiplier
                            for each additional source that agrees on a value.
        corroboration_bonus_cap: Maximum corroboration multiplier.
        pipeline_version:   Semver string embedded in every output.
    """

    project_root: Path = field(default_factory=lambda: Path(__file__).parents[2])
    output_dir: Path = field(default_factory=lambda: Path(__file__).parents[2] / "outputs")
    default_country: str = "IN"  # Used as fallback for phone parsing
    pdf_max_pages: int = 20
    skill_fuzzy_threshold: float = 82.0
    corroboration_bonus_per_source: float = 0.05
    corroboration_bonus_cap: float = 1.2
    pipeline_version: str = "1.0.0"


# Singleton instance — import this everywhere instead of instantiating directly
settings = Settings()
