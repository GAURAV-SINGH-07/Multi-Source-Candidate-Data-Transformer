# Multi-Source Candidate Data Transformer — Engineering Design Document

This document provides a comprehensive engineering description of the Multi-Source Candidate Data Transformer project. It details the architecture, module responsibilities, domain models, pipeline execution flow, algorithms, and engineering design rationale of the system.

---

# Project Overview

### Purpose
The Multi-Source Candidate Data Transformer is a production-style ETL (Extract, Transform, Load) pipeline designed to ingest candidate profiles from heterogeneous, raw data sources (such as recruiter-entered spreadsheet rows and parsed text resumes), normalize their properties into clean canonical shapes, resolve conflicting information deterministically, and construct a single unified candidate profile.

### Assignment Goal
The core objective is to solve the classic data-integration problem of candidate profiles in human resources tech stack. When a candidate's information is gathered from multiple channels (e.g. self-submitted PDFs, recruiter phone screen notes, ATS entries), the data is typically incomplete, duplicated, unstructured, or conflicting. This system handles this data lifecycle by:
1. Ingesting multiple unstructured/semi-structured files.
2. Normalizing variables to strict data formats (e.g., ISO country codes, E.164 phone numbers).
3. Merging the sources using deterministic priority hierarchies.
4. Outputting a JSON-serializable structured profile and a browser-viewable dashboard showing full provenance and explainable confidence metrics.

### Supported Inputs
The pipeline supports the following input sources natively:
* **Recruiter CSV:** Semi-structured tabular candidate records. Columns are mapped flexibly using aliases to support varied naming schemas.
* **Resume PDF:** Unstructured text-based PDFs containing sections such as Contact, Experience, Education, and Skills.

Additionally, the system reserves schema keys for **ATS JSON**, **LinkedIn profiles**, **GitHub profiles**, and **Recruiter Notes**, allowing rapid integration of these plugins without schema modifications.

### Supported Outputs
Each pipeline run produces five synchronized output files in the target directory:
1. `candidate.json`: The projected candidate profile containing the final values shaped by a config-driven schema mapper.
2. `explanation.json`: A granular audit report explaining the pipeline's decisions on every field (e.g., chosen value, discarded alternatives, matching metrics).
3. `metrics.json`: Performance metrics, execution details, record counts, and schema validation summaries.
4. `decision_log.json`: A chronological audit log documenting every conflict resolution decision made by the merge engine.
5. `report.html`: A self-contained, interactive candidate profile dashboard featuring styled confidence gauges, timelines, and explanation accordions.

### Overall Design Philosophy
* **Dependency Inversion:** Wires stages using abstract interfaces (`BaseExtractor`, registry maps) to allow extending components without modifying the pipeline engine.
* **Immutability:** Ensures candidate domain models are frozen once constructed to prevent side-effects in downstream presentation or reporting layers.
* **Zero Magic Numbers:** Decomposes confidence metrics and conflict logic into transparent formulas whose weights, priorities, and thresholds are fully defined in configuration files.
* **Auditable Operations:** Every field value retains its history (provenance records, alternate values, extraction timestamps, and confidence scores) throughout the pipeline.

### Implementation Notes for the Current Codebase
* The orchestrator currently routes each configured input file to a concrete extractor by known source type (CSV or PDF) rather than relying on runtime auto-detection for the main execution path.
* The `years_experience` field is handled as a derived value in the merge layer: when experience entries contain parseable date ranges, the merger computes total experience from work history; otherwise it preserves the summary-based value extracted from the source text.
* The canonical schema remains stable: the bug fix was implemented in extraction and merge logic, not by changing the contract of `CanonicalCandidate` or downstream projection/validation modules.

---

# High-Level Architecture

The system is designed as a decoupled, seven-stage sequential pipeline. This design isolates parsing, data validation, domain merging, and presentation logic into independent, testable modules.

```
                  ┌──────────────────────┐
                  │   Pipeline Input     │
                  └──────────┬───────────┘
                             │
                             ▼
 ┌─────────┐      ┌──────────────────────┐
 │Registry ├─────►│  1. Extract Stage    │ (BaseExtractor plugins)
 └─────────┘      └──────────┬───────────┘
                             │ list[RawCandidateData]
                             ▼
 ┌─────────┐      ┌──────────────────────┐
 │Normal-  ├─────►│  2. Normalize &      │ (7 pure normalizers)
 │izers    │      │     Merge Stage      │ (ConflictResolver, ConfidenceEngine)
 └─────────┘      └──────────┬───────────┘
                             │ CanonicalCandidate (Frozen)
                             ▼
 ┌─────────┐      ┌──────────────────────┐
 │Config   ├─────►│  3. Project Stage    │ (ProjectionEngine & Config)
 └─────────┘      └──────────┬───────────┘
                             │ dict[str, Any]
                             ▼
                  ┌──────────────────────┐
                  │  4. Validate Stage   │ (validate_output schema validation)
                  └──────────┬───────────┘
                             │ ValidationResult
                             ▼
                  ┌──────────────────────┐
                  │  5. Metrics Stage    │ (Execution metrics compilation)
                  └──────────┬───────────┘
                             │ dict[str, Any] (metrics payload)
                             ▼
                  ┌──────────────────────┐
                  │  6. Generate Stage   │ (Atomic write-then-replace system)
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   5 Output Files     │
                  └──────────────────────┘
```

