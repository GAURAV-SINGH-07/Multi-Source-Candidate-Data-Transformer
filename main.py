"""
main.py — CLI entry point for the Multi-Source Candidate Data Transformer.

This file is intentionally thin. All business logic lives in the src/ package.
Responsibilities here:
    1. Parse CLI arguments.
    2. Configure logging.
    3. Build PipelineInput from parsed args.
    4. Invoke PipelineOrchestrator.run().
    5. Print a human-readable summary.
    6. Exit with a non-zero code if validation failed.

Usage:
    python main.py --csv sample_inputs/recruiter.csv
    python main.py --csv recruiter.csv --resume resume.pdf --config config.json
    python main.py --help
"""

import sys
import logging


def main() -> int:
    """Run the pipeline and return an exit code."""
    from src.cli import parse_args
    from src.services import PipelineOrchestrator, PipelineInput
    from src.utils.logging_config import configure_logging

    args = parse_args()

    # Configure logging based on --log-level and --quiet flags
    configure_logging(
        level=getattr(logging, args.log_level),
        quiet=args.quiet,
    )

    log = logging.getLogger(__name__)

    # ── Build pipeline input ───────────────────────────────────────────────
    pipeline_input = PipelineInput(
        csv_path=args.csv_path,
        resume_path=args.resume_path,
        config_path=args.config_path,
        output_dir=args.output_dir,
    )

    # ── Progress reporting (rich if available, plain text fallback) ───────
    def progress(message: str, percent: int) -> None:
        if not args.quiet:
            bar_filled = int(percent / 5)
            bar = "#" * bar_filled + "-" * (20 - bar_filled)
            # Use sys.stdout.buffer for safe Unicode output on Windows
            import sys as _sys
            line = f"\r  [{bar}] {percent:3d}%  {message:<40}"
            _sys.stdout.write(line)
            _sys.stdout.flush()

    # ── Run ───────────────────────────────────────────────────────────────
    orchestrator = PipelineOrchestrator()
    try:
        result = orchestrator.run(pipeline_input, progress=progress)
    except ValueError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        log.exception("Unexpected pipeline error")
        print(f"\nFatal error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print()  # newline after progress bar

    # ── Print summary ──────────────────────────────────────────────────────
    c = result.candidate
    sep = "-" * 60
    print("\n" + sep)
    print(f"  Candidate : {c.full_name or '(unknown)'}")
    print(f"  ID        : {c.candidate_id}")
    print(f"  Confidence: {c.overall_confidence:.1%}")
    print(f"  Skills    : {len(c.skills)}")
    print(f"  Warnings  : {len(result.warnings)}")
    print(sep)
    print(f"  Validation: {result.validation.summary()}")
    print(sep)
    print("  Output files:")
    for key, path in sorted(result.output_paths.items()):
        print(f"    {key:<14} -> {path}")
    print(sep + "\n")

    # Surface any validation errors to stderr
    for err in result.validation.errors:
        prefix = "ERROR" if err.severity == "error" else "WARN "
        print(f"  [{prefix}] {err.field}: {err.message}", file=sys.stderr)

    return 0 if result.validation.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
