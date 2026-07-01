"""Tests for MergeEngine, ConflictResolver, and ConfidenceEngine."""

import pytest
from src.merger import MergeEngine, MergeResult, ConflictResolver, ConfidenceEngine, ValueCandidate
from src.normalizers import NormalizationResult
from src.models.source_type import SourceType


# ═══════════════════════════════════════════════════════════════════════════
# ConflictResolver
# ═══════════════════════════════════════════════════════════════════════════

class TestConflictResolver:
    resolver = ConflictResolver()

    def _candidate(self, value, source, priority=1):
        nr = NormalizationResult(value=value, success=True, factor=1.0,
                                 method="test", original=value)
        return ValueCandidate(value=value, source=source, norm_result=nr, priority=priority)

    def test_returns_none_for_empty_candidates(self):
        assert self.resolver.resolve("field", []) is None

    def test_returns_none_for_all_none_values(self):
        nr = NormalizationResult(value=None, success=False, factor=0.0, method="m", original=None)
        c = ValueCandidate(value=None, source=SourceType.RECRUITER_CSV, norm_result=nr, priority=1)
        assert self.resolver.resolve("field", [c]) is None

    def test_single_candidate_no_conflict(self):
        c = self._candidate("Alice", SourceType.RECRUITER_CSV, priority=1)
        decision = self.resolver.resolve("full_name", [c])
        assert decision is not None
        assert not decision.had_conflict
        assert decision.winner.value == "Alice"

    def test_agreement_no_conflict(self):
        c1 = self._candidate("Alice", SourceType.RECRUITER_CSV, priority=1)
        c2 = self._candidate("Alice", SourceType.RESUME_PDF, priority=2)
        decision = self.resolver.resolve("full_name", [c1, c2])
        assert not decision.had_conflict
        assert decision.agreed_sources == 2

    def test_conflict_higher_priority_wins(self):
        c1 = self._candidate("Alice Smith", SourceType.RECRUITER_CSV, priority=1)
        c2 = self._candidate("A. Smith",    SourceType.RESUME_PDF,    priority=2)
        decision = self.resolver.resolve("full_name", [c1, c2])
        assert decision.had_conflict
        assert decision.winner.value == "Alice Smith"
        assert len(decision.losers) == 1

    def test_conflict_is_deterministic(self):
        """Same inputs in different order → same winner every time."""
        c1 = self._candidate("Alice", SourceType.RECRUITER_CSV, priority=1)
        c2 = self._candidate("Bob",   SourceType.RESUME_PDF,    priority=2)
        d1 = self.resolver.resolve("f", [c1, c2])
        d2 = self.resolver.resolve("f", [c2, c1])  # reversed
        assert d1.winner.value == d2.winner.value == "Alice"

    def test_conflict_reason_is_populated(self):
        c1 = self._candidate("A", SourceType.RECRUITER_CSV, priority=1)
        c2 = self._candidate("B", SourceType.RESUME_PDF,    priority=2)
        d = self.resolver.resolve("f", [c1, c2])
        assert len(d.reason) > 20


# ═══════════════════════════════════════════════════════════════════════════
# ConfidenceEngine
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceEngine:
    engine = ConfidenceEngine()

    def _nr(self, factor=1.0):
        return NormalizationResult(value="x", success=True, factor=factor,
                                   method="m", original="x")

    def test_score_clamped_to_one(self):
        fc = self.engine.compute("f", SourceType.RECRUITER_CSV, self._nr(1.0), 5)
        assert fc.score <= 1.0

    def test_corroboration_increases_score(self):
        fc1 = self.engine.compute("f", SourceType.RECRUITER_CSV, self._nr(0.8), 1)
        fc2 = self.engine.compute("f", SourceType.RECRUITER_CSV, self._nr(0.8), 2)
        assert fc2.score >= fc1.score

    def test_lower_norm_factor_reduces_score(self):
        fc_high = self.engine.compute("f", SourceType.RECRUITER_CSV, self._nr(1.0), 1)
        fc_low  = self.engine.compute("f", SourceType.RECRUITER_CSV, self._nr(0.5), 1)
        assert fc_low.score < fc_high.score

    def test_score_in_valid_range(self):
        fc = self.engine.compute("f", SourceType.RESUME_PDF, self._nr(0.7), 1)
        assert 0.0 <= fc.score <= 1.0

    def test_explanation_is_non_empty_string(self):
        fc = self.engine.compute("full_name", SourceType.RECRUITER_CSV, self._nr(0.9), 2)
        assert isinstance(fc.explanation, str) and len(fc.explanation) > 10

    def test_overall_confidence_empty(self):
        assert self.engine.compute_overall({}) == 0.0

    def test_overall_confidence_weighted(self):
        from src.models.field_confidence import FieldConfidence
        # full_name has weight 1.5, links has weight 0.8
        fc_name  = FieldConfidence(source_reliability=1.0, normalization_factor=1.0,
                                   corroboration_bonus=1.0, explanation="")
        fc_links = FieldConfidence(source_reliability=0.5, normalization_factor=1.0,
                                   corroboration_bonus=1.0, explanation="")
        overall = self.engine.compute_overall({"full_name": fc_name, "links": fc_links})
        # Should be closer to fc_name.score because full_name has higher weight
        assert overall > 0.6