### Module Responsibilities
* **`PipelineOrchestrator` (`src/services/pipeline.py`):** Acts as the central coordinator. It accepts file paths, sequences the execution stages, passes callbacks for live progress telemetry, and handles file I/O.
* **`ExtractorRegistry` (`src/extractors/registry.py`):** Maintains the active list of extractor subclasses. It analyzes file formats to auto-detect and instantiate the correct plugin.
* **`MergeEngine` (`src/merger/engine.py`):** Orchestrates the normalization and merging processes. It transforms raw candidate data envelopes into a single `CanonicalCandidate`.
* **`ConflictResolver` (`src/merger/conflict.py`):** Resolves property conflicts deterministically when multiple sources assert differing values for a single-valued field.
* **`ConfidenceEngine` (`src/merger/confidence.py`):** Analyzes the quality of sources, the success of normalization, and corroborating agreements to produce an auditable float score in `[0, 1]` for each property.
* **`ProjectionEngine` (`src/projection/engine.py`):** Shapes the immutable candidate model into a plain Python dictionary based on field selection, renaming rules, and missing value policies defined in a `config.json`.
* **`validate_output` (`src/validators/output.py`):** Evaluates the projected output dictionary against schema constraints (such as UUID formats, E.164 rules, and type boundaries) to ensure downstream compatibility.

### Module Dependencies
All core data pipelines are driven by low-level, specialized python libraries to enforce accuracy:
* **`fitz` (PyMuPDF):** Selected for high-performance text extraction from PDF documents.
* **`phonenumbers`:** Wraps Google’s libphonenumber port to handle E.164 normalization, validity checks, and default region parsing.
* **`python-dateutil`:** Provides parser engines to parse fuzzy datetime strings safely.
* **`pycountry`:** Supplies a localized ISO 3166-1 database of countries, codes, and names.
* **`rapidfuzz`:** Implements rapid Levenshtein distance calculations to fuzzy-match skills and country strings.
* **`pydantic`:** Powers validation and serialization of model classes.

---

# Folder Structure

The project layout follows a strict separation of concerns, dividing domain models, logic packages, utilities, and configuration modules into distinct directories:

* **`src/config/`**
  * **Purpose:** Stores settings and static knowledge databases.
  * **Responsibility:** Contains settings settings (`settings.py`), source definitions (`source_priority.py`), and skill mappings (`skill_synonyms.py`).
  * **Important Classes:** `Settings`.
  * **Interaction:** Imported across extractors, normalizers, and the merge engine.

* **`src/models/`**
  * **Purpose:** Defines the pipeline's core data models.
  * **Responsibility:** Declares Pydantic data structures for raw entries, sub-records, and canonical candidates.
  * **Important Classes:** `CanonicalCandidate`, `RawCandidateData`, `FieldConfidence`, `ProvenanceRecord`, `Location`, `Link`, `SkillEntry`, `ExperienceEntry`, `EducationEntry`, `SourceType`.
  * **Interaction:** Serves as the primary data interface passed between the extractors, merger, and projector.

* **`src/extractors/`**
  * **Purpose:** Implements file-parsing logic.
  * **Responsibility:** Declares the abstract base class and concrete plugins for parsing CSV and PDF formats.
  * **Important Classes:** `BaseExtractor`, `ExtractorRegistry`, `RecruiterCSVExtractor`, `ResumePDFExtractor`.
  * **Interaction:** Ingests raw inputs and returns `RawCandidateData` payloads to the `PipelineOrchestrator`.

* **`src/normalizers/`**
  * **Purpose:** Standardizes raw field values.
  * **Responsibility:** Packages normalization logic for phone numbers, dates, skills, names, countries, URLs, and emails.
  * **Important Classes:** `NormalizationResult`, `SkillNormalizer`.
  * **Interaction:** Invoked by the `MergeEngine` during the normalization phase.

* **`src/merger/`**
  * **Purpose:** Resolves and combines multi-source records.
  * **Responsibility:** Handles conflict decisions and aggregates confidence scores.
  * **Important Classes:** `MergeEngine`, `ConflictResolver`, `ConfidenceEngine`, `ConflictDecision`, `ValueCandidate`, `MergeResult`.
  * **Interaction:** Consumes `RawCandidateData` inputs and produces a `CanonicalCandidate` profile.

* **`src/projection/`**
  * **Purpose:** Configures and formats outputs.
  * **Responsibility:** Renames fields, hides metadata, and filters attributes based on configuration rules.
  * **Important Classes:** `ProjectionEngine`, `ProjectionConfig`, `FieldConfig`.
  * **Interaction:** Ingests the final `CanonicalCandidate` and yields a plain Python dictionary.

* **`src/validators/`**
  * **Purpose:** Enforces data quality schemas on projected outputs.
  * **Responsibility:** Evaluates output dictionaries and generates structural error logs.
  * **Important Classes:** `ValidationError`, `ValidationResult`.
  * **Interaction:** Run by the `PipelineOrchestrator` before writing final outputs to disk.

* **`src/utils/`**
  * **Purpose:** Utility helpers.
  * **Responsibility:** Houses ID generators, logger setups, and HTML template renderers.
  * **Important Classes:** None (module-level functions like `configure_logging`, `generate_candidate_id`, `render_html_report`).
  * **Interaction:** Imported across all layers of the application.

---

# Pipeline

The `PipelineOrchestrator` (`src/services/pipeline.py`) coordinates the execution flow from raw inputs to finalized outputs. The pipeline executes sequentially through seven stages:

```
[Input Files] ──► 1. Extract ──► 2. Normalize ──► 3. Merge ──► 4. Project ──► 5. Validate ──► 6. Write Outputs
```

