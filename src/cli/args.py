"""
CLI argument parser for the Multi-Source Candidate Data Transformer.

Usage examples:
    python main.py --csv sample_inputs/recruiter.csv
    python main.py --resume sample_inputs/resume.pdf
    python main.py --csv sample_inputs/recruiter.csv --resume sample_inputs/resume.pdf
    python main.py --csv recruiter.csv --resume resume.pdf --config config.json --output-dir outputs/
    python main.py --csv recruiter.csv --log-level DEBUG
    python main.py --version
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CLIArgs:
    """Typed representation of parsed CLI arguments."""
    csv_path: Path | None
    resume_path: Path | None
    config_path: Path | None
    output_dir: Path
    log_level: str
    quiet: bool


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="eightfold-transformer",
        description=(
            "Multi-Source Candidate Data Transformer — "
            "merges recruiter CSV and/or resume PDF into one canonical profile."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --csv recruiter.csv
  python main.py --resume resume.pdf
  python main.py --csv recruiter.csv --resume resume.pdf --config config.json
  python main.py --csv recruiter.csv --output-dir my_outputs/ --log-level DEBUG
        """,
    )

    parser.add_argument(
        "--csv",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to the recruiter CSV file.",
    )
    parser.add_argument(
        "--resume",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to the candidate resume PDF.",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        default=None,
        help=(
            "Path to the projection config JSON. "
            "If omitted, all fields are included with no renaming."
        ),
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        type=Path,
        default=Path("outputs"),
        help="Directory to write output files (default: outputs/).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all log output to stdout (useful for scripted pipelines).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> CLIArgs:
    """Parse and validate CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        :class:`CLIArgs` with typed, validated values.

    Raises:
        SystemExit: On argument errors (handled by argparse).
    """
    parser = build_parser()
    ns = parser.parse_args(argv)

    # Validate: at least one source required
    if ns.csv is None and ns.resume is None:
        parser.error(
            "at least one source is required: provide --csv and/or --resume"
        )

    # Validate: source files must exist
    for flag, path in [("--csv", ns.csv), ("--resume", ns.resume)]:
        if path is not None and not path.exists():
            parser.error(f"{flag} path does not exist: {path}")

    # Validate: config file must exist if provided
    if ns.config is not None and not ns.config.exists():
        parser.error(f"--config path does not exist: {ns.config}")

    return CLIArgs(
        csv_path=ns.csv,
        resume_path=ns.resume,
        config_path=ns.config,
        output_dir=ns.output_dir,
        log_level=ns.log_level,
        quiet=ns.quiet,
    )
