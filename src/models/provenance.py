"""
ProvenanceRecord — immutable audit trail for a single field value.

Every value in the canonical profile has at least one ProvenanceRecord
describing where it came from, how it was extracted, and when. Records
are accumulated (not replaced) so the full audit trail is preserved.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .source_type import SourceType


class ProvenanceRecord(BaseModel):
    """Audit trail entry for a single field extraction event.

    Attributes:
        field:      The canonical field name this record applies to
                    (e.g., ``"phones"``, ``"full_name"``).
        value:      The extracted and normalized value at this point.
        source:     Which data source produced this value.
        method:     Short description of the extraction method
                    (e.g., ``"regex"``, ``"csv_column:phone"``).
        confidence: The confidence score assigned to this specific record
                    before merging (0.0 – 1.0).
        timestamp:  When this record was created. Defaults to UTC now.
        notes:      Optional free-form annotation (e.g., conflict details).
    """

    model_config = ConfigDict(frozen=True)

    field: str = Field(..., description="Canonical field name")
    value: Any = Field(..., description="Extracted and normalized value")
    source: SourceType = Field(..., description="Data source that produced this value")
    method: str = Field(..., description="Extraction method description")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Per-record confidence before merging",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of extraction",
    )
    notes: str | None = Field(
        default=None,
        description="Optional annotation, e.g. conflict explanation",
    )
