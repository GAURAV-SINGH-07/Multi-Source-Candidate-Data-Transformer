"""
Extractors sub-package.

Importing this package automatically registers all built-in extractors with
:class:`ExtractorRegistry`. Third-party extractors register themselves when
their module is imported — the pipeline just needs to import the package
containing them before calling ``ExtractorRegistry.get()``.

Adding a new built-in source:
    1. Create ``src/extractors/my_extractor.py``
    2. Subclass :class:`BaseExtractor` and decorate with
       ``@ExtractorRegistry.register``
    3. Add an import line below — that's it.
"""

from .base import BaseExtractor
from .registry import ExtractorRegistry

# Importing concrete extractors triggers their @ExtractorRegistry.register
# decorator. Order does not matter — each registers itself independently.
from .csv_extractor import RecruiterCSVExtractor
from .pdf_extractor import ResumePDFExtractor

__all__ = [
    "BaseExtractor",
    "ExtractorRegistry",
    "RecruiterCSVExtractor",
    "ResumePDFExtractor",
]
