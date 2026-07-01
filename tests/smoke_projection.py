"""Smoke tests for Projection Engine (Phase 7) and Validator (Phase 8)."""

import sys
import json
sys.path.insert(0, "d:/EightFold")

from src.models.raw import RawCandidateData
from src.models.source_type import SourceType
from src.merger import MergeEngine
from src.projection import ProjectionEngine, ProjectionConfig, FieldConfig
from src.validators import validate_output, ValidationResult

failures = []

def check(label, cond, got=""):
    if not cond:
        failures.append(f"FAIL [{label}] got={got!r}")
    else:
        print(f"[PASS] {label}")

# Build a candidate to project
engine = MergeEngine()
raw = RawCandidateData(
    source=SourceType.RECRUITER_CSV,
    full_name="priya sharma",
    emails=["priya.sharma@email.com"],
    phones=["+91-98765-43210"],
    location="Bangalore, India",
    links=["https://linkedin.com/in/priyasharma"],
    headline="Senior Data Engineer",
    years_experience=6.0,
    skills=["Python", "apache spark", "reactjs"],
)
merge_result = engine.merge([raw])
candidate = merge_result.candidate

proj = ProjectionEngine()

# ── Test 1: Default config — all fields included ──────────────────────────
cfg_default = ProjectionConfig.default()
out = proj.project(candidate, cfg_default)

check("Default: candidate_id present", "candidate_id" in out, list(out))
check("Default: full_name present", "full_name" in out, list(out))
check("Default: full_name normalized", out["full_name"] == "Priya Sharma", out.get("full_name"))
check("Default: phones present", "phones" in out, list(out))
check("Default: _confidence included", "_confidence" in out, list(out))
check("Default: _provenance NOT included (default)", "_provenance" not in out, list(out))

# ── Test 2: Field renaming ────────────────────────────────────────────────
cfg_rename = ProjectionConfig(
    fields={
        "full_name":        FieldConfig(include=True, rename="name"),
        "years_experience": FieldConfig(include=True, rename="experience_years"),
        "experience":       FieldConfig(include=True, rename="work_history"),
    }
)
out2 = proj.project(candidate, cfg_rename)

check("Rename: 'name' key present", "name" in out2, list(out2))
check("Rename: 'full_name' key absent", "full_name" not in out2, list(out2))
check("Rename: 'experience_years' key present", "experience_years" in out2, list(out2))
check("Rename: 'work_history' key present", "work_history" in out2, list(out2))

# ── Test 3: Field exclusion ───────────────────────────────────────────────
cfg_exclude = ProjectionConfig(
    fields={
        "provenance":    FieldConfig(include=False),
        "warnings":      FieldConfig(include=False),
        "pipeline_version": FieldConfig(include=False),
        "created_at":    FieldConfig(include=False),
    }
)
out3 = proj.project(candidate, cfg_exclude)

check("Exclude: warnings omitted", "warnings" not in out3, list(out3))
check("Exclude: pipeline_version omitted", "pipeline_version" not in out3, list(out3))
check("Exclude: emails still present", "emails" in out3, list(out3))

# ── Test 4: missing_value_policy="omit" ──────────────────────────────────
cfg_omit = ProjectionConfig(missing_value_policy="omit")
# Remove a field to make it absent — we'll check headline (might be None)
out4 = proj.project(candidate, cfg_omit)
# headline value is "Senior Data Engineer" — should be present
check("Omit: non-null headline still present", "headline" in out4, list(out4))

# ── Test 5: missing_value_policy="null" ──────────────────────────────────
cfg_null = ProjectionConfig(missing_value_policy="null")
out5 = proj.project(candidate, cfg_null)
check("Null policy: output is dict", isinstance(out5, dict), type(out5))

# ── Test 6: missing_value_policy="error" ─────────────────────────────────
from src.models.candidate import CanonicalCandidate
from src.utils.id_generator import generate_candidate_id
# Build a minimal candidate with no name
minimal = CanonicalCandidate(
    candidate_id=generate_candidate_id("test@test.com"),
    emails=["test@test.com"],
)
cfg_error = ProjectionConfig(
    fields={"full_name": FieldConfig(include=True)},
    missing_value_policy="error",
)
try:
    proj.project(minimal, cfg_error)
    check("Error policy: should have raised", False, "no exception")
