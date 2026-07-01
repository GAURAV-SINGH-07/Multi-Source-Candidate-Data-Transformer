"""
RecruiterCSVExtractor — extracts candidate data from a recruiter-supplied CSV.

Handles real-world messiness:
    - Flexible column names (case-insensitive, with common aliases)
    - BOM-prefixed UTF-8 files
    - Latin-1 / cp1252 encoded files
    - Empty rows and whitespace-only values
    - Skills as comma/semicolon-separated strings in a single cell
    - years_experience as int, float, or string (e.g. "5", "5.5", "5+")
    - Quoted fields with embedded newlines (handled by csv.DictReader)
"""

import csv
import io
import logging
from pathlib import Path
from typing import IO

from src.models.raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from src.models.source_type import SourceType
from src.utils.logging_config import get_logger
from .base import BaseExtractor
from .registry import ExtractorRegistry

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column alias map
# Keys are canonical field names (matching RawCandidateData attributes).
# Values are lists of accepted CSV header variants (all lowercased).
# ---------------------------------------------------------------------------
_COLUMN_ALIASES: dict[str, list[str]] = {
    "full_name": [
        "full_name", "name", "candidate_name", "candidate name",
        "full name", "fullname",
    ],
    "email": [
        "email", "email_address", "emailaddress", "e-mail", "emails",
        "email address",
    ],
    "phone": [
        "phone", "phone_number", "phonenumber", "mobile", "mobile_number",
        "telephone", "contact", "phone number", "mobile number", "cell",
    ],
    "location": [
        "location", "city", "address", "place", "current_location",
        "current location", "city_country",
    ],
    "linkedin_url": [
        "linkedin_url", "linkedin", "linkedin_profile", "linkedin profile",
        "linkedin url", "linkedin_link",
    ],
    "headline": [
        "headline", "title", "job_title", "current_title", "current title",
        "jobtitle", "position", "role", "designation",
    ],
    "skills": [
        "skills", "skill_set", "skillset", "skill set", "technologies",
        "tech_stack", "techstack", "core_skills", "core skills",
        "key skills", "key_skills",
    ],
    "years_experience": [
        "years_experience", "years experience", "total_experience",
        "total experience", "experience", "experience_years", "exp",
        "years_of_experience", "years of experience",
    ],
}

# Build the reverse lookup: lowercased-header → canonical name
_HEADER_TO_FIELD: dict[str, str] = {
    alias: field
    for field, aliases in _COLUMN_ALIASES.items()
    for alias in aliases
}


@ExtractorRegistry.register
class RecruiterCSVExtractor(BaseExtractor):
    """Extracts candidate data from a recruiter-supplied CSV file.

    Each non-empty row is treated as one candidate record and returned as a
    :class:`~src.models.raw.RawCandidateData` instance. The pipeline
    orchestrator decides which row(s) to process.
    """

    source_type = SourceType.RECRUITER_CSV

    def can_handle(self, source: Path | str) -> bool:
        """Return True for ``.csv`` files."""
        return Path(source).suffix.lower() == ".csv"

    def extract(self, source: Path | str) -> list[RawCandidateData]:
        """Parse *source* CSV and return one RawCandidateData per candidate row.

        Args:
            source: Path to the CSV file.

        Returns:
            List of :class:`RawCandidateData` instances.

        Raises:
            FileNotFoundError: If *source* does not exist.
        """
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        log.info("Extracting CSV: %s", path.name)

        text = self._read_file(path)
        if not text.strip():
            log.warning("CSV file is empty: %s", path.name)
            return []

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            log.warning("CSV has no headers: %s", path.name)
            return []

        column_map = self._resolve_column_map(list(reader.fieldnames))
        log.debug("Resolved column map: %s", column_map)

        records: list[RawCandidateData] = []
        for row_index, row in enumerate(reader, start=2):  # Row 1 is header
            if self._is_empty_row(row):
                log.debug("Skipping empty row %d", row_index)
                continue
            try:
                record = self._parse_row(row, column_map, str(path))
                records.append(record)
                log.debug("Extracted row %d: %s", row_index, record.full_name)
            except Exception as exc:
                log.warning("Failed to parse row %d: %s", row_index, exc)

        log.info("Extracted %d record(s) from %s", len(records), path.name)
        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> str:
        """Read *path* with UTF-8-sig (handles BOM), falling back to latin-1."""
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            log.warning("UTF-8 decode failed for %s; retrying with latin-1", path.name)
            return path.read_text(encoding="latin-1")

    def _resolve_column_map(self, fieldnames: list[str]) -> dict[str, str]:
        """Map each CSV header to its canonical field name.

        Args:
            fieldnames: Raw header strings from the CSV.

        Returns:
            Dict of ``{canonical_field: actual_csv_header}``.
        """
        mapping: dict[str, str] = {}
        for header in fieldnames:
            normalized = header.strip().lower()
            canonical = _HEADER_TO_FIELD.get(normalized)
            if canonical and canonical not in mapping:
                mapping[canonical] = header
        return mapping

    def _is_empty_row(self, row: dict[str, str | None]) -> bool:
        """Return True if every cell in *row* is empty or whitespace."""
        return all(not (v and v.strip()) for v in row.values())

    def _get_cell(
        self,
        row: dict[str, str | None],
        column_map: dict[str, str],
        field: str,
    ) -> str | None:
        """Safely retrieve a cell value, returning None if absent or empty."""
        header = column_map.get(field)
        if header is None:
            return None
        raw = row.get(header, "")
        cleaned = (raw or "").strip()
        return cleaned if cleaned else None

    def _parse_skills(self, raw: str | None) -> list[str]:
        """Split a skill cell on commas or semicolons, strip whitespace."""
        if not raw:
            return []
        import re
        parts = re.split(r"[,;|]+", raw)
        return [p.strip() for p in parts if p.strip()]

    def _parse_years_experience(self, raw: str | None) -> float | None:
        """Coerce years_experience to float, ignoring non-numeric suffixes."""
        if not raw:
            return None
        import re
        match = re.search(r"[\d.]+", raw)
        if not match:
            return None
        try:
            return float(match.group())
        except ValueError:
            return None

    def _parse_row(
        self,
        row: dict[str, str | None],
        column_map: dict[str, str],
        source_file: str,
    ) -> RawCandidateData:
        """Convert one CSV row dict into a :class:`RawCandidateData`."""
        get = lambda field: self._get_cell(row, column_map, field)  # noqa: E731

        raw_email = get("email")
        emails = [raw_email] if raw_email else []

        raw_phone = get("phone")
        phones = [raw_phone] if raw_phone else []

        raw_linkedin = get("linkedin_url")
        links = [raw_linkedin] if raw_linkedin else []

        return RawCandidateData(
            source=self.source_type,
            source_file=source_file,
            full_name=get("full_name"),
            emails=emails,
            phones=phones,
            location=get("location"),
            links=links,
            headline=get("headline"),
            years_experience=self._parse_years_experience(get("years_experience")),
            skills=self._parse_skills(get("skills")),
        )
