# Multi-Source Candidate Data Transformer

> **Eightfold AI — Senior Software Engineering Assignment**
>
> A production-quality ETL pipeline that ingests candidate data from heterogeneous sources (Recruiter CSV, Resume PDF), normalises every field to canonical form, merges across sources with deterministic conflict resolution, and emits a single enriched candidate profile with full provenance and confidence scoring.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage — CLI](#usage--cli)
- [Usage — Streamlit UI](#usage--streamlit-ui)
- [Output Files](#output-files)
- [Configuration — config.json](#configuration--configjson)
- [Extending the Pipeline](#extending-the-pipeline)
- [Running Tests](#running-tests)
- [Design Decisions](#design-decisions)

---

## Overview

```
[Recruiter CSV]  ──┐
                   ├──► ExtractorRegistry ──► MergeEngine ──► ProjectionEngine ──► 5 output files
[Resume PDF]     ──┘         │                    │
                        Normalizers          ConfidenceEngine
                        (7 fields)          ConflictResolver
```

**Supported sources (Phase 1):**
| Source | Extractor | Auto-detected by |
|---|---|---|
| Recruiter CSV | `RecruiterCSVExtractor` | `.csv` extension |
| Resume PDF | `ResumePDFExtractor` | `.pdf` extension |

**Adding new sources** (ATS JSON, LinkedIn, GitHub, Recruiter Notes) requires **zero changes to existing code** — see [Extending the Pipeline](#extending-the-pipeline).

---

## Architecture

```
src/
├── config/           ← Source priorities, skill synonyms, settings
├── extractors/       ← Plugin registry + per-source extractors
├── normalizers/      ← 7 pure field normalizers (phone, email, date, …)
├── merger/           ← MergeEngine, ConflictResolver, ConfidenceEngine
├── projection/       ← ProjectionEngine + ProjectionConfig (runtime output shaping)
├── validators/       ← Output schema validation
├── services/         ← PipelineOrchestrator (stage coordinator)
├── models/           ← Pydantic domain models (immutable after creation)
├── utils/            ← Logging, ID generation, HTML report
└── cli/              ← Argument parser
```

### Data Flow

```
File path(s)
    │
    ▼
ExtractorRegistry.detect(path)
    │  @register decorator auto-registers all extractors on import
    ▼
BaseExtractor.extract(path) → list[RawCandidateData]
    │
    ▼
MergeEngine.merge(sources)
    ├── _normalize_source()     # 7 normalizers per field
    ├── _merge_scalar()         # ConflictResolver → picks winner
    ├── _merge_list()           # union + dedup
    └── ConfidenceEngine        # score = reliability × norm_factor × corroboration
    │
    ▼
CanonicalCandidate  (frozen Pydantic model)
    │
    ▼
ProjectionEngine.project(candidate, config)  # field selection, renaming
    │
    ▼
validate_output(dict) → ValidationResult
    │
    ▼
5 output files written by PipelineOrchestrator
```

---

## Project Structure

```
EightFold/
├── main.py                         ← CLI entry point
├── app.py                          ← Streamlit UI
├── requirements.txt
├── pyproject.toml
├── sample_inputs/
│   ├── recruiter.csv               ← 3-row sample recruiter data
│   ├── resume.pdf                  ← Sample resume PDF
│   └── config.json                 ← Sample projection config
├── outputs/                        ← Generated output files (gitignored)
│   ├── candidate.json
│   ├── explanation.json
│   ├── metrics.json
│   ├── decision_log.json
│   └── report.html
├── src/
│   ├── config/
│   │   ├── settings.py             ← Pydantic Settings (env-configurable)
│   │   ├── source_priority.py      ← Source reliability scores
│   │   └── skill_synonyms.py       ← 68 canonical skills + aliases
│   ├── extractors/
│   │   ├── base.py                 ← BaseExtractor ABC
│   │   ├── registry.py             ← ExtractorRegistry (plugin system)
│   │   ├── csv_extractor.py        ← RecruiterCSVExtractor
│   │   └── pdf_extractor.py        ← ResumePDFExtractor
│   ├── normalizers/
│   │   ├── result.py               ← NormalizationResult dataclass
│   │   ├── phone.py                ← E.164 via phonenumbers
│   │   ├── email.py                ← Lowercase + RFC5322 validation
│   │   ├── date.py                 ← YYYY-MM via python-dateutil
│   │   ├── name.py                 ← Title-case with cultural edge cases
│   │   ├── url.py                  ← Scheme normalisation + platform inference
│   │   ├── country.py              ← ISO Alpha-2 via pycountry + rapidfuzz
│   │   └── skill.py                ← SkillNormalizer with synonym dict + fuzzy
│   ├── merger/
│   │   ├── conflict.py             ← ConflictResolver + ConflictDecision
│   │   ├── confidence.py           ← ConfidenceEngine (formula + weighted average)
│   │   └── engine.py               ← MergeEngine + MergeResult
│   ├── projection/
│   │   ├── config.py               ← ProjectionConfig + FieldConfig
│   │   └── engine.py               ← ProjectionEngine (dispatch table)
│   ├── validators/
│   │   └── output.py               ← validate_output() + ValidationResult
│   ├── services/
│   │   └── pipeline.py             ← PipelineOrchestrator (stage coordinator)
│   ├── models/
│   │   ├── candidate.py            ← CanonicalCandidate (frozen Pydantic)
│   │   ├── raw.py                  ← RawCandidateData + RawExperienceEntry
│   │   ├── sub_models.py           ← Location, SkillEntry, ExperienceEntry, …
│   │   ├── field_confidence.py     ← FieldConfidence with computed score
│   │   ├── provenance.py           ← ProvenanceRecord
│   │   └── source_type.py          ← SourceType enum
│   └── utils/
│       ├── logging_config.py       ← Structured logging (configurable from CLI)
│       ├── id_generator.py         ← UUID5 (email) / UUID4 (fallback)
│       └── html_report.py          ← Self-contained HTML renderer
└── tests/
    ├── conftest.py                 ← Shared pytest fixtures
    ├── test_normalizers.py         ← 53 parametrized normalizer tests
    ├── test_extractors.py          ← 17 extractor tests (incl. PDF with fitz)
    ├── test_merger.py              ← 28 merger/conflict/confidence tests
    └── test_projection.py          ← 30 projection + validator tests
```

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd EightFold

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

**Python 3.12+** is required.

---

## Usage — CLI

```bash
# CSV only
python main.py --csv sample_inputs/recruiter.csv

# PDF only
python main.py --resume sample_inputs/resume.pdf

# Both sources + custom config
python main.py \
  --csv sample_inputs/recruiter.csv \
  --resume sample_inputs/resume.pdf \
  --config sample_inputs/config.json \
  --output-dir outputs/

# Verbose logging
python main.py --csv recruiter.csv --log-level DEBUG

# Silent (no stdout, non-zero exit on validation errors)
python main.py --csv recruiter.csv --quiet

# Version
python main.py --version
```

**Sample output:**

```
  [####################] 100%  Complete.

------------------------------------------------------------
  Candidate : Priya Sharma
  ID        : 09c12063-be5e-5676-b66f-44d8a488433f
  Confidence: 97.0%
  Skills    : 6
  Warnings  : 0
------------------------------------------------------------
  Validation: [VALID] 0 error(s), 0 warning(s)
------------------------------------------------------------
  Output files:
    candidate      -> outputs\candidate.json
    decision_log   -> outputs\decision_log.json
    explanation    -> outputs\explanation.json
    metrics        -> outputs\metrics.json
    report         -> outputs\report.html
------------------------------------------------------------
```

---

## Usage — Streamlit UI

```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

**Features:**
- Drag-and-drop CSV, PDF, and config file uploads
- Live progress bar
- Tabbed output: Profile | Skills | Experience | Education | Metrics | Explanations | Raw JSON | Downloads
- Per-field confidence bars (green / amber / red)
- One-click download of all 5 output files

---

## Output Files

| File | Description |
|---|---|
| `candidate.json` | The merged candidate profile, projected per `config.json` |
| `explanation.json` | Per-field: chosen value, reason, had_conflict, discarded alternatives |
| `metrics.json` | Execution time, conflicts resolved, confidence score, etc. |
| `decision_log.json` | Timestamped audit log of every conflict resolution decision |
| `report.html` | Self-contained HTML report (open in any browser, no server needed) |

---

## Configuration — config.json

```json
{
  "_comment": "Projection configuration for the output profile",
  "fields": {
    "full_name":        { "include": true,  "rename": "name" },
    "years_experience": { "include": true,  "rename": "experience_years" },
    "experience":       { "include": true,  "rename": "work_history" },
    "pipeline_version": { "include": false  },
    "created_at":       { "include": false  }
  },
  "include_confidence": true,
  "include_provenance": false,
  "missing_value_policy": "null"
}
```

**`missing_value_policy` options:**
- `"null"` — include the field with a `null` value (default)
- `"omit"` — skip the field entirely
- `"error"` — raise a `ValueError` (useful for strict pipelines)

---

## Extending the Pipeline

Adding a new source (e.g., ATS JSON) requires **no changes to existing code**:

**1. Create the extractor:**

```python
# src/extractors/ats_json_extractor.py

from src.models.source_type import SourceType
from src.models.raw import RawCandidateData
from .base import BaseExtractor
from .registry import ExtractorRegistry

@ExtractorRegistry.register                # ← self-registers on import
class ATSJsonExtractor(BaseExtractor):
    source_type = SourceType.ATS_JSON

    def can_handle(self, source) -> bool:
        return str(source).endswith(".json")

    def extract(self, source) -> list[RawCandidateData]:
        ...
```

**2. Add the source type:**

```python
# src/models/source_type.py
class SourceType(str, Enum):
    RECRUITER_CSV = "recruiter_csv"
    RESUME_PDF    = "resume_pdf"
    ATS_JSON      = "ats_json"       # ← add this line
```

**3. Register the import** in `src/extractors/__init__.py`:

```python
from .ats_json_extractor import ATSJsonExtractor
```

**4. Set priority and reliability** in `src/config/source_priority.py`.

That's it. The MergeEngine, ConflictResolver, ConfidenceEngine, ProjectionEngine, and Validator all work unchanged.

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific module
python -m pytest tests/test_normalizers.py -v

# With coverage report
python -m pytest tests/ --cov=src --cov-report=term-missing
```

**Test summary (128 tests):**

| Module | Tests | Focus |
|---|---|---|
| `test_normalizers.py` | 53 | All 7 normalizers, parametrized |
| `test_extractors.py`  | 17 | CSV edge cases, PDF text, registry |
| `test_merger.py`      | 28 | Conflict resolution, confidence, merge logic |
| `test_projection.py`  | 30 | Config, field renaming, policy, validator |

---

## Design Decisions

### 1. Plugin Registry (`@ExtractorRegistry.register`)
New extractors register themselves at import time — no central list to maintain, no switch/case. Adding a new source is a 3-file change with zero risk to existing sources.

### 2. Immutable `CanonicalCandidate` (`frozen=True`)
Once built by the MergeEngine, the canonical model cannot be mutated. This eliminates a class of bugs where downstream code accidentally modifies shared state. The ProjectionEngine only *reads* from it.

### 3. `NormalizationResult` envelope
Every normalizer returns the same dataclass instead of a bare value. This gives the Confidence Engine the normalization factor, the Merge Engine the method name for provenance, and the caller the original value for audit logs — all without every module knowing about every other module.

### 4. Confidence formula
```
score = source_reliability × normalization_factor × corroboration_bonus
```
Each term is independently interpretable and logged in the `explanation` string. Engineers can diagnose a low confidence score by inspecting which term drove it down.

### 5. Deterministic conflict resolution
Conflict winner is always the **highest-priority source** (priority defined in `SOURCE_PRIORITY`). Given the same inputs in any order, the same value always wins. This makes the pipeline reproducible and auditable.

### 6. Two-pass MergeEngine
Pass 1: normalize all sources → `_NormalizedSource` intermediate objects.
Pass 2: merge field-by-field from clean normalized data.
Keeping normalization and merge separate means each is independently testable and the merge logic never calls normalizer code.

---

