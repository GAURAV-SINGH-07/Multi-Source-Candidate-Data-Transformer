"""
ResumePDFExtractor — extracts candidate data from a resume PDF.

Extraction strategy:
    1. Use PyMuPDF (``fitz``) for robust text extraction per page.
    2. Concatenate all page texts into one document string.
    3. Apply regex patterns to locate contact fields (email, phone, URLs).
    4. Apply section-heading heuristics to split the text into named sections.
    5. Parse skill, experience, and education sections with targeted patterns.

Known limitations:
    - Works best on text-based PDFs; scanned-image PDFs produce no text.
    - Section detection relies on common heading patterns; unusual resume
      formats may produce incomplete results. This is logged as a warning,
      not raised as an error.
    - Name extraction is heuristic (first substantive line); inaccurate for
      PDFs with headers, logos, or contact info before the name.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from src.models.raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from src.models.source_type import SourceType
from src.utils.logging_config import get_logger
from .base import BaseExtractor
from .registry import ExtractorRegistry

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
_PHONE_RE = re.compile(
    r"""
    (?:
        \+?\d{1,3}[\s\-.]?      # optional country code
    )?
    (?:\(?\d{2,4}\)?[\s\-.]?)   # area code
    \d{3,4}[\s\-.]?\d{3,4}      # local number
    """,
    re.VERBOSE,
)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+",
    re.IGNORECASE,
)
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    r"https?://[^\s<>\"{}|\\^\[\]`]+",
    re.IGNORECASE,
)

# Section heading patterns — matches lines that look like resume section headers.
# Anchored to start of line (after stripping) and case-insensitive.
_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "skills": re.compile(
        r"^(?:technical\s+)?skills?(?:\s+[&/]?\s*\w+)?$|"
        r"^(?:core\s+)?competenc(?:y|ies)$|"
        r"^technologies$|"
        r"^tech(?:nical)?\s+stack$|"
        r"^tools\s+(?:&|and)\s+technologies$",
        re.IGNORECASE,
    ),
    "experience": re.compile(
        r"^(?:professional\s+|work\s+)?experience$|"
        r"^employment(?:\s+history)?$|"
        r"^work\s+history$|"
        r"^career\s+(?:history|summary)?$",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"^education(?:al\s+background)?$|"
        r"^academic(?:\s+background)?$|"
        r"^qualifications?$",
        re.IGNORECASE,
    ),
    "summary": re.compile(
        r"^(?:professional\s+)?summary$|"
        r"^profile$|"
        r"^objective$|"
        r"^about(?:\s+me)?$",
        re.IGNORECASE,
    ),
}

# Date pattern used in experience/education parsing
_DATE_RE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{4}"
    r"|(?:\d{1,2}/\d{4})"
    r"|\d{4}",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{4}"
    r"|\d{4})"
    r"\s*(?:–|—|-|·|•|to)\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{4}"
    r"|Present|Current|Now|\d{4})",
    re.IGNORECASE,
)

# Years-of-experience extraction from summary text
_WORD_TO_NUMBER = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_YOE_RE = re.compile(
    r"(?i)\b(?:over|more than|about|around|approximately|nearly|almost|roughly)?\s*"
    r"(?:(?P<numeric>\d+(?:\.\d+)?)\+?|(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty))"
    r"\s*(?:\+)?\s*years?\b"
)


class _Section(NamedTuple):
    name: str
    lines: list[str]


@ExtractorRegistry.register
class ResumePDFExtractor(BaseExtractor):
    """Extracts candidate data from a resume PDF using PyMuPDF."""

    source_type = SourceType.RESUME_PDF

    def can_handle(self, source: Path | str) -> bool:
        """Return True for ``.pdf`` files."""
        return Path(source).suffix.lower() == ".pdf"

    def extract(self, source: Path | str) -> list[RawCandidateData]:
        """Extract candidate data from a resume PDF.

        Args:
            source: Path to the PDF file.

        Returns:
            A list containing exactly one :class:`RawCandidateData` (PDFs
            represent one candidate), or an empty list if extraction fails
            completely.

        Raises:
            FileNotFoundError: If *source* does not exist.
        """
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        log.info("Extracting PDF: %s", path.name)

        text, warnings = self._extract_text(path)
        if not text.strip():
            log.warning("No text content extracted from PDF: %s", path.name)
            return []

        sections = self._detect_sections(text)
        record = self._build_record(text, sections, str(path), warnings)

        log.info(
            "PDF extraction complete: name=%r, emails=%d, phones=%d, skills=%d",
            record.full_name,
            len(record.emails),
            len(record.phones),
            len(record.skills),
        )
        return [record]

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def _extract_text(self, path: Path) -> tuple[str, list[str]]:
        """Extract plain text from all pages of *path*.

        Returns:
            Tuple of (full_text, warnings). On page-level errors, the page
            is skipped and a warning is appended rather than raising.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise ImportError("PyMuPDF is required: pip install PyMuPDF") from exc

        warnings: list[str] = []
        pages: list[str] = []

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            log.error("Cannot open PDF %s: %s", path.name, exc)
            warnings.append(f"PDF open error: {exc}")
            return "", warnings

        from src.config.settings import settings
        max_pages = min(len(doc), settings.pdf_max_pages)

        for page_num in range(max_pages):
            try:
                page = doc.load_page(page_num)
                pages.append(page.get_text("text"))
            except Exception as exc:
                msg = f"Failed to read page {page_num + 1}: {exc}"
                log.warning(msg)
                warnings.append(msg)

        doc.close()
        return "\n".join(pages), warnings

    # ------------------------------------------------------------------
    # Section detection
    # ------------------------------------------------------------------

    def _detect_sections(self, text: str) -> dict[str, _Section]:
        """Split document text into named sections.

        A line is treated as a section heading if it:
            - Is short (≤ 60 chars after stripping)
            - Matches one of the known ``_SECTION_PATTERNS``
            - Is not obviously a regular sentence (no period at end)

        Returns:
            Dict of ``{section_name: _Section}``, plus a special ``"header"``
            section containing all lines before the first detected heading.
        """
        lines = text.splitlines()
        sections: dict[str, _Section] = {}
        current_section = "header"
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_lines.append(line)
                continue

            heading = self._classify_heading(stripped)
            if heading and heading != current_section:
                sections[current_section] = _Section(current_section, current_lines)
                current_section = heading
                current_lines = []
            else:
                current_lines.append(line)

        sections[current_section] = _Section(current_section, current_lines)
        log.debug("Detected sections: %s", list(sections.keys()))
        return sections

    def _classify_heading(self, line: str) -> str | None:
        """Return the section name if *line* looks like a heading, else None."""
        if len(line) > 60 or line.endswith("."):
            return None
        for section_name, pattern in _SECTION_PATTERNS.items():
            if pattern.match(line):
                return section_name
        return None

    # ------------------------------------------------------------------
    # Record building
    # ------------------------------------------------------------------

    def _build_record(
        self,
        full_text: str,
        sections: dict[str, _Section],
        source_file: str,
        warnings: list[str],
    ) -> RawCandidateData:
        """Assemble a RawCandidateData from the extracted text and sections."""
        header_text = "\n".join(
            sections.get("header", _Section("header", [])).lines
        )

        emails = _EMAIL_RE.findall(full_text)
        emails = list(dict.fromkeys(emails))  # preserve order, deduplicate

        phones = self._extract_phones(full_text)

        all_urls = _URL_RE.findall(full_text)
        linkedin = _LINKEDIN_RE.findall(full_text)
        github = _GITHUB_RE.findall(full_text)
        links = list(dict.fromkeys(linkedin + github + [
            u for u in all_urls
            if "linkedin" not in u.lower() and "github" not in u.lower()
        ]))

        name = self._extract_name(header_text, emails)
        headline = self._extract_headline(sections)
        yoe = self._extract_years_experience(full_text)
        skills = self._extract_skills(sections)
        experience = self._extract_experience(sections)
        education = self._extract_education(sections)

        return RawCandidateData(
            source=self.source_type,
            source_file=source_file,
            full_name=name,
            emails=emails,
            phones=phones,
            links=links,
            headline=headline,
            years_experience=yoe,
            skills=skills,
            experience=experience,
            education=education,
            raw_text=full_text,
            metadata={"warnings": warnings},
        )

    # ------------------------------------------------------------------
    # Field-level extractors
    # ------------------------------------------------------------------

    def _extract_phones(self, text: str) -> list[str]:
        """Extract phone-like strings, filtering obvious false positives."""
        candidates = _PHONE_RE.findall(text)
        phones: list[str] = []
        seen: set[str] = set()
        for raw in candidates:
            digits = re.sub(r"\D", "", raw)
            # Reject too-short, too-long, or pure-year matches
            if len(digits) < 7 or len(digits) > 15:
                continue
            normalized = raw.strip()
            if normalized not in seen:
                seen.add(normalized)
                phones.append(normalized)
        return phones

    def _extract_name(self, header_text: str, emails: list[str]) -> str | None:
        """Heuristically extract the candidate name from the document header.

        Strategy: the name is typically the first non-empty line that is:
            - Not an email address
            - Not a URL
            - Not a phone number
            - Not longer than 60 characters
        """
        for line in header_text.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) > 60:
                continue
            if "@" in stripped or "http" in stripped.lower():
                continue
            if re.match(r"^[\d\s\+\-\(\)\.]+$", stripped):
                continue
            # Must contain at least two "word" tokens to be a name
            words = stripped.split()
            if len(words) >= 2:
                return stripped
        return None

    def _extract_headline(self, sections: dict[str, _Section]) -> str | None:
        """Extract headline from the summary section (first non-empty line)."""
        summary = sections.get("summary")
        if not summary:
            return None
        for line in summary.lines:
            stripped = line.strip()
            if stripped and len(stripped) > 5:
                return stripped
        return None

    def _extract_years_experience(self, text: str) -> float | None:
        """Extract years of experience from the document text."""
        match = _YOE_RE.search(text)
        if not match:
            return None

        raw_value = match.group("numeric") or match.group("word")
        if raw_value is None:
            return None

        value = raw_value.rstrip("+")
        if match.group("word"):
            value = str(_WORD_TO_NUMBER.get(match.group("word").lower(), value))

        try:
            return float(value)
        except ValueError:
            return None

    def _extract_skills(self, sections: dict[str, _Section]) -> list[str]:
        """Extract skills from the skills section."""
        skills_section = sections.get("skills")
        if not skills_section:
            return []

        text = "\n".join(skills_section.lines)
        # Skills appear as comma/pipe/bullet separated lists
        parts = re.split(r"[,|•·\n]+", text)
        skills = []
        for part in parts:
            cleaned = re.sub(r"[^\w\s\+\#\.\/\-]", "", part).strip()
            if cleaned and 1 < len(cleaned) < 60:
                skills.append(cleaned)
        return list(dict.fromkeys(skills))  # deduplicate, preserve order

    def _extract_experience(
        self, sections: dict[str, _Section]
    ) -> list[RawExperienceEntry]:
        """Parse work experience entries from the experience section.

        Each entry is heuristically detected by looking for date-range
        patterns (which typically anchor a job block in a resume).
        """
        exp_section = sections.get("experience")
        if not exp_section:
            return []

        entries: list[RawExperienceEntry] = []
        current_lines: list[str] = []

        def _flush(lines: list[str]) -> None:
            entry = self._parse_experience_block(lines)
            if entry:
                entries.append(entry)

        for line in exp_section.lines:
            if _DATE_RANGE_RE.search(line) and current_lines:
                _flush(current_lines)
                current_lines = [line]
            else:
                current_lines.append(line)

        _flush(current_lines)
        return entries

    def _parse_experience_block(
        self, lines: list[str]
    ) -> RawExperienceEntry | None:
        """Convert a block of lines into a RawExperienceEntry."""
        text = " ".join(l.strip() for l in lines if l.strip())
        if not text:
            return None

        date_match = _DATE_RANGE_RE.search(text)
        start_date = date_match.group(1) if date_match else None
        end_date = date_match.group(2) if date_match else None
        is_current = bool(
            end_date and re.match(r"present|current|now", end_date, re.IGNORECASE)
        )

        # Strip date range from text to get title/company
        remainder = _DATE_RANGE_RE.sub("", text).strip(" –—|-")
        parts = re.split(r"\s*[|@–—,]\s*|\s{2,}", remainder)
        parts = [p.strip() for p in parts if p.strip()]

        title = parts[0] if len(parts) >= 1 else None
        company = parts[1] if len(parts) >= 2 else None

        return RawExperienceEntry(
            title=title,
            company=company,
            start_date=start_date,
            end_date=None if is_current else end_date,
            is_current=is_current,
            description=text,
        )

    def _extract_education(
        self, sections: dict[str, _Section]
    ) -> list[RawEducationEntry]:
        """Parse education entries from the education section."""
        edu_section = sections.get("education")
        if not edu_section:
            return []

        entries: list[RawEducationEntry] = []
        current_lines: list[str] = []

        def _flush(lines: list[str]) -> None:
            entry = self._parse_education_block(lines)
            if entry:
                entries.append(entry)

        for line in edu_section.lines:
            # A new institution block often starts with a year or degree keyword
            if (_DATE_RE.search(line) or re.search(
                r"\b(?:B\.?Tech|B\.?E|M\.?Tech|M\.?S|MBA|B\.?Sc|M\.?Sc|Ph\.?D|Bachelor|Master|Doctor)\b",
                line, re.IGNORECASE
            )) and current_lines:
                _flush(current_lines)
                current_lines = [line]
            else:
                current_lines.append(line)

        _flush(current_lines)
        return entries

    def _parse_education_block(
        self, lines: list[str]
    ) -> RawEducationEntry | None:
        """Convert a block of lines into a RawEducationEntry."""
        text = " ".join(l.strip() for l in lines if l.strip())
        if not text:
            return None

        # Try to find degree type
        degree_match = re.search(
            r"\b(B\.?Tech|B\.?E|M\.?Tech|M\.?S|MBA|B\.?Sc|M\.?Sc|Ph\.?D|"
            r"Bachelor(?:\s+of\s+\w+)?|Master(?:\s+of\s+\w+)?|Doctorate)\b",
            text, re.IGNORECASE
        )
        degree = degree_match.group(0) if degree_match else None

        date_match = _DATE_RANGE_RE.search(text)
        start_date = date_match.group(1) if date_match else None
        end_date = date_match.group(2) if date_match else None

        # Institution is often the last substantive fragment after removing degree/dates
        remainder = text
        if degree_match:
            remainder = remainder.replace(degree_match.group(0), "")
        if date_match:
            remainder = _DATE_RANGE_RE.sub("", remainder)
        institution = remainder.strip(" ,|–—") or None

        return RawEducationEntry(
            institution=institution,
            degree=degree,
            start_date=start_date,
            end_date=end_date,
        )