### Stage 1: Source Detection & Extraction
* **Input:** `PipelineInput` containing `csv_path` and `resume_path`.
* **Output:** A list of `RawCandidateData` objects (representing parsed source envelopes) and a list of string warning messages.
* **Responsibilities:**
  * Iterates over the configured file paths and instantiates the matching extractor for each known source type (`RECRUITER_CSV` or `RESUME_PDF`).
  * Calls `.extract(path)` on each plugin to retrieve candidates, extracting the primary record (index `0`) from each file.
  * Collects warnings when a file is missing, empty, or parsing fails, while continuing with any remaining sources.
* **Important Methods:** `PipelineOrchestrator._extract_all`.
* **Error Handling:** Catches broad exceptions raised by individual extractors, logs them, and appends them to warnings to allow the pipeline to run on remaining files.

### Stage 2: Normalization
* **Input:** A list of `RawCandidateData` structures.
* **Output:** A list of `_NormalizedSource` objects containing standardized values wrapped in `NormalizationResult` envelopes.
* **Responsibilities:**
  * For each raw source, maps raw properties using specialized normalizer functions.
  * Populates fields such as `full_name`, `emails`, `phones`, `location`, `links`, and `skills` with their respective `NormalizationResult` mappings.
* **Important Methods:** `MergeEngine._normalize_source`.

### Stage 3: Merge & Conflict Resolution
* **Input:** Sorted list of `_NormalizedSource` structures (highest-priority source first).
* **Output:** A single candidate profile containing merged values, along with a collection of `ConflictDecision` objects.
* **Responsibilities:**
  * Evaluates each single-valued field (`full_name`, `headline`, `years_experience`, and `location`) across all sources.
  * Passes candidates to the `ConflictResolver` to elect a deterministic winner and discard alternatives.
  * Dedupes list fields (emails, phones, skills, links) using union and canonical comparisons.
  * Computes `years_experience` from employment-date ranges when experience entries are available, using the summary-based extraction as a fallback and attaching warnings if the two signals disagree.
* **Important Methods:** `MergeEngine.merge`, `MergeEngine._merge_scalar`, `ConflictResolver.resolve`, `MergeEngine._derive_years_experience_from_experience`.

### Stage 4: Confidence Score Generation
* **Input:** Values chosen for each field, the winning source, normalization factors, and corroborating source counts.
* **Output:** A dict of `FieldConfidence` models mapping canonical field names to structured scores, and a float `overall_confidence`.
* **Responsibilities:**
  * Runs the confidence engine on each merged property to compute a decomposed score.
  * Aggregates these scores into a weighted average for the overall score, weighting high-importance fields (like email and name) more heavily.
* **Important Methods:** `ConfidenceEngine.compute`, `ConfidenceEngine.compute_overall`.

### Stage 5: Output Projection
* **Input:** `CanonicalCandidate` and a `ProjectionConfig`.
* **Output:** A JSON-serializable dictionary.
* **Responsibilities:**
  * Iterates over the canonical fields mapped in `_FIELD_EXTRACTORS`.
  * Drops excluded keys and applies renaming schemas.
  * Enforces the `missing_value_policy` when a field is empty (inserts `null`, omits the key, or raises a `ValueError`).
  * Conditionally appends `_confidence` and `_provenance` blocks.
* **Important Methods:** `ProjectionEngine.project`.

### Stage 6: Validation
* **Input:** The projected output dictionary.
* **Output:** A `ValidationResult` containing error logs.
* **Responsibilities:**
  * Verifies type constraints and formatting rules (like UUID formats and E.164 numbers).
  * Records validation errors and warnings without raising exceptions.
* **Important Methods:** `validate_output`.

### Stage 7: Output Generation (Atomic Write-then-Replace)
* **Input:** Directory path, projected candidate dict, explanations, metrics, conflict decisions, and the original candidate.
* **Output:** A dictionary mapping file identifiers to written file paths.
* **Responsibilities:**
  * Serializes outputs to `.tmp` files.
  * Atomically replaces target destination files on disk using `replace()`.
  * Renders `report.html` using a template format and writes it to disk.
* **Important Methods:** `PipelineOrchestrator._write_outputs` and its inner helper `_write`.

---

# Canonical Candidate Model

The `CanonicalCandidate` (`src/models/candidate.py`) is the core immutable domain model representing a unified candidate profile. Once created by the `MergeEngine`, it is frozen (`frozen=True`) to prevent side-effects in downstream processing modules.

### Schema Fields

| Field Name | Type | Normalization Rule | Required/Optional | Description |
|---|---|---|---|---|
| `candidate_id` | `str` | UUID5 derived from primary email; falls back to UUID4. | **Required** | The candidate's unique identifier. |
| `full_name` | `str \| None` | Cased to proper title-case. | Optional | Standardized candidate name. |
| `emails` | `list[str]` | Lowercase, stripped, and deduplicated. | **Required** (Defaults to `[]`) | List of contact email addresses. |
| `phones` | `list[str]` | Formatted to E.164 standard. | **Required** (Defaults to `[]`) | List of contact phone numbers. |
| `location` | `Location \| None` | Country resolved to ISO-2; city title-cased. | Optional | Standardized location properties. |
| `links` | `list[Link]` | Standardized URLs with scheme prefixes. | **Required** (Defaults to `[]`) | Professional links (LinkedIn, GitHub, etc.). |
| `headline` | `str \| None` | Stripped leading/trailing whitespace. | Optional | Job title or current role summary. |
| `years_experience` | `float \| None` | Extracted numeric values cased to float. | Optional | Total years of professional experience. |
| `skills` | `list[SkillEntry]` | Synonyms mapped to canonical terms. | **Required** (Defaults to `[]`) | Deduplicated list of candidate skills. |
| `experience` | `list[ExperienceEntry]` | Parsed timelines sorted reverse-chronologically. | **Required** (Defaults to `[]`) | Employment history records. |
| `education` | `list[EducationEntry]` | Institution name mapped; dates formatted to YYYY-MM. | **Required** (Defaults to `[]`) | Academic history records. |
| `provenance` | `dict[str, list[ProvenanceRecord]]` | Populated progressively by the Merge Engine. | **Required** (Defaults to `{}`) | Field audit logs. |
| `confidence` | `dict[str, FieldConfidence]` | Decomposed scores calculated per field. | **Required** (Defaults to `{}`) | Score breakdown logs. |
| `overall_confidence` | `float` | Weighted average of active field scores. | **Required** (Defaults to `0.0`) | Overall confidence score. |
| `warnings` | `list[str]` | Accumulated execution warnings. | **Required** (Defaults to `[]`) | Pipeline warnings list. |
| `pipeline_version` | `str` | Hardcoded constant (`"1.0.0"`). | **Required** | Version tag. |
| `created_at` | `datetime` | Timezone-aware UTC timestamp. | **Required** | Timestamp of creation. |

