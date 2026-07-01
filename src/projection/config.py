"""
ProjectionConfig — Pydantic model for the runtime output configuration.

The config is loaded from a user-supplied ``config.json`` file at pipeline
start-up and remains immutable for the lifetime of a run.

Schema (config.json):
    {
      "fields": {
        "full_name":        {"include": true,  "rename": "name"},
        "years_experience": {"include": true,  "rename": "experience_years"},
        "experience":       {"include": true,  "rename": "work_history"}
      },
      "include_confidence":  true,
      "include_provenance":  false,
      "missing_value_policy": "null"   // "null" | "omit" | "error"
    }

If a field is not listed in ``fields``, it defaults to included with no rename.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Every known canonical output field, in display order.
_CANONICAL_FIELDS: list[str] = [
    "candidate_id",
    "full_name",
    "emails",
    "phones",
    "location",
    "links",
    "headline",
    "years_experience",
    "skills",
    "experience",
    "education",
    "overall_confidence",
    "warnings",
    "pipeline_version",
    "created_at",
]


class FieldConfig(BaseModel):
    """Per-field projection settings.

    Attributes:
        include: Whether to include this field in the output.
                 Defaults to ``True``.
        rename:  Output key name. If ``None``, the canonical name is used.
    """

    model_config = ConfigDict(frozen=True)

    include: bool = True
    rename: str | None = None

    @property
    def output_key(self) -> str | None:
        """Return the rename value, or None (caller uses canonical name)."""
        return self.rename


class ProjectionConfig(BaseModel):
    """Runtime output shaping configuration.

    Attributes:
        fields:               Per-field overrides. Missing fields default to
                              ``FieldConfig(include=True, rename=None)``.
        include_confidence:   Append ``_confidence`` sub-object to each field.
        include_provenance:   Append ``_provenance`` sub-object to each field.
        missing_value_policy: What to do when an included field's value is
                              ``None`` or an empty list:
                              ``"null"``  — emit the key with ``null`` value
                              ``"omit"``  — omit the key entirely
                              ``"error"`` — raise ValueError (caught by validator)
    """

    model_config = ConfigDict(frozen=True)

    fields: dict[str, FieldConfig] = Field(default_factory=dict)
    include_confidence: bool = True
    include_provenance: bool = False
    missing_value_policy: Literal["null", "omit", "error"] = "null"

    # ── Class-level factory methods ────────────────────────────────────────

    @classmethod
    def default(cls) -> "ProjectionConfig":
        """Return a config that includes all fields with no renaming."""
        return cls()

    @classmethod
    def from_file(cls, path: Path | str) -> "ProjectionConfig":
        """Load a ProjectionConfig from a JSON file.

        Args:
            path: Path to the config JSON file.

        Returns:
            Validated :class:`ProjectionConfig` instance.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the file contains invalid JSON or fails Pydantic
                        validation.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file '{p}': {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectionConfig":
        """Build a ProjectionConfig from a plain dict.

        Handles the ``_comment`` key that may appear in hand-edited configs.
        """
        clean = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls.model_validate(clean)

    # ── Convenience accessors ──────────────────────────────────────────────

    def get_field_config(self, canonical_name: str) -> FieldConfig:
        """Return the FieldConfig for *canonical_name*, defaulting to include."""
        return self.fields.get(canonical_name, FieldConfig())

    def is_included(self, canonical_name: str) -> bool:
        """Return True if *canonical_name* should appear in the output."""
        return self.get_field_config(canonical_name).include

    def output_key_for(self, canonical_name: str) -> str:
        """Return the output key for *canonical_name* (renamed or original)."""
        cfg = self.get_field_config(canonical_name)
        return cfg.rename or canonical_name
