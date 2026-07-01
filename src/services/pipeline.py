"""
PipelineOrchestrator — wires all pipeline stages into one coherent run.

Responsibilities:
    1. Accept input paths (CSV, PDF, config) and an output directory.
    2. Route each file to the correct extractor via ExtractorRegistry.
    3. Run the MergeEngine over all extracted sources.
    4. Project the canonical candidate via ProjectionEngine.
    5. Validate the projected output.
    6. Collect execution metrics.
    7. Write all output files and return a PipelineOutput.

The orchestrator depends only on the public interfaces of each stage.
It holds no business logic of its own — it is a coordinator, not a processor.

A ``progress_callback`` parameter supports the Streamlit UI's live progress
bar without coupling the orchestrator to Streamlit.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.config.settings import settings
from src.extractors import ExtractorRegistry
from src.merger import MergeEngine, MergeResult
from src.models.candidate import CanonicalCandidate
from src.models.source_type import SourceType
from src.projection import ProjectionConfig, ProjectionEngine
from src.validators import ValidationResult, validate_output
from src.utils.logging_config import get_logger
from src.utils.html_report import render_html_report

log = get_logger(__name__)

# Callable type: (message: str, percent_complete: int) -> None
ProgressCallback = Callable[[str, int], None]


@dataclass
class PipelineInput:
    """Configuration for a single pipeline run.

    Attributes:
        csv_path:    Path to the recruiter CSV file (optional).
        resume_path: Path to the resume PDF file (optional).
        config_path: Path to the projection config JSON (optional;
                     defaults to an include-everything config).
        output_dir:  Directory where output files are written.
                     Created if it does not exist.
    """

    csv_path: Path | None = None
    resume_path: Path | None = None
    config_path: Path | None = None
    output_dir: Path = field(default_factory=lambda: settings.output_dir)


@dataclass
class PipelineOutput:
    """Results of one complete pipeline run.

    Attributes:
        candidate:          The merged, normalized canonical candidate.
        projected:          The projected output dict (from ProjectionEngine).
        validation:         Validation result for the projected output.
        merge_result:       Full MergeResult including conflict decisions.
        metrics:            Execution metrics dict.
        output_paths:       Paths to all written output files.
        warnings:           All non-fatal warnings accumulated during the run.
    """

    candidate: CanonicalCandidate
    projected: dict[str, Any]
    validation: ValidationResult
    merge_result: MergeResult
    metrics: dict[str, Any]
    output_paths: dict[str, Path]
    warnings: list[str]


class PipelineOrchestrator:
    """Coordinates the full multi-source candidate transformation pipeline.

    Args:
        merge_engine:       Injectable MergeEngine (default: fresh instance).
        projection_engine:  Injectable ProjectionEngine (default: fresh instance).
    """

    def __init__(
        self,
        merge_engine: MergeEngine | None = None,
        projection_engine: ProjectionEngine | None = None,
    ) -> None:
        self._merger = merge_engine or MergeEngine()
        self._projector = projection_engine or ProjectionEngine()

    def run(
        self,
        pipeline_input: PipelineInput,
        progress: ProgressCallback | None = None,
    ) -> PipelineOutput:
        """Execute the full pipeline and write output files.

        Args:
            pipeline_input: Source paths and output directory.
            progress:       Optional callback for progress reporting.
                            Called as ``progress(message, percent_complete)``.

        Returns:
            :class:`PipelineOutput` with the full run results.

        Raises:
            ValueError: If no source files are provided.
        """
        started_at = time.perf_counter()
        _progress = progress or (lambda msg, pct: None)

        _progress("Validating inputs…", 5)
        self._validate_inputs(pipeline_input)

        output_dir = pipeline_input.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # ── Stage 1: Extract ──────────────────────────────────────────────
        _progress("Extracting sources…", 15)
        raw_sources, extract_warnings = self._extract_all(pipeline_input)

        # ── Stage 2: Merge + Normalize + Confidence ───────────────────────
        _progress("Merging and normalizing…", 40)
        merge_result = self._merger.merge(raw_sources)

        # ── Stage 3: Load projection config ───────────────────────────────
        _progress("Loading projection config…", 55)
        proj_config = self._load_projection_config(pipeline_input.config_path)

        # ── Stage 4: Project ──────────────────────────────────────────────
        _progress("Projecting output…", 65)
        projected = self._projector.project(merge_result.candidate, proj_config)

        # ── Stage 5: Validate ─────────────────────────────────────────────
        _progress("Validating output…", 75)
        validation = validate_output(projected)

        # ── Stage 6: Collect metrics ──────────────────────────────────────
        elapsed = round(time.perf_counter() - started_at, 3)
        all_warnings = extract_warnings + merge_result.warnings
        metrics = self._build_metrics(
            pipeline_input, merge_result, validation, elapsed, all_warnings
        )

        # ── Stage 7: Write output files ───────────────────────────────────
        _progress("Writing output files…", 85)
        output_paths = self._write_outputs(
            output_dir=output_dir,
            projected=projected,
            explanation=merge_result.explanation,
            metrics=metrics,
            decision_log=merge_result.decision_log,
            candidate=merge_result.candidate,
        )

        _progress("Complete.", 100)
        log.info(
            "Pipeline complete in %.3fs: candidate=%s confidence=%.2f "
            "warnings=%d files=%d",
            elapsed,
            merge_result.candidate.candidate_id,
            merge_result.candidate.overall_confidence,
            len(all_warnings),
            len(output_paths),
        )

        return PipelineOutput(
            candidate=merge_result.candidate,
            projected=projected,
            validation=validation,
            merge_result=merge_result,
            metrics=metrics,
            output_paths=output_paths,
            warnings=all_warnings,
        )

    # ------------------------------------------------------------------
    # Private: stage runners
    # ------------------------------------------------------------------

    def _validate_inputs(self, inp: PipelineInput) -> None:
        """Raise ValueError if no usable source files are provided."""
        if not inp.csv_path and not inp.resume_path:
            raise ValueError(
                "At least one source file is required: --csv and/or --resume"
            )

    def _extract_all(
        self, inp: PipelineInput
    ) -> tuple[list, list[str]]:
        """Run all available extractors and collect results."""
        from src.models.raw import RawCandidateData
        sources: list[RawCandidateData] = []
        warnings: list[str] = []

        file_pairs: list[tuple[Path | None, SourceType]] = [
            (inp.csv_path,    SourceType.RECRUITER_CSV),
            (inp.resume_path, SourceType.RESUME_PDF),
        ]

        for path, source_type in file_pairs:
            if not path:
                continue
            if not path.exists():
                msg = f"Source file not found: {path}"
                warnings.append(msg)
                log.warning(msg)
                continue
            try:
                extractor = ExtractorRegistry.instantiate(source_type)
                records = extractor.extract(path)
                # For this pipeline we take the first record per source
                if records:
                    sources.append(records[0])
                    log.info("Extracted 1 record from %s (%s)", path.name, source_type.value)
                else:
                    msg = f"No records extracted from {path.name}"
                    warnings.append(msg)
                    log.warning(msg)
            except Exception as exc:
                msg = f"Extraction failed for {path.name}: {exc}"
                warnings.append(msg)
                log.error(msg)

        return sources, warnings

    def _load_projection_config(self, config_path: Path | None) -> ProjectionConfig:
        """Load the projection config, falling back to default."""
        if config_path is None:
            log.info("No config file provided — using default projection config")
            return ProjectionConfig.default()
        try:
            cfg = ProjectionConfig.from_file(config_path)
            log.info("Loaded projection config from %s", config_path.name)
            return cfg
        except Exception as exc:
            log.warning("Failed to load config from %s: %s — using default", config_path, exc)
            return ProjectionConfig.default()

    def _build_metrics(
        self,
        inp: PipelineInput,
        merge_result: MergeResult,
        validation: ValidationResult,
        elapsed: float,
        warnings: list[str],
    ) -> dict[str, Any]:
        """Assemble the metrics.json payload."""
        candidate = merge_result.candidate

        # Count normalized skills
        skill_count = len(candidate.skills)
        exact_skills = sum(
            1 for prov_list in candidate.provenance.get("skills", [])
            for prov in [prov_list]
            if hasattr(prov, "method") and "exact" in prov.method
        )

        sources_used = []
        if inp.csv_path:
            sources_used.append(SourceType.RECRUITER_CSV.value)
        if inp.resume_path:
            sources_used.append(SourceType.RESUME_PDF.value)

        return {
            "records_processed": len(sources_used),
            "sources_used": sources_used,
            "conflicts_resolved": len(merge_result.conflicts),
            "duplicates_removed": merge_result.duplicates_removed,
            "invalid_fields": validation.error_count,
            "normalized_skills": skill_count,
            "warnings": warnings,
            "warning_count": len(warnings),
            "execution_time_seconds": elapsed,
            "overall_confidence": round(candidate.overall_confidence, 4),
            "pipeline_version": candidate.pipeline_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_fields": len(merge_result.explanation),
            "validation_summary": validation.summary(),
        }

    def _write_outputs(
        self,
        output_dir: Path,
        projected: dict[str, Any],
        explanation: dict[str, Any],
        metrics: dict[str, Any],
        decision_log: list[dict[str, Any]],
        candidate: CanonicalCandidate,
    ) -> dict[str, Path]:
        """Serialise and write all 5 output files. Returns path map."""
        paths: dict[str, Path] = {}

        def _write(filename: str, data: Any) -> Path:
            """Write *data* to *filename* inside *output_dir* atomically.

            Serialises to a ``.tmp`` sibling first, then calls
            ``Path.replace()`` to swap it into place.  On POSIX this is a
            single atomic ``rename(2)`` syscall; on Windows it uses
            ``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING``.  Either way,
            readers will never observe a partially-written file.

            If the write fails the ``.tmp`` file is removed and the
            exception is re-raised, leaving any pre-existing output file
            untouched.
            """
            path = output_dir / filename
            tmp_path = path.with_name(path.name + ".tmp")
            content = (
                data
                if isinstance(data, str)
                else json.dumps(data, indent=2, default=str, ensure_ascii=False)
            )
            try:
                tmp_path.write_text(content, encoding="utf-8")
                tmp_path.replace(path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
            log.debug("Wrote %s (%d bytes)", filename, path.stat().st_size)
            return path

        paths["candidate"]    = _write("candidate.json", projected)
        paths["explanation"]  = _write("explanation.json", explanation)
        paths["metrics"]      = _write("metrics.json", metrics)
        paths["decision_log"] = _write("decision_log.json", decision_log)
        paths["report"]       = _write(
            "report.html",
            render_html_report(candidate, explanation, metrics),
        )
        return paths
