"""Merger sub-package — deterministic merge and conflict resolution."""

from .conflict import ConflictDecision, ConflictResolver, ValueCandidate
from .confidence import ConfidenceEngine
from .engine import MergeEngine, MergeResult

__all__ = [
    "ConflictDecision",
    "ConflictResolver",
    "ValueCandidate",
    "ConfidenceEngine",
    "MergeEngine",
    "MergeResult",
]
