"""Tests for the CSV and PDF extractors."""

import pytest
import tempfile
from pathlib import Path

from src.extractors import ExtractorRegistry, RecruiterCSVExtractor, ResumePDFExtractor
from src.models.source_type import SourceType


# ═══════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════

def test_registry_has_both_extractors():
    registry = ExtractorRegistry.all_registered()
    assert SourceType.RECRUITER_CSV in registry
    assert SourceType.RESUME_PDF in registry


def test_registry_auto_detect_csv(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("name,email\nAlice,alice@test.com\n")
    extractor = ExtractorRegistry.detect(f)
    assert isinstance(extractor, RecruiterCSVExtractor)


def test_registry_auto_detect_pdf(tmp_path):
    f = tmp_path / "resume.pdf"
    f.write_bytes(b"%PDF-1.4 fake")  # minimal "PDF" header
    extractor = ExtractorRegistry.detect(f)
    assert isinstance(extractor, ResumePDFExtractor)


def test_registry_instantiate():
    extractor = ExtractorRegistry.instantiate(SourceType.RECRUITER_CSV)
    assert isinstance(extractor, RecruiterCSVExtractor)


# ═══════════════════════════════════════════════════════════════════════════
# CSV Extractor
# ═══════════════════════════════════════════════════════════════════════════

class TestRecruiterCSVExtractor:

    def test_extract_sample_csv(self, sample_csv_path):
        """Extracts all 3 rows from the sample recruiter CSV."""
        extractor = RecruiterCSVExtractor()
        records = extractor.extract(sample_csv_path)
        assert len(records) == 3

    def test_first_record_fields(self, sample_csv_path):
        extractor = RecruiterCSVExtractor()
        r = extractor.extract(sample_csv_path)[0]
        assert r.source == SourceType.RECRUITER_CSV
        assert r.full_name == "Priya Sharma"
        assert "priya.sharma@email.com" in r.emails
        assert len(r.phones) >= 1
        assert r.years_experience == 6.0

    def test_skills_extracted(self, sample_csv_path):
        extractor = RecruiterCSVExtractor()
        r = extractor.extract(sample_csv_path)[0]
        assert len(r.skills) > 0

    def test_can_handle_csv(self):
        assert RecruiterCSVExtractor().can_handle("anything.csv")
        assert not RecruiterCSVExtractor().can_handle("file.pdf")

    def test_empty_csv_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("")
        records = RecruiterCSVExtractor().extract(f)
        assert records == []

    def test_csv_with_unknown_columns(self, tmp_path):
        """CSV with unrecognized columns should gracefully return records with None fields."""
        f = tmp_path / "weird.csv"
        f.write_text("col_a,col_b\nfoo,bar\n")
        records = RecruiterCSVExtractor().extract(f)
        assert len(records) == 1
        assert records[0].full_name is None

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            RecruiterCSVExtractor().extract("nonexistent.csv")

    def test_bom_encoded_csv(self, tmp_path):
        """UTF-8-sig (BOM) encoded CSV should be handled transparently."""
        f = tmp_path / "bom.csv"
        f.write_bytes(
            b"\xef\xbb\xbfname,email\nBob,bob@test.com\n"
        )
        records = RecruiterCSVExtractor().extract(f)
        assert len(records) == 1
        assert records[0].full_name == "Bob"

    def test_years_experience_plus_format(self, tmp_path):
        """'5+ years' style should parse to 5.0."""
        f = tmp_path / "yoe.csv"
        f.write_text("name,email,years_of_experience\nAlice,a@b.com,5+\n")
        r = RecruiterCSVExtractor().extract(f)[0]
        assert r.years_experience == 5.0


# ═══════════════════════════════════════════════════════════════════════════
# PDF Extractor
# ═══════════════════════════════════════════════════════════════════════════

class TestResumePDFExtractor:

    def test_can_handle_pdf(self):
        assert ResumePDFExtractor().can_handle("resume.pdf")
        assert not ResumePDFExtractor().can_handle("data.csv")

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            ResumePDFExtractor().extract("nonexistent.pdf")

    def test_empty_pdf_returns_empty_list(self, tmp_path):
        """A PDF that produces no text should return []."""
        import fitz
        f = tmp_path / "blank.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(f))
        doc.close()
        records = ResumePDFExtractor().extract(f)
        assert records == []

    def test_extract_text_pdf(self, tmp_path):
        """A PDF with textual content should produce one record."""
        import fitz
        f = tmp_path / "resume.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Jane Doe")
        page.insert_text((72, 120), "jane.doe@example.com")
        page.insert_text((72, 140), "+1 (415) 555-0100")
        page.insert_text((72, 200), "Skills")
        page.insert_text((72, 220), "Python, React, SQL")
        doc.save(str(f))
        doc.close()

        records = ResumePDFExtractor().extract(f)
        assert len(records) == 1
        r = records[0]
        assert r.source == SourceType.RESUME_PDF
        assert len(r.emails) > 0
        assert "jane.doe@example.com" in r.emails

    def test_years_experience_is_derived_from_resume_history(self, tmp_path):
        """Resume summary and employment dates should yield a derived years_experience value."""
        import fitz
        from src.merger import MergeEngine

        f = tmp_path / "resume.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 80), "Senior Software Engineer")
        page.insert_text((72, 100), "Professional Summary")
        page.insert_text((72, 120), "Senior Software Engineer with over eight years of experience building distributed backend systems")
        page.insert_text((72, 160), "Experience")
        page.insert_text((72, 180), "Google")
        page.insert_text((72, 200), "2022–Present")
        page.insert_text((72, 220), "Google")
        page.insert_text((72, 240), "2019–2021")
        page.insert_text((72, 260), "Amazon")
        page.insert_text((72, 280), "2017–2019")
        doc.save(str(f))
        doc.close()

        raw = ResumePDFExtractor().extract(f)[0]
        candidate = MergeEngine().merge([raw]).candidate

        assert candidate.years_experience == 8.0
        assert candidate.provenance["years_experience"]
        assert candidate.confidence["years_experience"].score >= 0.7
