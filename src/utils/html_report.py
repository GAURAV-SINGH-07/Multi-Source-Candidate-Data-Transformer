"""
HTML Report Renderer — produces a professional candidate profile report.

Uses Python f-string templates with inline CSS (no external dependencies).
The resulting HTML is self-contained and can be opened directly in any browser.

Design:
  - Neutral, professional color palette (dark header, white body, grey accents).
  - Confidence score displayed as a color-coded progress bar.
  - Skills rendered as pill/badge chips.
  - Timeline layout for experience.
  - Warning section only shown if warnings exist.
"""

from __future__ import annotations
import html
from typing import Any


def render_html_report(
    candidate: object,
    explanation: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    """Render *candidate* as a self-contained HTML report string.

    Args:
        candidate:   :class:`~src.models.candidate.CanonicalCandidate` instance.
        explanation: Explanation dict from :class:`~src.merger.engine.MergeResult`.
        metrics:     Pipeline metrics dict from :class:`~src.services.pipeline.PipelineOrchestrator`.

    Returns:
        Complete HTML document as a string.
    """
    c = candidate
    name     = _esc(c.full_name or "Unknown Candidate")
    headline = _esc(c.headline or "")
    conf_pct = int(round(c.overall_confidence * 100))
    conf_clr = _confidence_color(c.overall_confidence)

    emails_html  = _render_contact_items(c.emails, icon="✉")
    phones_html  = _render_contact_items(c.phones, icon="☎")
    location_html = _render_location(c.location)
    links_html   = _render_links(c.links)
    skills_html  = _render_skills(c.skills)
    exp_html     = _render_experience(c.experience)
    edu_html     = _render_education(c.education)
    metrics_html = _render_metrics(metrics)
    explain_html = _render_explanation(explanation)
    warnings_html= _render_warnings(c.warnings)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Candidate Report — {name}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: #f4f5f7; color: #24292f; line-height: 1.6; font-size: 15px; }}
    a {{ color: #0969da; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* ── Layout ── */
    .page {{ max-width: 900px; margin: 32px auto; padding: 0 16px 48px; }}

    /* ── Header ── */
    .header {{ background: #1c2128; color: #fff; border-radius: 10px 10px 0 0;
               padding: 32px 36px 28px; position: relative; }}
    .header h1 {{ font-size: 2rem; font-weight: 700; letter-spacing: -.5px; }}
    .header .headline {{ color: #8b949e; margin-top: 4px; font-size: 1.05rem; }}
    .badge-conf {{
      position: absolute; top: 28px; right: 36px;
      background: {conf_clr}22; border: 1px solid {conf_clr}66;
      color: {conf_clr}; border-radius: 20px; padding: 4px 14px;
      font-size: .85rem; font-weight: 600;
    }}

    /* ── Confidence bar ── */
    .conf-bar-wrap {{ background: #2d333b; border-radius: 4px;
                      margin-top: 18px; height: 6px; overflow: hidden; }}
    .conf-bar {{ height: 100%; width: {conf_pct}%;
                 background: {conf_clr}; border-radius: 4px; }}

    /* ── Card ── */
    .card {{ background: #fff; border: 1px solid #d0d7de; margin-top: 0;
             padding: 24px 36px; }}
    .card + .card {{ border-top: none; }}
    .card:last-of-type {{ border-radius: 0 0 10px 10px; }}
    .card h2 {{ font-size: 1rem; font-weight: 700; color: #57606a;
                text-transform: uppercase; letter-spacing: .06em;
                border-bottom: 1px solid #eaecef; padding-bottom: 8px; margin-bottom: 16px; }}

    /* ── Contact ── */
    .contact-row {{ display: flex; flex-wrap: wrap; gap: 16px; }}
    .contact-item {{ display: flex; align-items: center; gap: 6px;
                     color: #57606a; font-size: .9rem; }}
    .contact-item .icon {{ font-size: .85em; opacity: .7; }}

    /* ── Links ── */
    .links-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .link-chip {{ display: inline-flex; align-items: center; gap: 5px;
                  background: #f6f8fa; border: 1px solid #d0d7de;
                  border-radius: 6px; padding: 3px 10px; font-size: .85rem; }}
    .platform-tag {{ font-size: .7rem; color: #57606a; text-transform: uppercase;
                     letter-spacing: .05em; }}

    /* ── Skills ── */
    .skills-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .skill-pill {{ background: #ddf4ff; color: #0969da; border: 1px solid #b6e3ff;
                   border-radius: 20px; padding: 3px 12px; font-size: .85rem; font-weight: 500; }}

    /* ── Experience timeline ── */
    .timeline {{ position: relative; padding-left: 20px; }}
    .timeline::before {{ content: ''; position: absolute; left: 7px; top: 0; bottom: 0;
                         width: 2px; background: #eaecef; }}
    .tl-item {{ position: relative; margin-bottom: 22px; }}
    .tl-item::before {{ content: ''; position: absolute; left: -17px; top: 6px;
                        width: 10px; height: 10px; border-radius: 50%;
                        background: #0969da; border: 2px solid #fff;
                        box-shadow: 0 0 0 2px #0969da; }}
    .tl-title {{ font-weight: 700; font-size: .98rem; }}
    .tl-company {{ color: #57606a; font-size: .9rem; }}
    .tl-dates {{ color: #8b949e; font-size: .82rem; margin-top: 2px; }}
    .tl-desc {{ color: #57606a; font-size: .87rem; margin-top: 6px; line-height: 1.5; }}

    /* ── Education ── */
    .edu-item {{ margin-bottom: 16px; }}
    .edu-degree {{ font-weight: 600; }}
    .edu-inst {{ color: #57606a; }}
    .edu-dates {{ color: #8b949e; font-size: .82rem; }}

    /* ── Metrics table ── */
    .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                     gap: 12px; }}
    .metric-cell {{ background: #f6f8fa; border: 1px solid #eaecef; border-radius: 8px;
                    padding: 12px 16px; text-align: center; }}
    .metric-val {{ font-size: 1.5rem; font-weight: 700; color: #0969da; }}
    .metric-lbl {{ font-size: .78rem; color: #57606a; margin-top: 2px;
                   text-transform: uppercase; letter-spacing: .05em; }}

    /* ── Explanation accordion ── */
    details {{ border: 1px solid #eaecef; border-radius: 6px; margin-bottom: 8px; }}
    summary {{ padding: 10px 14px; cursor: pointer; font-weight: 600; font-size: .9rem;
               list-style: none; display: flex; justify-content: space-between;
               align-items: center; user-select: none; }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::after {{ content: '▸'; color: #8b949e; font-size: .8em; }}
    details[open] summary::after {{ content: '▾'; }}
    .exp-body {{ padding: 10px 14px 12px; font-size: .87rem; color: #57606a;
                 border-top: 1px solid #eaecef; line-height: 1.6; }}
    .exp-row {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
    .exp-key {{ font-weight: 600; color: #24292f; min-width: 160px; }}
    .conf-badge {{ font-weight: 700; }}

    /* ── Warnings ── */
    .warnings {{ background: #fff8c5; border: 1px solid #d4a72c;
                 border-radius: 6px; padding: 12px 16px; font-size: .87rem; }}
    .warnings li {{ margin-left: 18px; margin-top: 4px; }}
  </style>
</head>
<body>
<div class="page">

  <!-- ── Header ── -->
  <div class="header">
    <span class="badge-conf">Confidence: {conf_pct}%</span>
    <h1>{name}</h1>
    {f'<p class="headline">{headline}</p>' if headline else ''}
    <div class="conf-bar-wrap"><div class="conf-bar"></div></div>
  </div>

  <!-- ── Contact ── -->
  <div class="card">
    <h2>Contact</h2>
    <div class="contact-row">
      {emails_html}
      {phones_html}
      {location_html}
    </div>
    {f'<div class="links-row">{links_html}</div>' if links_html else ''}
  </div>

  <!-- ── Skills ── -->
  {f'<div class="card"><h2>Skills</h2><div class="skills-grid">{skills_html}</div></div>' if skills_html else ''}

  <!-- ── Experience ── -->
  {f'<div class="card"><h2>Work Experience</h2><div class="timeline">{exp_html}</div></div>' if exp_html else ''}

  <!-- ── Education ── -->
  {f'<div class="card"><h2>Education</h2>{edu_html}</div>' if edu_html else ''}

  <!-- ── Metrics ── -->
  <div class="card">
    <h2>Pipeline Metrics</h2>
    {metrics_html}
  </div>

  <!-- ── Explanation ── -->
  {f'<div class="card"><h2>Field Explanations</h2>{explain_html}</div>' if explain_html else ''}

  <!-- ── Warnings ── -->
  {f'<div class="card">{warnings_html}</div>' if warnings_html else ''}

</div>
</body>
</html>"""


# ── Section renderers ─────────────────────────────────────────────────────

def _render_contact_items(items: list[str], icon: str) -> str:
    if not items:
        return ""
    return "".join(
        f'<span class="contact-item"><span class="icon">{icon}</span>{_esc(item)}</span>'
        for item in items
    )


def _render_location(location: object | None) -> str:
    if not location:
        return ""
    parts = []
    if hasattr(location, "city") and location.city:
        parts.append(location.city)
    if hasattr(location, "country_code") and location.country_code:
        parts.append(location.country_code)
    if not parts:
        return ""
    text = _esc(", ".join(parts))
    return f'<span class="contact-item"><span class="icon">📍</span>{text}</span>'


def _render_links(links: list) -> str:
    if not links:
        return ""
    parts = []
    for lnk in links:
        url = _esc(lnk.url if hasattr(lnk, "url") else str(lnk))
        platform = _esc((lnk.platform if hasattr(lnk, "platform") else "link") or "link")
        parts.append(
            f'<a class="link-chip" href="{url}" target="_blank" rel="noopener">'
            f'<span class="platform-tag">{platform}</span>{url}'
            f'</a>'
        )
    return "".join(parts)


def _render_skills(skills: list) -> str:
    if not skills:
        return ""
    return "".join(
        f'<span class="skill-pill">{_esc(s.name if hasattr(s, "name") else str(s))}</span>'
        for s in skills
    )


def _render_experience(experience: list) -> str:
    if not experience:
        return ""
    items = []
    for exp in experience:
        title   = _esc(getattr(exp, "title", "") or "")
        company = _esc(getattr(exp, "company", "") or "")
        start   = _esc(getattr(exp, "start_date", "") or "")
        end_val = getattr(exp, "end_date", None)
        is_cur  = getattr(exp, "is_current", False)
        end     = "Present" if is_cur else _esc(end_val or "")
        dates   = f"{start} – {end}" if start or end else ""
        desc    = _esc(getattr(exp, "description", "") or "")
        desc_snippet = desc[:180] + ("…" if len(desc) > 180 else "") if desc else ""

        items.append(f"""
        <div class="tl-item">
          <div class="tl-title">{title}</div>
          <div class="tl-company">{company}</div>
          <div class="tl-dates">{dates}</div>
          {f'<div class="tl-desc">{desc_snippet}</div>' if desc_snippet else ''}
        </div>""")
    return "".join(items)


def _render_education(education: list) -> str:
    if not education:
        return ""
    items = []
    for edu in education:
        degree  = _esc(getattr(edu, "degree", "") or "")
        fos     = _esc(getattr(edu, "field_of_study", "") or "")
        inst    = _esc(getattr(edu, "institution", "") or "")
        start   = _esc(getattr(edu, "start_date", "") or "")
        end     = _esc(getattr(edu, "end_date", "") or "")
        dates   = f"{start} – {end}" if start or end else ""
        deg_str = f"{degree} in {fos}" if fos else degree

        items.append(f"""
        <div class="edu-item">
          <div class="edu-degree">{deg_str}</div>
          <div class="edu-inst">{inst}</div>
          <div class="edu-dates">{dates}</div>
        </div>""")
    return "".join(items)


def _render_metrics(metrics: dict[str, Any]) -> str:
    cells = [
        ("Records Processed",  metrics.get("records_processed", "—")),
        ("Conflicts Resolved", metrics.get("conflicts_resolved", "—")),
        ("Normalized Skills",  metrics.get("normalized_skills", "—")),
        ("Invalid Fields",     metrics.get("invalid_fields", "—")),
        ("Warnings",           metrics.get("warning_count", "—")),
        ("Elapsed (s)",        metrics.get("execution_time_seconds", "—")),
    ]
    cells_html = "".join(
        f'<div class="metric-cell">'
        f'<div class="metric-val">{_esc(str(val))}</div>'
        f'<div class="metric-lbl">{_esc(lbl)}</div>'
        f'</div>'
        for lbl, val in cells
    )
    return f'<div class="metrics-grid">{cells_html}</div>'


def _render_explanation(explanation: dict[str, Any]) -> str:
    if not explanation:
        return ""
    items = []
    for field_key, info in explanation.items():
        if not isinstance(info, dict):
            continue
        value   = _esc(str(info.get("chosen_value", "—") or "—"))
        conf    = info.get("confidence")
        conf_str = f"{conf:.3f}" if isinstance(conf, float) else "—"
        reason  = _esc(info.get("reason", ""))
        had_conflict = info.get("had_conflict", False)
        conflict_tag = ' <span style="color:#cf222e;font-size:.78rem;font-weight:700;">[CONFLICT]</span>' if had_conflict else ""

        alts = info.get("alternatives", [])
        alts_html = ""
        if alts:
            alt_rows = "".join(
                f'<div class="exp-row"><span class="exp-key">{_esc(a.get("source",""))}:</span>'
                f'<span>{_esc(str(a.get("value","—")))}</span></div>'
                for a in alts
            )
            alts_html = f'<div style="margin-top:8px"><strong>Discarded alternatives:</strong>{alt_rows}</div>'

        items.append(f"""
        <details>
          <summary>{_esc(field_key)}{conflict_tag}<span class="conf-badge" style="color:{_confidence_color(float(conf) if isinstance(conf, float) else 0)}">⬤ {conf_str}</span></summary>
          <div class="exp-body">
            <div class="exp-row"><span class="exp-key">Chosen value:</span><span>{value}</span></div>
            <div class="exp-row"><span class="exp-key">Reason:</span><span>{reason}</span></div>
            {alts_html}
          </div>
        </details>""")
    return "".join(items)


def _render_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{_esc(w)}</li>" for w in warnings)
    return f"""
    <div class="warnings">
      <strong>⚠ Pipeline Warnings ({len(warnings)})</strong>
      <ul>{items}</ul>
    </div>"""


# ── Utilities ──────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


def _confidence_color(score: float) -> str:
    """Map a 0–1 confidence score to a hex color."""
    if score >= 0.85:
        return "#1a7f37"   # green
    if score >= 0.65:
        return "#9a6700"   # amber
    return "#cf222e"       # red
