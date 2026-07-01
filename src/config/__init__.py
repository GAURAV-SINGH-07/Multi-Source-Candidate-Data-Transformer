"""Config sub-package — static configuration and skill dictionaries."""

from .settings import Settings, settings
from .source_priority import (
    SOURCE_PRIORITY,
    SOURCE_RELIABILITY,
    get_priority,
    get_reliability,
)
from .skill_synonyms import SKILL_SYNONYMS

__all__ = [
    "Settings",
    "settings",
    "SOURCE_PRIORITY",
    "SOURCE_RELIABILITY",
    "get_priority",
    "get_reliability",
    "SKILL_SYNONYMS",
]
