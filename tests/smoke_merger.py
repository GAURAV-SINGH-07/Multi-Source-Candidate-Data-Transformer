"""Integration smoke test for the Merge Engine + Confidence Engine."""

import sys
sys.path.insert(0, "d:/EightFold")

from datetime import datetime
from src.models.raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from src.models.source_type import SourceType
from src.merger import MergeEngine, MergeResult

failures = []

def check(label, cond, got=""):
    if not cond:
        failures.append(f"FAIL [{label}] got={got!r}")
    else:
        print(f"[PASS] {label}")

engine = MergeEngine()

# ── Test 1: Single source (CSV only) ──────────────────────────────────────
csv_source = RawCandidateData(
    source=SourceType.RECRUITER_CSV,
    source_file="recruiter.csv",
    full_name="priya sharma",
    emails=["Priya.Sharma@Email.COM", "priya@alt.com"],
    phones=["+91-98765-43210"],
    location="Bangalore, India",
    links=["linkedin.com/in/priyasharma"],
    headline="Senior Data Engineer",
    years_experience=6.0,
    skills=["Python", "apache spark", "kafka", "sql"],
)
result = engine.merge([csv_source])
c = result.candidate

check("Single source: full_name normalized", c.full_name == "Priya Sharma", c.full_name)
check("Single source: email lowercased", "priya.sharma@email.com" in c.emails, c.emails)
check("Single source: email deduped (2 unique)", len(c.emails) == 2, c.emails)
check("Single source: phone E.164", "+919876543210" in c.phones, c.phones)
check("Single source: location country", c.location and c.location.country_code == "IN", c.location)
check("Single source: linkedin link", any("linkedin" in l.url for l in c.links), c.links)
check("Single source: Python canonical", any(s.name == "Python" for s in c.skills), c.skills)
check("Single source: Apache Spark canonical", any(s.name == "Apache Spark" for s in c.skills), c.skills)
check("Single source: overall_confidence > 0", c.overall_confidence > 0, c.overall_confidence)
check("Single source: candidate_id is UUID", len(c.candidate_id) == 36, c.candidate_id)
check("Single source: provenance has full_name", "full_name" in c.provenance, list(c.provenance))
check("Single source: confidence has full_name", "full_name" in c.confidence, list(c.confidence))

# ── Test 2: Two sources with agreement ───────────────────────────────────
pdf_source = RawCandidateData(
    source=SourceType.RESUME_PDF,
    source_file="resume.pdf",
    full_name="Priya Sharma",
    emails=["priya.sharma@email.com"],
    phones=["+91-98765-43210"],
    location="Bangalore, IN",
    years_experience=6,
    skills=["Python", "pyspark", "TensorFlow"],
)
result2 = engine.merge([csv_source, pdf_source])
c2 = result2.candidate

check("Two sources: no conflicts on name", not result2.conflicts or not any(c.field == "full_name" for c in result2.conflicts), result2.conflicts)
check("Two sources: confidence boosted", c2.confidence.get("full_name") and c2.confidence["full_name"].corroboration_bonus > 1.0, c2.confidence.get("full_name"))
check("Two sources: skills unioned", len(c2.skills) >= 3, len(c2.skills))
check("Two sources: TensorFlow in skills", any(s.name == "TensorFlow" for s in c2.skills), c2.skills)
check("Two sources: overall_confidence > 0.7", c2.overall_confidence > 0.7, c2.overall_confidence)
print(f"  Confidence scores: {[(k, round(v.score, 3)) for k, v in c2.confidence.items()]}")

# ── Test 3: Conflicting values — CSV wins ────────────────────────────────
conflicting_pdf = RawCandidateData(
    source=SourceType.RESUME_PDF,
    source_file="resume.pdf",
    full_name="P. Sharma",  # Different name
    emails=["priya.sharma@email.com"],
    phones=["+91-98765-43210"],
    location="Mumbai, India",  # Different city
)
result3 = engine.merge([csv_source, conflicting_pdf])
c3 = result3.candidate

check("Conflict: CSV name wins over PDF", c3.full_name == "Priya Sharma", c3.full_name)
check("Conflict: decision recorded", len(result3.conflicts) > 0, result3.conflicts)
check("Conflict: decision_log populated", len(result3.decision_log) > 0, result3.decision_log)
check("Conflict: explanation has alternatives", "alternatives" in result3.explanation.get("full_name", {}), result3.explanation.get("full_name"))

# ── Test 4: Empty input ──────────────────────────────────────────────────
empty_result = engine.merge([])
check("Empty: returns MergeResult", isinstance(empty_result, MergeResult), empty_result)
check("Empty: candidate has UUID", len(empty_result.candidate.candidate_id) == 36, empty_result.candidate.candidate_id)
check("Empty: warnings populated", len(empty_result.warnings) > 0, empty_result.warnings)

# ── Test 5: No email → random UUID ───────────────────────────────────────
no_email = RawCandidateData(
    source=SourceType.RECRUITER_CSV,
    full_name="Ghost Candidate",
    phones=["+14155550192"],
    skills=["JavaScript"],
)
result5 = engine.merge([no_email])
check("No email: still gets a UUID", len(result5.candidate.candidate_id) == 36, result5.candidate.candidate_id)
check("No email: emails list is empty", result5.candidate.emails == [], result5.candidate.emails)

# ── Test 6: Experience + Education passthrough ────────────────────────────
with_exp = RawCandidateData(
    source=SourceType.RESUME_PDF,
    full_name="John Doe",
    emails=["john@doe.com"],
    experience=[
        RawExperienceEntry(title="Engineer", company="Acme", start_date="Jan 2020", end_date="Present", is_current=True),
    ],
    education=[
        RawEducationEntry(institution="IIT Delhi", degree="B.Tech", field_of_study="CS", end_date="2019"),
    ],
)
result6 = engine.merge([with_exp])
c6 = result6.candidate
check("Experience: title preserved", c6.experience and c6.experience[0].title == "Engineer", c6.experience)
check("Experience: start_date normalized", c6.experience and c6.experience[0].start_date == "2020-01", c6.experience)
check("Experience: is_current preserved", c6.experience and c6.experience[0].is_current, c6.experience)
check("Education: institution preserved", c6.education and c6.education[0].institution == "IIT Delhi", c6.education)

print()
if failures:
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("ALL MERGE ENGINE TESTS PASSED")
