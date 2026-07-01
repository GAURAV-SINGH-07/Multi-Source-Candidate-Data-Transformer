"""Quick smoke test for all 7 normalizers."""

import sys
sys.path.insert(0, "d:/EightFold")

from src.normalizers import (
    normalize_phone, normalize_email, normalize_date, normalize_name,
    normalize_url, normalize_country, normalize_skill, SkillNormalizer,
    deduplicate_emails,
)

failures = []

def check(label, cond, got=""):
    if not cond:
        failures.append(f"FAIL [{label}] got={got!r}")
    else:
        print(f"[PASS] {label}")

# ── Phone ──────────────────────────────────────────────────────────────────
r = normalize_phone("+91-98765-43210")
check("Phone: explicit CC", r.value == "+919876543210" and r.factor == 1.0, r)

r = normalize_phone("09876543211", default_country="IN")
check("Phone: default region", r.success and r.value.startswith("+91"), r)

r = normalize_phone("+1 (415) 555-0192")
check("Phone: US explicit", r.value == "+14155550192", r)

r = normalize_phone("not-a-phone")
check("Phone: invalid returns original", not r.success and r.factor < 0.5, r)

r = normalize_phone("")
check("Phone: empty returns None", r.value is None and r.factor == 0.0, r)

# ── Email ──────────────────────────────────────────────────────────────────
r = normalize_email("Priya.Sharma@Email.COM")
check("Email: lowercased", r.value == "priya.sharma@email.com" and r.factor == 1.0, r)

r = normalize_email("already@lowercase.com")
check("Email: already_lowercase method", r.method == "already_lowercase", r)

r = normalize_email("bad@@email.com")
check("Email: double @ rejected", not r.success, r)

r = normalize_email("")
check("Email: empty", r.value is None, r)

deduped = deduplicate_emails(["a@b.com", "A@B.COM", "c@d.com", "a@b.com"])
check("Email: deduplicate", deduped == ["a@b.com", "c@d.com"], deduped)

# ── Date ───────────────────────────────────────────────────────────────────
r = normalize_date("March 2021")
check("Date: month year", r.value == "2021-03" and r.success, r)

r = normalize_date("2019")
check("Date: year only", r.value == "2019-01" and r.factor == 0.70, r)

r = normalize_date("Present")
check("Date: present marker", r.value is None and r.success, r)

r = normalize_date("current")
check("Date: current marker", r.value is None and r.success, r)

r = normalize_date("2021-06-15")
check("Date: ISO format", r.value == "2021-06", r)

r = normalize_date("")
check("Date: empty", r.value is None and r.factor == 0.0, r)

# ── Name ───────────────────────────────────────────────────────────────────
r = normalize_name("PRIYA SHARMA")
check("Name: ALL CAPS", r.value == "Priya Sharma", r)

r = normalize_name("priya sharma")
check("Name: all lower", r.value == "Priya Sharma", r)

r = normalize_name("patrick o'brien")
check("Name: O'Brien", r.value == "Patrick O'Brien", r)

r = normalize_name("Priya Sharma")
check("Name: already proper (factor 1.0)", r.factor == 1.0, r)

# ── URL ────────────────────────────────────────────────────────────────────
r = normalize_url("linkedin.com/in/priyasharma")
check("URL: scheme added", r.value.startswith("https://") and r.factor == 0.90, r)

r = normalize_url("https://github.com/johndoe/")
check("URL: trailing slash removed", not r.value.endswith("/"), r)

r = normalize_url("https://LinkedIn.com/in/Test")
check("URL: netloc lowercased", "linkedin.com" in r.value, r)

r = normalize_url("")
check("URL: empty", r.value is None, r)

# ── Country ────────────────────────────────────────────────────────────────
r = normalize_country("IN")
check("Country: alpha2 direct", r.value == "IN" and r.factor == 1.0, r)

r = normalize_country("India")
check("Country: full name", r.value == "IN", r)

r = normalize_country("USA")
check("Country: USA alias", r.value == "US", r)

r = normalize_country("Bangalore, India")
check("Country: from location string", r.value == "IN", r)

r = normalize_country("San Francisco, USA")
check("Country: city USA location", r.value == "US", r)

r = normalize_country("IND")
check("Country: alpha3", r.value == "IN", r)

# ── Skill ──────────────────────────────────────────────────────────────────
r = normalize_skill("python")
check("Skill: exact alias match", r.value == "Python" and r.factor == 1.0, r)

r = normalize_skill("reactjs")
check("Skill: alias reactjs -> React", r.value == "React", r)

r = normalize_skill("scikit learn")
check("Skill: scikit learn -> Scikit-learn", r.value == "Scikit-learn", r)

r = normalize_skill("pyspark")
check("Skill: pyspark -> Apache Spark", r.value == "Apache Spark", r)

r = normalize_skill("TensorFlow")
check("Skill: TensorFlow canonical", r.value == "TensorFlow", r)

r = normalize_skill("SomeObscureTool2024")
check("Skill: unknown kept as-is", not r.success and r.factor == 0.60, r)

ns = SkillNormalizer()
canonicals = ns.canonical_names(["python", "Python", "reactjs", "react"])
check("Skill: dedup via canonical_names", canonicals == ["Python", "React"], canonicals)

print()
if failures:
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("ALL NORMALIZER TESTS PASSED")