### Rationale
Constructing a unified candidate profile on top of loose data formats requires a strict boundary. The `CanonicalCandidate` acts as this interface boundary. By consolidating all parsing and merge operations into this single domain model, downstream consumer interfaces (like the CLI, JSON outputters, and Streamlit components) can rely on a consistent schema, eliminating the need to handle messy input formats directly.

---

# Input Sources

```
[Raw Input File]
       │
       ▼
Registry.detect() (Uses file extension signatures)
       │
       ├─► .csv  ──► RecruiterCSVExtractor  ──► [csv.DictReader]  ──► list[RawCandidateData]
       └─► .pdf  ──► ResumePDFExtractor     ──► [PyMuPDF (fitz)] ──► list[RawCandidateData]
```

### 1. Recruiter CSV
* **Detection:** Identifies files ending with a `.csv` extension.
* **Parsing:** Reads contents using Python’s built-in `csv.DictReader`. It standardizes incoming stream headers using lowercased aliases to handle naming variants.
* **Extraction:** Ingests string cell values, maps them to `RawCandidateData` properties, and splits multi-value skill columns using comma, semicolon, or pipe separators.
* **Errors:** If a row contains corrupt format fields, it skips that row and continues processing the remainder of the file.

### 2. Resume PDF
* **Detection:** Identifies files ending with a `.pdf` extension.
* **Parsing:** Opens the file using `fitz.open()` (PyMuPDF) and extracts text page-by-page.
* **Extraction:** Applies regular expressions to parse emails, URLs, and phone numbers. It segments the text into functional areas (like experience or skills) by matching common header strings.
* **Errors:** On page-level read errors, the extractor logs a warning, skips the page, and extracts text from the remaining pages.

---

# Extraction Engine

The system uses a **Plugin Registry** model to manage extractions. This design allows adding new source formats without modifying the core orchestrator code.

```
                    ┌─────────────────┐
                    │  BaseExtractor  │
                    └────────┬────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────┐
│                   ExtractorRegistry                    │
├────────────────────────────────────────────────────────┤
│ _registry: dict[SourceType, type[BaseExtractor]]       │
│                                                        │
│ + register(extractor_class)                            │
│ + detect(source_path) -> BaseExtractor                  │
│ + instantiate(source_type) -> BaseExtractor            │
└────────────────────────┬───────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────┐
│ RecruiterCSVExtractor │         │  ResumePDFExtractor   │
└───────────────────────┘         └───────────────────────┘
```

### Core Components
* **`BaseExtractor` (`src/extractors/base.py`):** An abstract base class that concrete extractors subclass. It defines:
  * `source_type` (a `SourceType` enum value).
  * `extract(source_path)`: Returns a list of `RawCandidateData`.
  * `can_handle(source_path)`: Auto-detects if the extractor can handle the file format.
* **`ExtractorRegistry` (`src/extractors/registry.py`):** A class-level registry mapping `SourceType` enums to concrete extractor classes.
  * Classes register themselves using the `@ExtractorRegistry.register` decorator at import time.
  * Wires imports in `src/extractors/__init__.py` to trigger registration during boot.
* **`RawCandidateData` (`src/models/raw.py`):** The output model returned by all extractors. It uses `extra="allow"` to allow extractors to store source-specific metadata without modifying the core model schema.

---

# Normalization Engine

Before merging, field values are standardized by dedicated normalization modules to ensure consistent data formats.

```
[Raw Candidate Data] ──► Normalizers ──► [NormalizationResult]
```

Every normalizer returns a `NormalizationResult` envelope (`src/normalizers/result.py`). This dataclass encapsulates the normalized value, a success flag, a confidence multiplier (`factor` in `[0, 1]`), the name of the method used, and any warnings.

```
@dataclass(frozen=True)
class NormalizationResult:
    value: Any
    success: bool
    factor: float          # 0.0 - 1.0 (normalization quality score)
    method: str
    original: Any
    warning: str | None = None
```

### Field Normalizer Details

