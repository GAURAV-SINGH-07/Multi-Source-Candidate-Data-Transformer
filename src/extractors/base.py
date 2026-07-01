"""
BaseExtractor — abstract plugin interface for all candidate data sources.

Every source (CSV, PDF, ATS JSON, LinkedIn…) must subclass this and implement
``extract()``. The pipeline interacts exclusively with this interface, never
with concrete classes directly — a strict application of the Dependency
Inversion Principle.

Adding a new source requires:
    1. Create a new file in ``src/extractors/``
    2. Subclass ``BaseExtractor``
    3. Decorate with ``@ExtractorRegistry.register``
    4. Zero changes elsewhere.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from src.models.raw import RawCandidateData
from src.models.source_type import SourceType


class BaseExtractor(ABC):
    """Abstract plugin interface for candidate data extractors.

    Subclasses must:
        - Declare ``source_type`` as a class-level :class:`SourceType` value.
        - Implement :meth:`extract` to return a list of
          :class:`~src.models.raw.RawCandidateData` instances.
        - Optionally override :meth:`can_handle` for auto-detection support.

    The ``source_type`` attribute is used by :class:`ExtractorRegistry` to map
    source identifiers to their extractor implementations.

    Example::

        @ExtractorRegistry.register
        class ATSJsonExtractor(BaseExtractor):
            source_type = SourceType.ATS_JSON

            def extract(self, source: Path | str) -> list[RawCandidateData]:
                ...
    """

    #: Must be overridden in every concrete subclass.
    source_type: ClassVar[SourceType]

    @abstractmethod
    def extract(self, source: Path | str) -> list[RawCandidateData]:
        """Extract raw candidate data from *source*.

        Args:
            source: Absolute or relative path to the source file.

        Returns:
            A list of :class:`RawCandidateData` instances — one per logical
            candidate record found in the source. Returns an empty list (never
            raises) if the source yields no usable data.

        Raises:
            FileNotFoundError: If *source* does not exist.
            ValueError: If *source* is fundamentally unreadable (e.g., corrupt
                        binary with no recoverable content). Partial failures
                        (e.g., one bad page in a PDF) should be logged as
                        warnings, not raised.
        """
        ...  # pragma: no cover

    def can_handle(self, source: Path | str) -> bool:
        """Return True if this extractor can process *source*.

        The default implementation always returns False. Override to add
        auto-detection logic (e.g., extension check, magic-byte inspection).
        Used by the pipeline when the source type is not known in advance.

        Args:
            source: Path to inspect.

        Returns:
            True if this extractor should be chosen for *source*.
        """
        return False  # pragma: no cover

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source_type={self.source_type!r})"
