"""
Tests for all 7 field normalizers.

Uses parametrize extensively so each test case is individually named
and reported — failures are pinpointed without extra boilerplate.
"""

import pytest
from src.normalizers import (
    normalize_phone, normalize_email, normalize_date, normalize_name,
    normalize_url, normalize_country, normalize_skill, SkillNormalizer,
    deduplicate_emails, NormalizationResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# Phone
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected_e164,min_factor", [
    ("+91-98765-43210",   "+919876543210", 1.0),
    ("+1 (415) 555-0192", "+14155550192",  1.0),
    ("+44 20 7946 0958",  "+442079460958", 1.0),
])
def test_phone_explicit_country_code(raw, expected_e164, min_factor):
    r = normalize_phone(raw)
    assert r.success
    assert r.value == expected_e164
    assert r.factor >= min_factor


def test_phone_default_region_india():
    r = normalize_phone("09876543211", default_country="IN")
    assert r.success
    assert r.value.startswith("+91")
    assert r.factor < 1.0  # not perfect (assumed region)


def test_phone_invalid_returns_original_with_warning():
    r = normalize_phone("not-a-phone")
    assert not r.success
    assert r.factor < 0.5
    assert r.warning is not None


def test_phone_empty_returns_none():
    r = normalize_phone("")
    assert r.value is None
    assert r.factor == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Email
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected", [
    ("Priya.Sharma@Email.COM", "priya.sharma@email.com"),
    ("UPPER@DOMAIN.IO",        "upper@domain.io"),
    ("already@lower.com",      "already@lower.com"),
])
def test_email_lowercase(raw, expected):
    r = normalize_email(raw)
    assert r.success
    assert r.value == expected
    assert r.factor == 1.0


def test_email_double_at_rejected():
    r = normalize_email("bad@@double.com")
    assert not r.success
    assert r.factor < 0.5


def test_email_empty():
    r = normalize_email("")
    assert r.value is None
    assert r.factor == 0.0


def test_email_deduplicate_case_insensitive():
    emails = ["a@b.com", "A@B.COM", "c@d.com", "a@b.com"]
    result = deduplicate_emails(emails)
    assert result == ["a@b.com", "c@d.com"]


# ═══════════════════════════════════════════════════════════════════════════
# Date
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected_value,expected_factor", [
    ("March 2021",  "2021-03", 1.0),
    ("2021-06-15",  "2021-06", 1.0),
    ("06/2021",     "2021-06", 1.0),
    ("2019",        "2019-01", 0.70),
])
def test_date_normalization(raw, expected_value, expected_factor):
    r = normalize_date(raw)
    assert r.success
    assert r.value == expected_value
    assert r.factor == pytest.approx(expected_factor)


@pytest.mark.parametrize("present_str", ["Present", "Current", "Now", "present", "current"])
def test_date_present_marker(present_str):
    r = normalize_date(present_str)
    assert r.success
    assert r.value is None  # None = ongoing


def test_date_empty():
    r = normalize_date("")
    assert not r.success
    assert r.factor == 0.0


def test_date_unparseable():
    r = normalize_date("not-a-date-xyz")
    assert not r.success
    assert r.warning is not None


# ═══════════════════════════════════════════════════════════════════════════
# Name
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected", [
    ("PRIYA SHARMA",     "Priya Sharma"),
    ("priya sharma",     "Priya Sharma"),
    ("john o'brien",     "John O'Brien"),
    ("Priya Sharma",     "Priya Sharma"),  # already correct
])
def test_name_normalization(raw, expected):
    r = normalize_name(raw)
    assert r.success
    assert r.value == expected


def test_name_already_correct_has_full_factor():
    r = normalize_name("Priya Sharma")
    assert r.factor == 1.0


def test_name_normalized_has_reduced_factor():
    r = normalize_name("priya sharma")
    assert r.factor < 1.0


def test_name_empty():
    r = normalize_name("")
    assert r.value is None
    assert r.factor == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# URL
# ═══════════════════════════════════════════════════════════════════════════

def test_url_scheme_added():
    r = normalize_url("linkedin.com/in/priyasharma")
    assert r.value.startswith("https://")
    assert r.factor == pytest.approx(0.90)


def test_url_trailing_slash_removed():
    r = normalize_url("https://github.com/johndoe/")
    assert not r.value.endswith("/")


def test_url_netloc_lowercased():
    r = normalize_url("https://LinkedIn.com/in/Test")
    assert "linkedin.com" in r.value


def test_url_empty():
    r = normalize_url("")
    assert r.value is None


def test_url_existing_scheme_has_full_factor():
    r = normalize_url("https://github.com/user")
    assert r.factor == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Country
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected_alpha2", [
    ("IN",                    "IN"),
    ("India",                 "IN"),
    ("USA",                   "US"),
    ("Bangalore, India",      "IN"),
    ("San Francisco, USA",    "US"),
    ("IND",                   "IN"),
    ("United States",         "US"),
])
def test_country_normalization(raw, expected_alpha2):
    r = normalize_country(raw)
    assert r.success, f"Expected success for '{raw}', got: {r}"
    assert r.value == expected_alpha2


def test_country_empty():
    r = normalize_country("")
    assert r.value is None


# ═══════════════════════════════════════════════════════════════════════════
# Skill
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("raw,expected_canonical", [
    ("python",       "Python"),
    ("Python",       "Python"),
    ("reactjs",      "React"),
    ("pyspark",      "Apache Spark"),
    ("scikit learn", "Scikit-learn"),
    ("TensorFlow",   "TensorFlow"),
    ("kafka",        "Apache Kafka"),
])
def test_skill_exact_match(raw, expected_canonical):
    r = normalize_skill(raw)
    assert r.success
    assert r.value == expected_canonical
    assert r.factor == 1.0


def test_skill_unknown_kept_as_is():
    r = normalize_skill("SomeObscureTool2024XYZ")
    assert not r.success
    assert r.factor == 0.60


def test_skill_normalizer_dedup():
    ns = SkillNormalizer()
    result = ns.canonical_names(["python", "Python", "reactjs", "react"])
    assert result == ["Python", "React"]


def test_norm_result_factor_validation():
    with pytest.raises(ValueError):
        NormalizationResult(value="x", success=True, factor=1.5, method="m", original="x")