| Normalizer | Input | Output Format | Algorithm & Logic | Libraries Used | Output Factor |
|---|---|---|---|---|---|
| **Name** | Raw cased strings. | Proper title-case. | Splits on whitespace/hyphens. Retains lowercase for particles (e.g. *van der*) unless last. Applies custom title casing for prefixes (e.g. *McDonald*, *O'Brien*). | Standard Library (`re`) | `1.0` if cased correctly; `0.90` if normalized. |
| **Email** | Raw email strings. | Lowercase format. | Strips whitespace, converts to lowercase, and validates against a regex pattern. Checks that only one `@` is present. | Standard Library (`re`) | `1.0` if valid; `0.50` if format is invalid; `0.30` if multiple `@`. |
| **Phone** | Raw numbers. | E.164 format (e.g., `+919876543210`). | Parses numbers using fallback configurations. Runs sequentially: (1) explicit country code, (2) configured default country, (3) common country list. | `phonenumbers` | `1.0` (explicit); `0.85` (default region); `0.70` (fallback region); `0.30` (unparseable). |
| **Date** | Fuzzy date strings. | YYYY-MM format. | Translates ongoing strings (e.g., "Present", "ongoing") to `None`. Maps single years to January (e.g. `"2021" -> "2021-01"`). Parses date components using a default fallback reference. | `python-dateutil` | `1.0` if parsed; `0.70` (year-only); `0.30` (unparseable fallback). |
| **Country** | Location strings. | ISO 3166-1 Alpha-2. | Runs checks sequentially: (1) direct Alpha-2 check, (2) Alpha-3 resolution, (3) exact name matching, (4) alias lookup, (5) city inference, (6) fuzzy matching. | `pycountry`, `rapidfuzz` | `1.0` (direct match); `0.90` (split); `0.75` (city inference); `0.65` (fuzzy). |
| **URL** | Web URLs. | Standardized HTTPS link. | Strips whitespace, appends `https://` if missing, lowercases domains, removes trailing slashes, and infers platform types. | `urllib.parse` | `1.0` if prefix was present; `0.90` if scheme was added; `0.30` if parsing failed. |
| **Skills** | Unstructured skill text. | Canonical name. | Compares lowercased strings against the synonym dictionary. If no exact match is found, fuzzy-matches aliases using WRatio. | `rapidfuzz` | `1.0` (exact match); `0.85-0.95` (fuzzy scale); `0.60` (unknown fallback). |

---

# Merge Engine

The `MergeEngine` (`src/merger/engine.py`) consolidates candidate data from different sources into a single profile. The merge pipeline executes in two passes:

```
[RawCandidateData] ──► Pass 1: Normalize ──► Pass 2: Merge & Resolve ──► CanonicalCandidate
```

* **Pass 1 (Normalization):** Standardizes raw properties using normalizer functions.
* **Pass 2 (Sort & Merge):** Sorts normalized sources by priority (`SOURCE_PRIORITY`) to ensure deterministic processing. Single-valued fields are resolved using the `ConflictResolver`, while lists and nested structures are combined and deduplicated.

### Deterministic Conflict Resolution
When single-valued fields contain different values across sources, the system resolves them deterministically based on source priority:

```
Source Type:       MANUAL ──► RECRUITER_CSV ──► RESUME_PDF ──► RECRUITER_NOTES ──► ATS_JSON ──► LINKEDIN ──► GITHUB
Priority Value:      0            1             2                 3             4          5          6
(Lower value = Higher priority)
```

The source priorities are defined in `SOURCE_PRIORITY` (`src/config/source_priority.py`). Manual corrections always take precedence (priority `0`), followed by recruiter-curated data (priority `1`), and self-reported resume text (priority `2`).

```python
# Deterministic sort in ConflictResolver
sorted_candidates = sorted(valid, key=lambda c: (c.priority, c.source.value))
winner = sorted_candidates[0]
```

### List Merge and Deduplication Rules
* **Emails & Phones:** Combined using a union, converted to lowercase, cased to E.164, and deduplicated.
* **Skills:** Combined using a union, resolved to canonical names, and deduplicated.
* **Links:** Combined using a union, standardizing URLs by removing trailing slashes and comparing strings case-insensitively.
* **Experience & Education:** Deduplicated by comparing key identifiers. Experience entries are matched using lowercase company and title keys, while education entries match on institution and degree. Timelines are sorted reverse-chronologically.

---

# Confidence Engine

The `ConfidenceEngine` (`src/merger/confidence.py`) calculates confidence scores at both the field level and the candidate level. These scores are designed to be transparent and auditable.

```
Field Confidence = Source Reliability × Normalization Factor × Corroboration Bonus
```

* **Source Reliability:** The baseline accuracy of the source, defined in `SOURCE_RELIABILITY` (e.g. `RECRUITER_CSV` = `1.00`, `RESUME_PDF` = `0.85`).
* **Normalization Factor:** The normalization quality score returned by the normalizer (e.g., exact matches score `1.00`, fallback/city inferences score `0.75`, unparseable values score `0.30`).
* **Corroboration Bonus:** A multiplier applied when multiple sources agree on a value. The bonus increases by a configured increment (`corroboration_bonus_per_source` = `0.05`) for each additional agreeing source, up to a defined cap (`corroboration_bonus_cap` = `1.2`).

```python
bonus = 1.0 + max(0, agreed_sources - 1) * per_source_bonus
```

### Overall Confidence Score
The overall candidate confidence score is a weighted average of the active field confidence scores. Fields with higher semantic importance (like name and email) are weighted more heavily:

| Field Name | Importance Weight |
|---|---|
| `full_name`, `emails` | **1.5** |
| `phones`, `skills`, `experience` | **1.2** |
| `location`, `years_experience`, `education` | **1.0** |
| `headline`, `links` | **0.8** |

Fields with a confidence score of `0.0` (indicating the field is absent in all sources) are excluded from the average calculation so they do not drag down the candidate's score.

---

# Provenance

The system tracks the full history of every field value, documenting its origin, extraction method, and timestamp.

```
                          ┌─────────────────────┐
                          │  ProvenanceRecord   │
                          ├─────────────────────┤
                          │ field: str          │
                          │ value: Any          │
                          │ source: SourceType  │
                          │ method: str         │
                          │ confidence: float   │
                          │ timestamp: datetime │
                          │ notes: str | None   │
                          └─────────────────────┘
```

### Storage and Display
* **Storage:** Provenance records are stored in the candidate model's `provenance` dictionary, mapping canonical field names to a chronological list of `ProvenanceRecord` objects.
* **Display:** 
  * The raw history is exported in the `_provenance` block of `candidate.json` (when enabled in projection settings).
  * The Streamlit UI displays the audit history under the **Explanations** tab, rendering timelines and discarded values for each field.

---

# Explainability

The system provides detailed explanations for all values, conflict resolutions, and confidence scores.

* **Decision Logs:** Chronological logs of every conflict resolution event, exported to `decision_log.json`. These logs record the field name, winning value, winner's priority, and details about the discarded alternatives.
* **Rejected Alternatives:** Discorded candidate values are tracked and structured inside `explanation.json`, showing the value, source, and confidence score of each rejected alternative.
* **Merge Explanations:** The system generates human-readable explanations explaining why a value was selected (e.g. *"...All 2 sources agree on this value... Chose from highest-priority source..."*).
* **Pipeline Warnings:** Any non-fatal issues (like unparseable dates or unknown skills) are captured and logged. These warnings are displayed in the warnings section of the output files and UI.

---

# Projection Engine

The `ProjectionEngine` (`src/projection/engine.py`) formats the immutable `CanonicalCandidate` model into a JSON-serializable dictionary based on configuration settings.

```
                        ┌───────────────────┐
                        │ ProjectionConfig  │
                        └─────────┬─────────┘
                                  │
                                  ▼
┌────────────────────┐  ┌───────────────────┐  ┌────────────────────┐
│ CanonicalCandidate ├──►  ProjectionEngine ├──►  JSON Output Dict  │
└────────────────────┘  └───────────────────┘  └────────────────────┘
```

### Configuration Format (`config.json`)
The output format is controlled by a JSON configuration file:
```json
{
  "fields": {
    "full_name": { "include": true, "rename": "name" },
    "years_experience": { "include": true, "rename": "experience_years" },
    "pipeline_version": { "include": false }
  },
  "include_confidence": true,
  "include_provenance": false,
  "missing_value_policy": "null"
}
```

### Missing Value Policies
Controls the output behavior when a selected field is empty or `None`:
* **`null`:** Includes the field key with a value of `null` (default).
* **`omit`:** Excludes the field key entirely from the output dictionary.
* **`error`:** Raises a `ValueError` during projection, which is caught and logged by the orchestrator.

---

# Validation

Before output files are written, the projected candidate dictionary is validated against the output schema (`src/validators/output.py`) to catch structural anomalies or invalid formats.

```
[Projected Output Dict] ──► validate_output() ──► [ValidationResult]
```

### Validation Checks
* **Types:** Verifies that fields match their expected structures (e.g. `emails` is a list, `years_experience` is numeric).
* **Formats:** Checks format constraints, validating phone numbers against E.164 rules (`^\+[1-9]\d{6,14}$`) and identifiers against UUID specifications.
* **Ranges:** Asserts that confidence scores lie within the range `[0.0, 1.0]`.
* **Sub-schemas:** Evaluates sub-records, checking that locations contain valid two-letter ISO country codes.

Validation runs do not raise exceptions; instead, they return a `ValidationResult` containing all errors and warnings. If any errors are found, the pipeline exits with a non-zero exit code.

---

# Metrics

The orchestrator compiles run statistics into a `metrics.json` file. The tracked metrics include:

| Metric Key | Data Type | Description |
|---|---|---|
| `records_processed` | `int` | Number of input files successfully parsed. |
| `sources_used` | `list[str]` | List of source identifiers (e.g., `["recruiter_csv", "resume_pdf"]`). |
| `conflicts_resolved` | `int` | Number of fields where conflicting source values were resolved. |
| `duplicates_removed` | `int` | Total number of duplicate values dropped during merging. |
| `normalized_skills` | `int` | Count of skills successfully matched to the canonical dictionary. |
| `invalid_fields` | `int` | Number of error-severity validation failures found. |
| `warning_count` | `int` | Total number of non-fatal warnings generated during execution. |
| `execution_time_seconds` | `float` | Pipeline execution time in seconds. |
| `overall_confidence` | `float` | Candidate confidence score, rounded to 4 decimal places. |
| `validation_summary` | `str` | Text summary of the validation pass (e.g., `[VALID] 0 error(s)`). |

---

# Output Files

The pipeline writes five output files to the target directory:

```
outputs/
├── candidate.json      # Final candidate profile
├── explanation.json    # Audit trail and decisions for each field
├── decision_log.json   # Chronological log of conflict decisions
├── metrics.json        # Performance metrics and run statistics
└── report.html         # Interactive visual dashboard
```

* **`candidate.json`:** The cased, normalized candidate profile shaped by the projection configuration.
* **`explanation.json`:** Explanations for each cased value, showing the winning source, corroboration count, and any discarded alternatives.
* **`decision_log.json`:** A timestamped audit trail of conflict decisions, recording the fields, winners, losers, and resolution reasons.
* **`metrics.json`:** Run statistics, validation summaries, execution times, and warnings.
* **`report.html`:** A self-contained visual dashboard. It features progress bars for confidence scores, interactive accordions for explanations, and a formatted resume timeline.

---

# Streamlit UI

The Streamlit interface (`app.py`) provides a web-based UI for uploading documents and visualizing pipeline results.

### UI Features
* **Sidebar:** File uploader widgets for CSV files, PDF resumes, and projection configurations, along with a run button.
* **Header Metrics:** Displays summary cards for overall confidence, skill counts, and warnings.
* **Tabs:**
  * **Profile:** General contact information, cased name, and a visual confidence progress bar.
  * **Skills:** Grid of canonical skill chips.
  * **Experience:** Formatted work history timeline.
  * **Education:** List of academic records.
  * **Metrics:** Detailed pipeline execution metrics.
  * **Explanations:** Interactive accordions showing conflict resolutions and confidence breakdowns.
  * **Raw JSON:** Expandable view of the raw candidate output.
  * **Downloads:** One-click download buttons for each of the five output files.

---

# CLI

The CLI entry point (`main.py`) handles argument parsing and executes the pipeline in terminal environments.

```
python main.py --csv <path> --resume <path> [--config <path>] [--output-dir <path>] [--log-level <level>] [--quiet]
```

### Parameters
* `--csv PATH`: Path to the recruiter CSV file.
* `--resume PATH`: Path to the candidate resume PDF.
* `--config PATH`: Path to the projection configuration JSON.
* `--output-dir DIR`: Output directory path (defaults to `outputs/`).
* `--log-level LEVEL`: Log level verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
* `--quiet`: Suppresses stdout prints and displays only progress bars.
* `--version`: Prints version information and exits.

---

# Logging

The system configures logging via `logging_config.py` to ensure consistent formatting and levels across all modules:

* **Format:** `YYYY-MM-DDTHH:MM:SS | LEVEL | module_name | log_message`.
* **Handlers:** Logs to stdout by default. The CLI entry point can modify the level or suppress stdout using the `--quiet` flag.
* **Events:** Key execution events are logged at the following levels:
  * **`INFO`:** Startup flags, extraction results, merge summaries, and completion metrics.
  * **`WARNING`:** Empty files, failed line parsing, normalization fallbacks, and validation warnings.
  * **`DEBUG`:** Registry lookups, resolved column mappings, and parsed lines.

---

# Configuration

Runtime settings are managed by the `Settings` class (`src/config/settings.py`):

* **`default_country` (`"IN"`):** Country code used as a fallback for phone parsing when no country code is detected.
* **`pdf_max_pages` (`20`):** Maximum pages scanned from a resume PDF to prevent processing excessively large files.
* **`skill_fuzzy_threshold` (`82.0`):** Minimum similarity score (0-100) required to match a skill to a canonical name.
* **`corroboration_bonus_per_source` (`0.05`):** Multiplier added for each corroborating source.
* **`corroboration_bonus_cap` (`1.2`):** Maximum corroboration multiplier cap.
* **`pipeline_version` (`"1.0.0"`):** Semver pipeline version tag.

---

# Error Handling

The pipeline implements graceful degradation strategies to handle failures without crashing:

```
[Error Occurs]
      │
      ├─► Critical (No files, invalid paths)  ──► Raise ValueError  ──► Exit 1/2
      └─► Non-Critical (Bad row, page error) ──► Log Warning/Skip   ──► Continue Execution
```

* **Missing Inputs:** If no input files are provided or path arguments do not exist, the CLI raises a `ValueError` and exits immediately.
* **Extraction Failures:** If an extractor fails to parse a file, it logs a warning, skips the file, and attempts to run the pipeline on the remaining files.
* **Row Parsing Failures:** If a CSV row contains formatting errors, it skips that row and continues processing the rest of the file.
* **Normalization Failures:** If a value cannot be normalized (e.g. an invalid phone number), the system retains the original value, assigns a low confidence factor, and logs a warning.

---

# Security

The pipeline implements security controls to validate inputs and prevent common vulnerabilities:

* **Path Traversal Prevention:** The Streamlit uploader sanitizes browser-supplied filenames using `Path(file.name).name` before writing them to the temporary directory. This strips any path traversal sequences (like `../`).
* **Page Limit Controls:** The PDF parser enforces the `pdf_max_pages` limit (default: 20 pages) to prevent resource exhaustion attacks from abnormally large files.
* **Format Checking:** Pydantic models validate data ranges (e.g., confidence scores in `[0.0, 1.0]`, GPA values in `[0.0, 10.0]`) to block out-of-bounds inputs.
* **Safe Parsing:** The CSV reader uses python's standard `csv.DictReader` to safely parse quoted fields and handle embedded newlines without code execution risks.

---

# Performance

The system is optimized for fast, single-candidate runs:

* **Time Complexity:**
  * **Extraction:** PDF parsing scales linearly with page count ($O(P)$). CSV parsing scales with row count ($O(R)$).
  * **Normalization:** Skills normalization uses a two-stage lookup. It runs a fast $O(1)$ exact match against the synonym dictionary first, only falling back to fuzzy matching ($O(S \times A)$ where $S$ is skills and $A$ is aliases) if the exact match fails.
* **Memory Footprint:** The pipeline processes data in memory. The Streamlit uploader writes files to a temporary directory to keep memory utilization low.
* **PDF Heuristics:** PyMuPDF extracts text directly from the PDF DOM. The extractor does not run OCR (Optical Character Recognition), meaning scanned image-based PDFs yield no text.

---

# Testing

The test suite contains **130 tests** organized into four functional test modules:

```
tests/
├── test_normalizers.py  # 53 tests (date, email, phone, name, URL, etc.)
├── test_extractors.py   # 17 tests (CSV columns, PDF text, registry)
├── test_merger.py       # 28 tests (conflicts, confidence calculations)
└── test_projection.py   # 32 tests (rename policies, outputs, validation)
```

* **`test_normalizers.py`:** Parses values using parametrized cases to verify formatting rules, title-casing edge cases, and fuzzy country resolution.
* **`test_extractors.py`:** Validates CSV column alias mappings, registry lookups, and page extraction limits.
* **`test_merger.py`:** Tests deterministic conflict resolutions, priorities, list deduplication, and confidence computations.
* **`test_projection.py`:** Verifies projection configuration loading, field renaming, missing value policies, and schema validation.

---

# Engineering Decisions

### 1. Plugin Registry Architecture
* **Decision:** Implement a self-registering plugin pattern (`ExtractorRegistry`) for extractors.
* **Reason:** Decouples file formatting logic from the pipeline runner.
* **Trade-off:** Requires importing extractor modules inside the registry folder to trigger registration.

### 2. Immutable Canonical Model
* **Decision:** Define the `CanonicalCandidate` model using Pydantic's `frozen=True` configuration.
* **Reason:** Ensures data integrity by blocking downstream modules from altering the candidate profile.
* **Trade-off:** Requires creating a separate mapping configuration (`ProjectionConfig`) to handle output formatting and field renaming.

### 3. Separation of Normalization and Merging
* **Decision:** Split candidate processing into distinct normalization and merging phases.
* **Reason:** Simplifies testing. Normalizers can be tested as pure functions, while the merge engine can be evaluated using standardized inputs.
* **Trade-off:** Requires an intermediate data structures (`_NormalizedSource`) to pass data between phases.

### 4. Rule-Based Regex Parser for PDFs
* **Decision:** Use a rule-based regex parser with section heading heuristics instead of an LLM or OCR.
* **Reason:** Ensures fast, predictable execution times (under 0.5s) without external dependencies or API costs.
* **Trade-off:** Fails to parse scanned-image PDFs and can miss sections if a resume uses highly non-standard headings.

---

# Supported Edge Cases

* **Hyphenated & Prefixed Names:** The name normalizer correctly title-cases names with hyphens (e.g. `anne-marie` → `Anne-Marie`) or prefixes (e.g. `mcdonald` → `McDonald`, `o'brien` → `O'Brien`).
* **BOM-Prefixed CSV Files:** The CSV reader falls back to `utf-8-sig` encoding to strip Byte Order Marks (BOM), and falls back to `latin-1` if decoding fails.
* **Fuzzy Skill Aliases:** The skill normalizer matches common abbreviations and variants (e.g., `pyspark` or `apache spark` match to the canonical `Spark` skill).
* **Location Parsing from Cities:** If a location string contains only a city name (e.g., `Bangalore`), the country normalizer infers the country code (`IN`) using the tech-hub lookup table.
* **Missing Dates in Timelines:** Ongoing roles (e.g. "Present", "ongoing") are resolved to `None` and sorted to the top of chronological work histories.

---

# Known Limitations

* **No OCR Support:** The PDF extractor relies on text extraction. Scanned PDFs or resumes saved as images yield no text.
* **Heuristic Name Extraction:** The PDF parser assumes the candidate's name is the first substantive line in the document header. This can produce incorrect results if the header contains logos, addresses, or metadata before the name.
* **Section-Heading Heuristics:** The resume segments text by matching common section titles. It can fail to parse sections if a resume uses non-standard headings (e.g., "Where I've Been" instead of "Experience").
* **Single Candidate Limitation:** The pipeline processes the first candidate record found in each source file. It does not support batch importing multi-candidate CSVs.

---

# Assignment Mapping

| Requirement | Implementation | Status | Evidence |
|---|---|---|---|
| Ingest multiple formats | Extractor registry with CSV and PDF extractors. | **Completed** | `src/extractors/registry.py` |
| Field Normalization | 7 normalizers in `src/normalizers/`. | **Completed** | `src/normalizers/` |
| Deterministic Merge | Conflict resolver using priority settings. | **Completed** | `src/merger/conflict.py` |
| Explainable Confidence | Decomposed confidence engine formula. | **Completed** | `src/merger/confidence.py` |
| Full Audit Provenance | Tracking source file, method, and timestamps. | **Completed** | `src/models/provenance.py` |
| Output Generation | Writing JSON and HTML report files. | **Completed** | `src/services/pipeline.py` |
| Streamlit Interface | Web application showing profile tabs and downloads. | **Completed** | `app.py` |
| Command Line Tool | CLI flags with validation checks. | **Completed** | `main.py`, `src/cli/args.py` |

---

# Future Extensibility

* **Adding Extractors:** Create a new class in `src/extractors/` inheriting from `BaseExtractor`, apply the `@ExtractorRegistry.register` decorator, add the source enum value to `SourceType`, and import the file in `__init__.py`.
* **Adding Normalizers:** Add a new normalizer function returning `NormalizationResult` in `src/normalizers/` and call it from `MergeEngine._normalize_source()`.
* **Adding Merge Rules:** Define a custom merge function in `MergeEngine` and add the field key to the processing loop in `MergeEngine.merge()`.

---

# Summary

The Multi-Source Candidate Data Transformer is a production-ready ETL pipeline built on clean architecture principles. 

```
[Raw Ingestion] ──► [Decoupled Normalizers] ──► [Deterministic Merger] ──► [Pydantic Output Validation]
```

By separating file parsing, field normalization, and schema validation into independent layers, the codebase remains highly maintainable. The use of immutable Pydantic models ensures data integrity across stages, while rule-based normalizers deliver fast, predictable execution times. The resulting candidate profile is output alongside full audit trails and confidence scores, providing a transparent, extensible data integration solution.