# ═══════════════════════════════════════════════════════════════════════════
# MergeEngine
# ═══════════════════════════════════════════════════════════════════════════

class TestMergeEngine:

    def test_single_source_returns_merge_result(self, raw_csv):
        result = MergeEngine().merge([raw_csv])
        assert isinstance(result, MergeResult)

    def test_name_normalized(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        assert c.full_name == "Priya Sharma"

    def test_email_lowercased(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        assert "priya.sharma@email.com" in c.emails

    def test_email_deduplicated(self, raw_csv):
        # raw_csv has 2 distinct emails
        c = MergeEngine().merge([raw_csv]).candidate
        assert len(c.emails) == 2

    def test_phone_e164(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        assert "+919876543210" in c.phones

    def test_skills_canonicalized(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        names = [s.name for s in c.skills]
        assert "Python" in names
        assert "Apache Spark" in names  # from "apache spark"

    def test_location_country_code(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        assert c.location is not None
        assert c.location.country_code == "IN"

    def test_candidate_id_is_uuid(self, raw_csv):
        import re
        c = MergeEngine().merge([raw_csv]).candidate
        assert re.match(r"^[0-9a-f-]{36}$", c.candidate_id)

    def test_candidate_id_stable_per_email(self, raw_csv):
        """Same email → same UUID5 every time."""
        c1 = MergeEngine().merge([raw_csv]).candidate
        c2 = MergeEngine().merge([raw_csv]).candidate
        assert c1.candidate_id == c2.candidate_id

    def test_empty_sources_returns_empty_candidate(self):
        result = MergeEngine().merge([])
        assert result.candidate is not None
        assert len(result.warnings) > 0

    def test_corroboration_boosts_confidence(self, raw_csv, raw_pdf):
        single = MergeEngine().merge([raw_csv]).candidate
        dual   = MergeEngine().merge([raw_csv, raw_pdf]).candidate
        assert dual.overall_confidence >= single.overall_confidence

    def test_conflict_csv_wins_over_pdf(self, raw_csv, raw_conflicting_pdf):
        result = MergeEngine().merge([raw_csv, raw_conflicting_pdf])
        assert result.candidate.full_name == "Priya Sharma"  # CSV value
        assert any(d.had_conflict for d in result.conflicts)

    def test_skills_unioned_across_sources(self, raw_csv, raw_pdf):
        c = MergeEngine().merge([raw_csv, raw_pdf]).candidate
        names = [s.name for s in c.skills]
        # CSV: Python, Spark, Kafka, SQL; PDF: Python, Spark, TensorFlow, Docker
        assert "TensorFlow" in names
        assert "Python" in names

    def test_experience_from_pdf(self, raw_pdf):
        c = MergeEngine().merge([raw_pdf]).candidate
        assert len(c.experience) == 1
        assert c.experience[0].title == "Senior Data Engineer"
        assert c.experience[0].start_date == "2020-01"
        assert c.experience[0].is_current is True

    def test_education_from_pdf(self, raw_pdf):
        c = MergeEngine().merge([raw_pdf]).candidate
        assert len(c.education) == 1
        assert c.education[0].institution == "IIT Bombay"

    def test_provenance_recorded(self, raw_csv):
        c = MergeEngine().merge([raw_csv]).candidate
        assert "full_name" in c.provenance
        assert len(c.provenance["full_name"]) > 0

    def test_decision_log_populated_on_conflict(self, raw_csv, raw_conflicting_pdf):
        result = MergeEngine().merge([raw_csv, raw_conflicting_pdf])
        assert len(result.decision_log) > 0