except ValueError as e:
    check("Error policy: raises ValueError for missing field", True, str(e))

# ── Test 7: include_provenance=True ──────────────────────────────────────
cfg_prov = ProjectionConfig(include_provenance=True)
out7 = proj.project(candidate, cfg_prov)
check("Provenance: _provenance block present", "_provenance" in out7, list(out7))
check("Provenance: full_name has records", "full_name" in out7.get("_provenance", {}), out7.get("_provenance"))

# ── Test 8: Confidence renaming in _confidence block ─────────────────────
cfg_rename_conf = ProjectionConfig(
    fields={"full_name": FieldConfig(include=True, rename="name")},
    include_confidence=True,
)
out8 = proj.project(candidate, cfg_rename_conf)
conf_block = out8.get("_confidence", {})
check("Confidence: renamed key 'name' in _confidence", "name" in conf_block, list(conf_block))

# ── Test 9: JSON serialisability ─────────────────────────────────────────
try:
    json_str = json.dumps(out, default=str)
    check("JSON: output is serialisable", True)
    reparsed = json.loads(json_str)
    check("JSON: roundtrip candidate_id", reparsed["candidate_id"] == out["candidate_id"], reparsed.get("candidate_id"))
except Exception as e:
    check("JSON: serialisable", False, str(e))

# ── Test 10: ProjectionConfig.from_dict ──────────────────────────────────
raw_cfg = {
    "_comment": "This is a comment",
    "fields": {"full_name": {"include": True, "rename": "name"}},
    "include_confidence": False,
    "include_provenance": False,
    "missing_value_policy": "null",
}
cfg_parsed = ProjectionConfig.from_dict(raw_cfg)
check("Config: from_dict parses rename", cfg_parsed.output_key_for("full_name") == "name", cfg_parsed.output_key_for("full_name"))
check("Config: _comment ignored", cfg_parsed.include_confidence == False, cfg_parsed.include_confidence)

# ── Test 11: Validation — valid output ───────────────────────────────────
vr = validate_output(out)
check("Validation: valid output passes", vr.is_valid, vr.summary())
check("Validation: zero errors", vr.error_count == 0, vr.error_count)
print(f"  Validation result: {vr.summary()}")

# ── Test 12: Validation — missing candidate_id ───────────────────────────
bad = dict(out)
del bad["candidate_id"]
vr2 = validate_output(bad)
check("Validation: missing candidate_id = error", not vr2.is_valid, vr2.summary())

# ── Test 13: Validation — bad confidence value ───────────────────────────
bad_conf = {"candidate_id": "fcbcbc64-f85c-5025-877c-37f4c7a12d6e", "_confidence": {"full_name": {"score": 1.5}}}
vr3 = validate_output(bad_conf)
check("Validation: score > 1.0 flagged as error", not vr3.is_valid, vr3.summary())

# ── Test 14: Validation — bad phone format ───────────────────────────────
bad_phone = {"candidate_id": "fcbcbc64-f85c-5025-877c-37f4c7a12d6e", "phones": ["not-a-phone"]}
vr4 = validate_output(bad_phone)
check("Validation: non-E164 phone = warning", vr4.is_valid and vr4.warning_count > 0, vr4.summary())

# ── Test 15: sample_inputs/config.json loads correctly ───────────────────
cfg_from_file = ProjectionConfig.from_file("d:/EightFold/sample_inputs/config.json")
check("Config: from_file loads sample config", isinstance(cfg_from_file, ProjectionConfig), cfg_from_file)
out_from_file = proj.project(candidate, cfg_from_file)
check("Config: from_file produces valid output", "candidate_id" in out_from_file, list(out_from_file))

print()
if failures:
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("ALL PROJECTION + VALIDATION TESTS PASSED")
