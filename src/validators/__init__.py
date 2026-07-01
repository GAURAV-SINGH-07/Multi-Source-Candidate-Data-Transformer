"""Validators sub-package — schema validation for projected output."""

from .output import ValidationResult, ValidationError, validate_output

__all__ = ["ValidationResult", "ValidationError", "validate_output"]
