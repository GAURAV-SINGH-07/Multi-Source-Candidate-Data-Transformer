"""
MergeEngine — orchestrates the full multi-source merge pipeline.

Responsibilities:
    1. Accept a list of RawCandidateData (one per source).
    2. Normalize each source's fields using the normalizer functions.
    3. Merge scalar fields via ConflictResolver (priority-based).
    4. Merge list fields (emails, phones, skills, links) via union + dedup.
    5. Compute per-field FieldConfidence via ConfidenceEngine.
    6. Build ProvenanceRecords for every field.
    7. Construct the immutable CanonicalCandidate.
    8. Return a MergeResult with the candidate + audit artifacts.

The engine is stateless between runs — instantiate once and call merge()
as many times as needed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.config.source_priority import get_priority, get_reliability
from src.models.candidate import CanonicalCandidate
from src.models.field_confidence import FieldConfidence
from src.models.provenance import ProvenanceRecord
from src.models.raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from src.models.source_type import SourceType
from src.models.sub_models import (
    EducationEntry,
    ExperienceEntry,
    Link,
    Location,
    SkillEntry,
)
from src.normalizers import (
    NormalizationResult,
    deduplicate_emails,
    normalize_country,
    normalize_date,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_url,
    infer_platform,
    SkillNormalizer,
)
from src.utils.id_generator import generate_candidate_id
from src.utils.logging_config import get_logger
from .conflict import ConflictDecision, ConflictResolver, ValueCandidate
from .confidence import ConfidenceEngine

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal intermediate types
# ---------------------------------------------------------------------------


@dataclass
class _NormalizedSource:
    """Fully normalized version of one RawCandidateData.

    Produced by ``MergeEngine._normalize_source()`` and consumed by the
    merge methods. Separates normalization from merge logic cleanly.
    """

    source: SourceType
    source_file: str | None
    priority: int
    reliability: float
    extracted_at: datetime

    full_name: NormalizationResult | None = None
    emails: list[NormalizationResult] = field(default_factory=list)
    phones: list[NormalizationResult] = field(default_factory=list)
    location_raw: str | None = None
    location_country: NormalizationResult | None = None
    location_city: str | None = None
    links: list[NormalizationResult] = field(default_factory=list)
    headline: NormalizationResult | None = None
    years_experience: NormalizationResult | None = None
    skills: list[NormalizationResult] = field(default_factory=list)
    experience: list[RawExperienceEntry] = field(default_factory=list)
    education: list[RawEducationEntry] = field(default_factory=list)


@dataclass
class MergeResult:
    """Output of MergeEngine.merge() — the canonical profile plus audit artifacts.

    Attributes:
        candidate:          The immutable, fully-merged CanonicalCandidate.
        conflicts:          All conflict decisions made during this merge.
        decision_log:       Structured log entries for decision_log.json.
        explanation:        Per-field human-readable explanations for explanation.json.
        warnings:           Non-fatal issues (duplicate emails, unknown skills, etc.).
        duplicates_removed: Total number of duplicate values dropped across all
                            list fields (emails, phones, skills) during the
                            union+dedup merge step. A duplicate is any raw value
                            that was identical to an already-seen value and was
                            therefore discarded rather than added to the output.
    """

    candidate: CanonicalCandidate
    conflicts: list[ConflictDecision]
    decision_log: list[dict[str, Any]]
    explanation: dict[str, dict[str, Any]]
    warnings: list[str]
    duplicates_removed: int = 0


# ---------------------------------------------------------------------------
# MergeEngine
# ---------------------------------------------------------------------------


class MergeEngine:
    """Deterministic multi-source candidate data merger.

    Args:
        conflict_resolver: Injectable ConflictResolver. Defaults to a
                           fresh default instance.
        confidence_engine: Injectable ConfidenceEngine. Defaults to a
                           fresh default instance.
        skill_normalizer:  Injectable SkillNormalizer. Defaults to the
                           module-level singleton.
    """

    def __init__(
        self,
        conflict_resolver: ConflictResolver | None = None,
        confidence_engine: ConfidenceEngine | None = None,
        skill_normalizer: SkillNormalizer | None = None,
    ) -> None:
        self._resolver = conflict_resolver or ConflictResolver()
        self._confidence = confidence_engine or ConfidenceEngine()
        self._skill_norm = skill_normalizer or SkillNormalizer()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def merge(self, sources: list[RawCandidateData]) -> MergeResult:
        """Merge *sources* into one canonical candidate profile.

        Args:
            sources: List of raw extractions from different sources.
                     May be empty (returns a minimal empty candidate).

        Returns:
            :class:`MergeResult` with the CanonicalCandidate and full
            audit trail.
        """
        if not sources:
            log.warning("MergeEngine.merge() called with empty source list")
            return self._empty_result()

        log.info("Merging %d source(s): %s", len(sources), [s.source.value for s in sources])

        # Pass 1: normalize all sources
        normalized = [self._normalize_source(raw) for raw in sources]
        # Sort by priority (ascending = highest authority first)
        normalized.sort(key=lambda ns: (ns.priority, ns.source.value))

        # Pass 2: merge each field
        conflicts: list[ConflictDecision] = []
        warnings: list[str] = []
        provenance: dict[str, list[ProvenanceRecord]] = {}
        confidences: dict[str, FieldConfidence] = {}
        decision_log: list[dict[str, Any]] = []
        explanation: dict[str, dict[str, Any]] = {}

        # ── Scalar fields ─────────────────────────────────────────────
        for field_name, getter in [
            ("full_name",        lambda ns: ns.full_name),
            ("headline",         lambda ns: ns.headline),
            ("years_experience", lambda ns: ns.years_experience),
        ]:
            merged_val, fc, prov, conflict, warn = self._merge_scalar(
                field_name, normalized, getter
            )
            provenance[field_name] = prov
            if fc:
                confidences[field_name] = fc
            if conflict:
                conflicts.append(conflict)
                decision_log.append(self._conflict_to_log(conflict))
            if warn:
                warnings.extend(warn)
            explanation[field_name] = self._build_field_explanation(
                field_name, merged_val, fc, conflict, prov
            )

        # ── Email (list field — union + dedup) ────────────────────────
        emails, email_fc, email_prov, email_dupes = self._merge_emails(normalized)
        if email_fc:
            confidences["emails"] = email_fc
        provenance["emails"] = email_prov
        explanation["emails"] = self._build_field_explanation("emails", emails, email_fc, None, email_prov)

        # ── Phone (list field — union + dedup) ────────────────────────
        phones, phone_fc, phone_prov, phone_warns, phone_dupes = self._merge_phones(normalized)
        warnings.extend(phone_warns)
        if phone_fc:
            confidences["phones"] = phone_fc
        provenance["phones"] = phone_prov
        explanation["phones"] = self._build_field_explanation("phones", phones, phone_fc, None, phone_prov)

        # ── Location (structured field) ───────────────────────────────
        location, loc_fc, loc_prov, loc_conflict = self._merge_location(normalized)
        provenance["location"] = loc_prov
        if loc_fc:
            confidences["location"] = loc_fc
        if loc_conflict:
            conflicts.append(loc_conflict)
            decision_log.append(self._conflict_to_log(loc_conflict))
        explanation["location"] = self._build_field_explanation("location", location, loc_fc, loc_conflict, loc_prov)

        # ── Links (list field — union + dedup) ────────────────────────
        links, link_prov = self._merge_links(normalized)
        provenance["links"] = link_prov

        # ── Skills (union + deduplicate by canonical name) ────────────
        skills, skill_fc, skill_prov, skill_warns, skill_dupes = self._merge_skills(normalized)
        warnings.extend(skill_warns)
        if skill_fc:
            confidences["skills"] = skill_fc
        provenance["skills"] = skill_prov
        explanation["skills"] = self._build_field_explanation("skills", skills, skill_fc, None, skill_prov)

        # ── Total duplicates removed across all list fields ────────────
        total_duplicates_removed = email_dupes + phone_dupes + skill_dupes

        # ── Experience (union + dedup by company+title) ───────────────
        experience = self._merge_experience(normalized)
        # ── Education (union + dedup by institution+degree) ───────────
        education = self._merge_education(normalized)

        # ── Resolve scalar values from merged results ─────────────────
        full_name_val = explanation["full_name"].get("chosen_value")
        headline_val = explanation["headline"].get("chosen_value")
        yoe_val = explanation["years_experience"].get("chosen_value")

        # ── Overall confidence ─────────────────────────────────────────
        overall = self._confidence.compute_overall(confidences)

        # ── Candidate ID ──────────────────────────────────────────────
        primary_email = emails[0] if emails else None
        candidate_id = generate_candidate_id(primary_email)

        # ── Build CanonicalCandidate ──────────────────────────────────
        candidate = CanonicalCandidate(
            candidate_id=candidate_id,
            full_name=full_name_val,
            emails=emails,
            phones=phones,
            location=location,
            links=links,
            headline=headline_val,
            years_experience=float(yoe_val) if yoe_val is not None else None,
            skills=skills,
            experience=experience,
            education=education,
            provenance=provenance,
            confidence=confidences,
            overall_confidence=overall,
            warnings=warnings,
        )

        log.info(
            "Merge complete: id=%s name=%r confidence=%.2f warnings=%d",
            candidate_id, full_name_val, overall, len(warnings),
        )

        return MergeResult(
            candidate=candidate,
            conflicts=conflicts,
            decision_log=decision_log,
            explanation=explanation,
            warnings=warnings,
            duplicates_removed=total_duplicates_removed,
        )

    # ------------------------------------------------------------------
    # Normalization pass
    # ------------------------------------------------------------------

    def _normalize_source(self, raw: RawCandidateData) -> _NormalizedSource:
        """Normalize all fields in *raw* and return a _NormalizedSource."""
        ns = _NormalizedSource(
            source=raw.source,
            source_file=raw.source_file,
            priority=get_priority(raw.source),
            reliability=get_reliability(raw.source),
            extracted_at=raw.extracted_at,
        )

        if raw.full_name:
            ns.full_name = normalize_name(raw.full_name)

        ns.emails = [normalize_email(e) for e in raw.emails if e]
        ns.phones = [normalize_phone(p) for p in raw.phones if p]

        for url_raw in raw.links:
            if url_raw:
                ns.links.append(normalize_url(url_raw))

        if raw.headline:
            from src.normalizers.name import normalize_name as nn
            ns.headline = NormalizationResult(
                value=raw.headline.strip(),
                success=True,
                factor=1.0,
                method="direct_string",
                original=raw.headline,
            )

        derived_yoe = self._derive_years_experience_from_experience(raw.experience)
        if derived_yoe is not None:
            warning = None
            explicit = self._coerce_years_experience(raw.years_experience)
            if explicit is not None and abs(explicit - derived_yoe) >= 2.0:
                warning = (
                    f"Summary-derived years_experience ({explicit}) conflicts "
                    f"with employment-date calculation ({derived_yoe})"
                )
            ns.years_experience = NormalizationResult(
                value=derived_yoe,
                success=True,
                factor=0.95,
                method="employment_date_calculation",
                original=raw.experience,
                warning=warning,
            )
        elif raw.years_experience is not None:
            yoe = self._coerce_years_experience(raw.years_experience)
            if yoe is not None:
                ns.years_experience = NormalizationResult(
                    value=yoe,
                    success=True,
                    factor=0.85,
                    method="summary_regex_extraction",
                    original=raw.years_experience,
                )

        if raw.location:
            ns.location_raw = raw.location
            country_result = normalize_country(raw.location)
            ns.location_country = country_result
            ns.location_city = self._extract_city(raw.location)

        ns.skills = [self._skill_norm.normalize(s) for s in raw.skills if s]
        ns.experience = raw.experience
        ns.education = raw.education

        return ns

    # ------------------------------------------------------------------
    # Scalar field merge
    # ------------------------------------------------------------------

    def _merge_scalar(
        self,
        field_name: str,
        sources: list[_NormalizedSource],
        getter,
    ) -> tuple[Any, FieldConfidence | None, list[ProvenanceRecord], ConflictDecision | None, list[str]]:
        """Merge a scalar field across all normalized sources.

        Returns:
            (value, field_confidence, provenance_records, conflict_or_none, warnings)
        """
        candidates: list[ValueCandidate] = []
        provenance: list[ProvenanceRecord] = []
        warnings: list[str] = []

        for ns in sources:
            nr: NormalizationResult | None = getter(ns)
            if nr is None or nr.value is None:
                continue
            candidates.append(ValueCandidate(
                value=nr.value,
                source=ns.source,
                norm_result=nr,
                priority=ns.priority,
            ))

        decision = self._resolver.resolve(field_name, candidates)
        if decision is None:
            return None, None, [], None, warnings

        winner = decision.winner
        provenance = [
            self._make_provenance(field_name, c.value, c.source, c.norm_result)
            for c in [winner] + decision.losers
        ]

        if winner.norm_result.warning:
            warnings.append(f"[{field_name}] {winner.norm_result.warning}")

        fc = self._confidence.compute(
            field=field_name,
            winning_source=winner.source,
            norm_result=winner.norm_result,
            agreed_sources=decision.agreed_sources,
        )

        return winner.value, fc, provenance, (decision if decision.had_conflict else None), warnings

    # ------------------------------------------------------------------
    # List field merges
    # ------------------------------------------------------------------

    def _merge_emails(
        self, sources: list[_NormalizedSource]
    ) -> tuple[list[str], FieldConfidence | None, list[ProvenanceRecord], int]:
        """Union and deduplicate emails across all sources.

        Returns:
            Tuple of (emails, field_confidence, provenance_records, duplicates_removed).
            ``duplicates_removed`` is the count of email values that were
            dropped because they were already present in the output.
        """
        seen: set[str] = set()
        result: list[str] = []
        provenance: list[ProvenanceRecord] = []
        best_nr: NormalizationResult | None = None
        best_source: SourceType | None = None
        agreed: int = 0

        for ns in sources:
            for nr in ns.emails:
                if nr.value and nr.success:
                    key = nr.value.lower()
                    if key not in seen:
                        seen.add(key)
                        result.append(nr.value)
                        if best_nr is None:
                            best_nr = nr
                            best_source = ns.source
                        provenance.append(
                            self._make_provenance("emails", nr.value, ns.source, nr)
                        )
                    else:
                        agreed += 1

        fc = None
        if best_nr and best_source:
            fc = self._confidence.compute("emails", best_source, best_nr, max(1, agreed + 1))
        return result, fc, provenance, agreed

    def _merge_phones(
        self, sources: list[_NormalizedSource]
    ) -> tuple[list[str], FieldConfidence | None, list[ProvenanceRecord], list[str], int]:
        """Union and deduplicate phones across all sources.

        Returns:
            Tuple of (phones, field_confidence, provenance_records, warnings,
            duplicates_removed). ``duplicates_removed`` is the count of phone
            values that were dropped because they were already present
            (compared digit-only to handle formatting variants).
        """
        seen: set[str] = set()
        result: list[str] = []
        provenance: list[ProvenanceRecord] = []
        warnings: list[str] = []
        best_nr: NormalizationResult | None = None
        best_source: SourceType | None = None
        agreed: int = 0

        for ns in sources:
            for nr in ns.phones:
                if nr.value:
                    key = re.sub(r"\D", "", nr.value)
                    if nr.warning:
                        warnings.append(f"[phones] {nr.warning}")
                    if nr.success and key not in seen:
                        seen.add(key)
                        result.append(nr.value)
                        if best_nr is None:
                            best_nr = nr
                            best_source = ns.source
                        provenance.append(
                            self._make_provenance("phones", nr.value, ns.source, nr)
                        )
                    elif key in seen:
                        agreed += 1

        fc = None
        if best_nr and best_source:
            fc = self._confidence.compute("phones", best_source, best_nr, max(1, agreed + 1))
        return result, fc, provenance, warnings, agreed

    def _merge_links(
        self, sources: list[_NormalizedSource]
    ) -> tuple[list[Link], list[ProvenanceRecord]]:
        """Union and deduplicate links by normalized URL."""
        seen_urls: set[str] = set()
        result: list[Link] = []
        provenance: list[ProvenanceRecord] = []

        for ns in sources:
            for nr in ns.links:
                if nr.value and nr.value not in seen_urls:
                    seen_urls.add(nr.value)
                    platform = infer_platform(nr.value)
                    result.append(Link(url=nr.value, platform=platform))
                    provenance.append(
                        self._make_provenance("links", nr.value, ns.source, nr)
                    )
        return result, provenance

    def _merge_skills(
        self, sources: list[_NormalizedSource]
    ) -> tuple[list[SkillEntry], FieldConfidence | None, list[ProvenanceRecord], list[str], int]:
        """Union and deduplicate skills by canonical name.

        Returns:
            Tuple of (skills, field_confidence, provenance_records, warnings,
            duplicates_removed). ``duplicates_removed`` is the count of skill
            values that were dropped because the same canonical name was already
            present in the output (cross-source deduplication).
        """
        seen_canonical: set[str] = set()
        result: list[SkillEntry] = []
        provenance: list[ProvenanceRecord] = []
        warnings: list[str] = []
        best_nr: NormalizationResult | None = None
        best_source: SourceType | None = None
        agreed = 0

        for ns in sources:
            for nr in ns.skills:
                if not nr.value:
                    continue
                canonical = nr.value
                if canonical not in seen_canonical:
                    seen_canonical.add(canonical)
                    result.append(SkillEntry(
                        name=canonical,
                        raw_name=nr.original or canonical,
                        category=None,
                    ))
                    if best_nr is None:
                        best_nr = nr
                        best_source = ns.source
                    provenance.append(
                        self._make_provenance("skills", canonical, ns.source, nr)
                    )
                    if nr.warning:
                        warnings.append(f"[skills] {nr.warning}")
                else:
                    agreed += 1

        fc = None
        if best_nr and best_source:
            fc = self._confidence.compute("skills", best_source, best_nr, max(1, agreed + 1))
        return result, fc, provenance, warnings, agreed

    # ------------------------------------------------------------------
    # Location merge
    # ------------------------------------------------------------------

    def _merge_location(
        self, sources: list[_NormalizedSource]
    ) -> tuple[Location | None, FieldConfidence | None, list[ProvenanceRecord], ConflictDecision | None]:
        """Merge location field — conflict on country_code."""
        candidates: list[ValueCandidate] = []
        cities: dict[str, str] = {}  # source_value → city
        provenance: list[ProvenanceRecord] = []

        for ns in sources:
            if ns.location_country and ns.location_country.value:
                candidates.append(ValueCandidate(
                    value=ns.location_country.value,
                    source=ns.source,
                    norm_result=ns.location_country,
                    priority=ns.priority,
                ))
                if ns.location_city:
                    cities[ns.location_country.value] = ns.location_city

        decision = self._resolver.resolve("location", candidates)
        if decision is None:
            return None, None, [], None

        winner = decision.winner
        provenance = [
            self._make_provenance("location", c.value, c.source, c.norm_result)
            for c in [winner] + decision.losers
        ]

        city = cities.get(winner.value)
        location = Location(
            city=city,
            country_code=winner.value,
            raw=sources[0].location_raw if sources else None,
        )

        fc = self._confidence.compute(
            "location", winner.source, winner.norm_result, decision.agreed_sources
        )

        return location, fc, provenance, (decision if decision.had_conflict else None)

    # ------------------------------------------------------------------
    # Experience and Education merges
    # ------------------------------------------------------------------

    def _merge_experience(self, sources: list[_NormalizedSource]) -> list[ExperienceEntry]:
        """Union experience entries, deduplicate by (company, title)."""
        seen: set[tuple[str | None, str | None]] = set()
        result: list[ExperienceEntry] = []

        for ns in sources:
            for raw_exp in ns.experience:
                key = (
                    (raw_exp.company or "").lower().strip() or None,
                    (raw_exp.title or "").lower().strip() or None,
                )
                if key in seen:
                    continue
                seen.add(key)
                start = normalize_date(raw_exp.start_date).value if raw_exp.start_date else None
                end = normalize_date(raw_exp.end_date).value if raw_exp.end_date else None
                try:
                    result.append(ExperienceEntry(
                        title=raw_exp.title,
                        company=raw_exp.company,
                        start_date=start if self._valid_ym(start) else None,
                        end_date=end if self._valid_ym(end) else None,
                        is_current=raw_exp.is_current,
                        description=raw_exp.description,
                        location=raw_exp.location,
                    ))
                except Exception as exc:
                    log.debug("Skipping malformed experience entry: %s", exc)
        return result

    def _merge_education(self, sources: list[_NormalizedSource]) -> list[EducationEntry]:
        """Union education entries, deduplicate by (institution, degree)."""
        seen: set[tuple[str | None, str | None]] = set()
        result: list[EducationEntry] = []

        for ns in sources:
            for raw_edu in ns.education:
                key = (
                    (raw_edu.institution or "").lower().strip() or None,
                    (raw_edu.degree or "").lower().strip() or None,
                )
                if key in seen:
                    continue
                seen.add(key)
                start = normalize_date(raw_edu.start_date).value if raw_edu.start_date else None
                end = normalize_date(raw_edu.end_date).value if raw_edu.end_date else None
                try:
                    result.append(EducationEntry(
                        institution=raw_edu.institution,
                        degree=raw_edu.degree,
                        field_of_study=raw_edu.field_of_study,
                        start_date=start if self._valid_ym(start) else None,
                        end_date=end if self._valid_ym(end) else None,
                        gpa=raw_edu.gpa,
                    ))
                except Exception as exc:
                    log.debug("Skipping malformed education entry: %s", exc)
        return result

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _make_provenance(
        field: str,
        value: Any,
        source: SourceType,
        nr: NormalizationResult,
    ) -> ProvenanceRecord:
        return ProvenanceRecord(
            field=field,
            value=value,
            source=source,
            method=nr.method,
            confidence=nr.factor,
            notes=nr.warning,
        )

    @staticmethod
    def _coerce_years_experience(raw: Any) -> float | None:
        """Coerce raw years_experience to float."""
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        match = re.search(r"[\d.]+", str(raw))
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_city(location_raw: str) -> str | None:
        """Heuristically extract city from a location string."""
        parts = [p.strip() for p in re.split(r"[,/|]", location_raw) if p.strip()]
        if parts:
            # City is typically the first part of "City, Country"
            candidate = parts[0]
            if len(candidate) < 50:
                return candidate
        return None

    @staticmethod
    def _valid_ym(value: str | None) -> bool:
        """Return True if *value* matches YYYY-MM format."""
        if not value:
            return False
        return bool(re.match(r"^\d{4}-\d{2}$", value))

    @staticmethod
    def _build_field_explanation(
        field: str,
        value: Any,
        fc: FieldConfidence | None,
        conflict: ConflictDecision | None,
        provenance: list[ProvenanceRecord] | None = None,
    ) -> dict[str, Any]:
        """Build an explanation dict entry for one field."""
        entry: dict[str, Any] = {
            "chosen_value": value,
            "confidence": round(fc.score, 4) if fc else None,
            "reason": conflict.reason if conflict else (
                fc.explanation if fc else "Field not present in any source."
            ),
            "had_conflict": bool(conflict),
        }
        if provenance:
            winner = provenance[0]
            entry["source"] = winner.source.value
            entry["method"] = winner.method
            if winner.notes:
                entry["notes"] = winner.notes
        if conflict:
            entry["alternatives"] = [
                {"source": c.source.value, "value": c.value}
                for c in conflict.losers
            ]
        return entry

    @staticmethod
    def _derive_years_experience_from_experience(experience: list[RawExperienceEntry]) -> float | None:
        """Derive years of professional experience from employment date ranges."""
        ranges: list[tuple[datetime, datetime]] = []

        for entry in experience:
            start_value = normalize_date(entry.start_date).value if entry.start_date else None
            if not start_value:
                continue
            start_dt = datetime.strptime(start_value, "%Y-%m").replace(tzinfo=timezone.utc)

            if entry.is_current or not entry.end_date:
                end_dt = datetime.now(timezone.utc)
            else:
                end_value = normalize_date(entry.end_date).value if entry.end_date else None
                if not end_value:
                    continue
                end_dt = datetime.strptime(end_value, "%Y-%m").replace(tzinfo=timezone.utc)

            if end_dt < start_dt:
                continue
            ranges.append((start_dt, end_dt))

        if not ranges:
            return None

        ranges.sort(key=lambda item: (item[0], item[1]))
        merged: list[tuple[datetime, datetime]] = []
        for start_dt, end_dt in ranges:
            if not merged:
                merged.append((start_dt, end_dt))
                continue
            last_start, last_end = merged[-1]
            if start_dt <= last_end:
                merged[-1] = (last_start, max(last_end, end_dt))
            else:
                merged.append((start_dt, end_dt))

        total_years = 0.0
        for start_dt, end_dt in merged:
            total_years += max(0.0, end_dt.year - start_dt.year)

        if total_years <= 0:
            return None

        rounded = round(total_years, 1)
        if rounded.is_integer():
            return float(int(rounded))
        return rounded

    @staticmethod
    def _conflict_to_log(conflict: ConflictDecision) -> dict[str, Any]:
        """Serialise a ConflictDecision to a log entry dict."""
        return {
            "field": conflict.field,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "had_conflict": conflict.had_conflict,
            "winner_source": conflict.winner.source.value,
            "winner_value": str(conflict.winner.value),
            "winner_priority": conflict.winner.priority,
            "agreed_sources": conflict.agreed_sources,
            "alternatives": [
                {"source": c.source.value, "value": str(c.value)}
                for c in conflict.losers
            ],
            "reason": conflict.reason,
        }

    @staticmethod
    def _empty_result() -> MergeResult:
        """Return a MergeResult with an empty candidate."""
        empty = CanonicalCandidate(
            candidate_id=generate_candidate_id(None),
            warnings=["No source data provided to MergeEngine."],
        )
        return MergeResult(
            candidate=empty, conflicts=[], decision_log=[],
            explanation={}, warnings=["No source data provided."],
        )
