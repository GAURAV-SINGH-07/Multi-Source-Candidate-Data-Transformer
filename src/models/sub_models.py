"""
Sub-models for the CanonicalCandidate.

Kept in a separate module to avoid the candidate.py file becoming large.
These models represent the nested structures within a candidate profile.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Location(BaseModel):
    """Parsed and normalized candidate location.

    Attributes:
        city:         City name (title-cased).
        state:        State or province name.
        country_code: ISO 3166-1 Alpha-2 country code (e.g., ``"IN"``).
        raw:          Original unparsed location string, kept for debugging.
    """

    model_config = ConfigDict(frozen=True)

    city: str | None = None
    state: str | None = None
    country_code: str | None = Field(
        default=None,
        description="ISO 3166-1 Alpha-2 (e.g. 'IN', 'US')",
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    raw: str | None = Field(default=None, description="Original unparsed string")

    @field_validator("country_code", mode="before")
    @classmethod
    def upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class Link(BaseModel):
    """A normalized URL with optional platform annotation.

    Attributes:
        url:      Fully qualified URL (always https-prefixed after normalization).
        platform: Inferred platform name (``"linkedin"``, ``"github"``,
                  ``"portfolio"``, ``"other"``).
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(..., description="Normalized URL")
    platform: str = Field(default="other", description="Inferred platform")


class SkillEntry(BaseModel):
    """A single normalized skill.

    Attributes:
        name:      Canonical skill name (from skill_synonyms dictionary).
        raw_name:  The original string as it appeared in the source.
        category:  Optional high-level category (``"language"``,
                   ``"framework"``, ``"cloud"``, ``"practice"``, etc.).
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Canonical skill name")
    raw_name: str = Field(..., description="Original string from source")
    category: str | None = Field(default=None, description="Skill category")


class ExperienceEntry(BaseModel):
    """A single work experience record.

    Dates are stored in YYYY-MM format after normalization, or ``None``
    if the source did not contain parseable dates.

    Attributes:
        title:       Job title.
        company:     Employer name.
        start_date:  YYYY-MM (normalized).
        end_date:    YYYY-MM (normalized) or ``None`` if current.
        is_current:  True if this is the candidate's current position.
        description: Role description / bullet points.
        location:    Work location if specified.
    """

    model_config = ConfigDict(frozen=True)

    title: str | None = None
    company: str | None = None
    start_date: str | None = Field(
        default=None,
        description="YYYY-MM formatted start date",
        pattern=r"^\d{4}-\d{2}$",
    )
    end_date: str | None = Field(
        default=None,
        description="YYYY-MM formatted end date",
        pattern=r"^\d{4}-\d{2}$",
    )
    is_current: bool = False
    description: str | None = None
    location: str | None = None


class EducationEntry(BaseModel):
    """A single education record.

    Attributes:
        institution:    Name of the educational institution.
        degree:         Degree type (e.g., ``"B.Tech"``, ``"M.S."``).
        field_of_study: Major or specialization.
        start_date:     YYYY-MM (normalized).
        end_date:       YYYY-MM (normalized).
        gpa:            Grade point average if present.
    """

    model_config = ConfigDict(frozen=True)

    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}$",
    )
    end_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}$",
    )
    gpa: float | None = Field(default=None, ge=0.0, le=10.0)
