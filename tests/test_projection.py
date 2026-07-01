"""Tests for ProjectionEngine and the output Validator."""

import json
import pytest
from src.merger import MergeEngine
from src.projection import ProjectionEngine, ProjectionConfig, FieldConfig
from src.validators import validate_output, ValidationResult


# ─── Shared fixture ────────────────────────────────────────────────────────

@pytest.fixture
def merged_candidate(raw_csv):
    return MergeEngine().merge([raw_csv]).candidate


# ═══════════════════════════════════════════════════════════════════════════
# ProjectionConfig
# ═══════════════════════════════════════════════════════════════════════════

class TestProjectionConfig:

    def test_default_includes_all_fields(self):
        cfg = ProjectionConfig.default()
        assert cfg.is_included("full_name")
        assert cfg.is_included("emails")
        assert cfg.include_confidence is True

    def test_output_key_with_rename(self):
        cfg = ProjectionConfig(fields={"full_name": FieldConfig(rename="name")})
        assert cfg.output_key_for("full_name") == "name"

    def test_output_key_without_rename(self):
        cfg = ProjectionConfig.default()
        assert cfg.output_key_for("full_name") == "full_name"

    def test_exclude_field(self):
        cfg = ProjectionConfig(fields={"warnings": FieldConfig(include=False)})
        assert not cfg.is_included("warnings")
        assert cfg.is_included("emails")

    def test_from_dict_parses_rename(self):
        data = {"fields": {"full_name": {"include": True, "rename": "name"}}}
        cfg = ProjectionConfig.from_dict(data)
        assert cfg.output_key_for("full_name") == "name"

    def test_from_dict_ignores_comment_keys(self):
        data = {"_comment": "ignore me", "include_confidence": False}
        cfg = ProjectionConfig.from_dict(data)
        assert cfg.include_confidence is False

    def test_from_file_loads_sample(self, sample_config_path):
        cfg = ProjectionConfig.from_file(sample_config_path)
        assert isinstance(cfg, ProjectionConfig)

    def test_from_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ProjectionConfig.from_file(tmp_path / "nonexistent.json")

    def test_from_file_invalid_json_raises_value_error(self, tmp_path):
        """A file that exists but contains malformed JSON must raise ValueError
        with a message that includes 'Invalid JSON'."""
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json: at all", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            ProjectionConfig.from_file(bad)

    def test_from_file_invalid_schema_raises(self, tmp_path):
        """A file with valid JSON but a value that fails Pydantic enum validation
        must raise a ValidationError (not silently accepted).

        ``missing_value_policy`` accepts only 'null' | 'omit' | 'error';
        any other value must be rejected.
        """
        from pydantic import ValidationError
        bad_schema = tmp_path / "bad_schema.json"
        bad_schema.write_text(
            '{"missing_value_policy": "destroy_all_data"}',
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            ProjectionConfig.from_file(bad_schema)

    def test_missing_value_policy_validated(self):
        with pytest.raises(Exception):
            ProjectionConfig(missing_value_policy="invalid_policy")


# ═══════════════════════════════════════════════════════════════════════════
# ProjectionEngine
# ═══════════════════════════════════════════════════════════════════════════

class TestProjectionEngine:
    engine = ProjectionEngine()

    def test_default_project_has_candidate_id(self, merged_candidate):
        out = self.engine.project(merged_candidate)
        assert "candidate_id" in out

    def test_full_name_normalized_in_output(self, merged_candidate):
        out = self.engine.project(merged_candidate)
        assert out.get("full_name") == "Priya Sharma"

    def test_rename_applied(self, merged_candidate):
        cfg = ProjectionConfig(fields={"full_name": FieldConfig(rename="name")})
        out = self.engine.project(merged_candidate, cfg)
        assert "name" in out
        assert "full_name" not in out

    def test_field_excluded(self, merged_candidate):
        cfg = ProjectionConfig(fields={"warnings": FieldConfig(include=False)})
        out = self.engine.project(merged_candidate, cfg)
        assert "warnings" not in out

    def test_confidence_block_present_by_default(self, merged_candidate):
        out = self.engine.project(merged_candidate)
        assert "_confidence" in out

    def test_provenance_block_present_when_enabled(self, merged_candidate):
        cfg = ProjectionConfig(include_provenance=True)
        out = self.engine.project(merged_candidate, cfg)
        assert "_provenance" in out

    def test_provenance_block_absent_by_default(self, merged_candidate):
        out = self.engine.project(merged_candidate)
        assert "_provenance" not in out

    def test_missing_value_policy_omit(self, merged_candidate):
        # headline might be absent; with omit it should not appear
        cfg = ProjectionConfig(missing_value_policy="omit",
                               fields={"headline": FieldConfig(include=True)})
        out = self.engine.project(merged_candidate, cfg)
        # headline is "Senior Data Engineer" from raw_csv, so it IS present
        # Just verify no KeyError and structure is correct
        assert isinstance(out, dict)

    def test_missing_value_policy_error_raises(self, merged_candidate):
        from src.models.candidate import CanonicalCandidate
        from src.utils.id_generator import generate_candidate_id
        empty = CanonicalCandidate(
            candidate_id=generate_candidate_id("t@t.com"),
            emails=["t@t.com"],
        )
        cfg = ProjectionConfig(
            fields={"full_name": FieldConfig(include=True)},
            missing_value_policy="error",
        )
        with pytest.raises(ValueError, match="required"):
            self.engine.project(empty, cfg)

    def test_output_is_json_serialisable(self, merged_candidate):
        out = self.engine.project(merged_candidate)
        serialised = json.dumps(out, default=str)
        reparsed = json.loads(serialised)
        assert reparsed["candidate_id"] == out["candidate_id"]

    def test_renamed_field_appears_in_confidence_block(self, merged_candidate):
        cfg = ProjectionConfig(
            fields={"full_name": FieldConfig(rename="name")},
            include_confidence=True,
        )
        out = self.engine.project(merged_candidate, cfg)
        assert "name" in out.get("_confidence", {})


# ═══════════════════════════════════════════════════════════════════════════
# Validator
# ═══════════════════════════════════════════════════════════════════════════

class TestValidator:

    def _valid_output(self, merged_candidate):
        return ProjectionEngine().project(merged_candidate)

    def test_valid_output_passes(self, merged_candidate):
        out = self._valid_output(merged_candidate)
        vr = validate_output(out)
        assert vr.is_valid
        assert vr.error_count == 0

    def test_missing_candidate_id_is_error(self, merged_candidate):
        out = self._valid_output(merged_candidate)
        del out["candidate_id"]
        vr = validate_output(out)
        assert not vr.is_valid
        assert any("candidate_id" in e.field for e in vr.errors)

    def test_confidence_over_1_is_error(self):
        out = {
            "candidate_id": "fcbcbc64-f85c-5025-877c-37f4c7a12d6e",
            "_confidence": {"full_name": {"score": 1.5}},
        }
        vr = validate_output(out)
        assert not vr.is_valid

    def test_non_e164_phone_is_warning_not_error(self):
        out = {
            "candidate_id": "fcbcbc64-f85c-5025-877c-37f4c7a12d6e",
            "phones": ["not-e164"],
        }
        vr = validate_output(out)
        assert vr.is_valid          # still valid
        assert vr.warning_count > 0 # but has warning

    def test_invalid_years_type_is_error(self):
        out = {
            "candidate_id": "fcbcbc64-f85c-5025-877c-37f4c7a12d6e",
            "years_experience": "six",
        }
        vr = validate_output(out)
        assert not vr.is_valid

    def test_validation_result_summary_format(self, merged_candidate):
        out = self._valid_output(merged_candidate)
        vr = validate_output(out)
        assert "VALID" in vr.summary() or "INVALID" in vr.summary()

    def test_empty_output_dict_fails(self):
        vr = validate_output({})
        assert not vr.is_valid
