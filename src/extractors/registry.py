"""
ExtractorRegistry — the plugin registry mapping SourceType → extractor class.

Extractors register themselves by decorating their class with
``@ExtractorRegistry.register``. Registration happens at module import time,
so the pipeline only needs to ensure all extractor modules are imported before
calling :meth:`ExtractorRegistry.get` or :meth:`ExtractorRegistry.instantiate`.

Design:
    The registry uses a class-level dict rather than module-level state so it
    can be cleanly inspected and tested. Overwriting an existing registration
    emits a warning but succeeds — this allows tests to swap in mock extractors
    without patching internals.
"""

import logging
from pathlib import Path
from typing import TypeVar

from src.models.raw import RawCandidateData
from src.models.source_type import SourceType
from src.utils.logging_config import get_logger
from .base import BaseExtractor

_T = TypeVar("_T", bound=type[BaseExtractor])
log = get_logger(__name__)


class ExtractorRegistry:
    """Class-level plugin registry for :class:`BaseExtractor` implementations.

    Usage::

        # Register (decoration pattern)
        @ExtractorRegistry.register
        class MyExtractor(BaseExtractor):
            source_type = SourceType.ATS_JSON
            ...

        # Retrieve and use
        extractor = ExtractorRegistry.instantiate(SourceType.ATS_JSON)
        records = extractor.extract(path)
    """

    _registry: dict[SourceType, type[BaseExtractor]] = {}

    @classmethod
    def register(cls, extractor_class: _T) -> _T:
        """Register *extractor_class* in the registry.

        Can be used as a plain decorator or called directly::

            @ExtractorRegistry.register
            class Foo(BaseExtractor): ...

            # Equivalent:
            ExtractorRegistry.register(Foo)

        Args:
            extractor_class: A concrete subclass of :class:`BaseExtractor`
                             with a declared ``source_type`` class attribute.

        Returns:
            The extractor class unchanged (for transparent decoration).

        Raises:
            AttributeError: If *extractor_class* has no ``source_type``.
        """
        if not hasattr(extractor_class, "source_type"):
            raise AttributeError(
                f"{extractor_class.__name__} must declare a 'source_type' "
                f"class attribute before registering."
            )
        source_type: SourceType = extractor_class.source_type
        if source_type in cls._registry:
            log.warning(
                "Overwriting existing extractor for %r: %s → %s",
                source_type,
                cls._registry[source_type].__name__,
                extractor_class.__name__,
            )
        cls._registry[source_type] = extractor_class
        log.debug("Registered extractor: %s → %r", extractor_class.__name__, source_type)
        return extractor_class

    @classmethod
    def get(cls, source_type: SourceType) -> type[BaseExtractor]:
        """Return the extractor class registered for *source_type*.

        Args:
            source_type: The source type to look up.

        Returns:
            The registered extractor class (not yet instantiated).

        Raises:
            KeyError: If no extractor has been registered for *source_type*.
        """
        if source_type not in cls._registry:
            available = [st.value for st in cls._registry]
            raise KeyError(
                f"No extractor registered for source type {source_type!r}. "
                f"Available: {available}"
            )
        return cls._registry[source_type]

    @classmethod
    def instantiate(cls, source_type: SourceType) -> BaseExtractor:
        """Instantiate and return the extractor for *source_type*.

        Args:
            source_type: The desired source type.

        Returns:
            A fresh instance of the registered extractor class.
        """
        return cls.get(source_type)()

    @classmethod
    def detect(cls, source: Path | str) -> BaseExtractor | None:
        """Auto-detect which extractor to use for *source*.

        Iterates through all registered extractors and returns the first one
        whose :meth:`~BaseExtractor.can_handle` returns True.

        Args:
            source: Path to the source file.

        Returns:
            An instantiated extractor, or ``None`` if no match found.
        """
        for extractor_class in cls._registry.values():
            instance = extractor_class()
            if instance.can_handle(source):
                log.debug("Auto-detected extractor %r for %s", extractor_class.__name__, source)
                return instance
        return None

    @classmethod
    def all_registered(cls) -> dict[SourceType, type[BaseExtractor]]:
        """Return a read-only snapshot of the current registry."""
        return dict(cls._registry)

    @classmethod
    def clear(cls) -> None:
        """Clear the registry. Intended for use in tests only."""
        cls._registry.clear()
