"""
Shared pytest fixtures for the EightFold test suite.

Fixtures defined here are automatically available to all test modules
without explicit imports.
"""

import sys
import pytest
from pathlib import Path

# Ensure src/ is importable when running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.raw import RawCandidateData, RawExperienceEntry, RawEducationEntry
from src.models.source_type import SourceType


# ── Sample raw data ────────────────────────────────────────────────────────

@pytest.fixture
def raw_csv() -> RawCandidateData:
    """Realistic RawCandidateData as if extracted from a recruiter CSV."""
    return RawCandidateData(
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


@pytest.fixture
def raw_pdf() -> RawCandidateData:
    """Realistic RawCandidateData as if extracted from a resume PDF."""
    return RawCandidateData(
        source=SourceType.RESUME_PDF,
        source_file="resume.pdf",
        full_name="Priya Sharma",
        emails=["priya.sharma@email.com"],
        phones=["+91-98765-43210"],
        location="Bangalore, IN",
        years_experience=6,
        skills=["Python", "pyspark", "TensorFlow", "Docker"],
        experience=[
            RawExperienceEntry(
                title="Senior Data Engineer",
                company="Acme Corp",
                start_date="Jan 2020",
                end_date="Present",
                is_current=True,
                description="Built ETL pipelines.",
            )
        ],
        education=[
            RawEducationEntry(
                institution="IIT Bombay",
                degree="B.Tech",
                field_of_study="Computer Science",
                end_date="2018",
            )
        ],
    )


@pytest.fixture
def raw_conflicting_pdf() -> RawCandidateData:
    """PDF source with values that conflict with the CSV source."""
    return RawCandidateData(
        source=SourceType.RESUME_PDF,
        source_file="resume.pdf",
        full_name="P. Sharma",       # conflicts with CSV
        emails=["priya.sharma@email.com"],
        phones=["+91-98765-43210"],
        location="Mumbai, India",    # conflicts with CSV (different city)
    )


@pytest.fixture
def sample_csv_path() -> Path:
    return Path(__file__).parent.parent / "sample_inputs" / "recruiter.csv"


@pytest.fixture
def sample_config_path() -> Path:
    return Path(__file__).parent.parent / "sample_inputs" / "config.json"
