"""Projection sub-package — runtime-configurable output shaping."""

from .config import ProjectionConfig, FieldConfig
from .engine import ProjectionEngine

__all__ = ["ProjectionConfig", "FieldConfig", "ProjectionEngine"]
