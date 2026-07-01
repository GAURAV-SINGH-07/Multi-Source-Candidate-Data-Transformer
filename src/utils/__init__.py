"""Utils sub-package — cross-cutting concerns with no business logic."""

from .logging_config import get_logger
from .id_generator import generate_candidate_id
from .html_report import render_html_report

__all__ = ["get_logger", "generate_candidate_id", "render_html_report"]
