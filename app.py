"""
Streamlit UI — Multi-Source Candidate Data Transformer.

Run with:
    streamlit run app.py

Layout:
  Sidebar  → File uploads + Run button + About section
  Main     → Tabbed output: Profile | Skills | Experience | Metrics | Explanations | Downloads
"""

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="Candidate Data Transformer",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Multi-Source Candidate Data Transformer — Eightfold AI Assignment"},
)

# ── Inline CSS overrides ───────────────────────────────────────────────────
st.markdown("""
<style>
  /* Tighten page padding */
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
  /* Metric cards */
  [data-testid="metric-container"] {
    background: #f6f8fa; border: 1px solid #d0d7de;
    border-radius: 8px; padding: 12px 16px;
  }
  /* Skill pills */
  .skill-pill {
    display: inline-block; background: #ddf4ff; color: #0969da;
    border: 1px solid #b6e3ff; border-radius: 20px;
    padding: 2px 10px; margin: 3px; font-size: .85rem; font-weight: 500;
  }
  /* Confidence bar */
  .conf-bar-outer {
    background: #eaecef; border-radius: 4px; height: 8px; margin-top: 4px;
  }
  .conf-bar-inner { height: 100%; border-radius: 4px; }
  /* Section header */
  .section-header {
    font-size: .75rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .07em; color: #57606a; margin-top: 0;
  }
  /* Timeline */
  .tl-item { border-left: 2px solid #0969da; padding-left: 14px;
              margin-bottom: 18px; }
  .tl-title { font-weight: 700; font-size: .97rem; }
  .tl-company { color: #57606a; font-size: .88rem; }
  .tl-dates { color: #8b949e; font-size: .8rem; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🎯 Data Transformer")
    st.caption("Multi-Source Candidate Profile Builder")
    st.divider()

    st.subheader("1. Upload Sources")
    csv_file  = st.file_uploader("Recruiter CSV",         type=["csv"],  key="csv_upload")
    pdf_file  = st.file_uploader("Resume PDF",            type=["pdf"],  key="pdf_upload")

    st.subheader("2. Configuration (optional)")
    cfg_file  = st.file_uploader("Projection Config JSON", type=["json"], key="cfg_upload")

    st.divider()
    run_btn = st.button(
        "▶  Run Pipeline",
        use_container_width=True,
        type="primary",
        disabled=(csv_file is None and pdf_file is None),
    )
    st.divider()

    with st.expander("ℹ  How it works"):
        st.markdown("""
        1. Upload a **CSV** (recruiter data) and/or a **PDF** (resume).
        2. Optionally upload a **config.json** to control which fields appear and their output names.
        3. Click **Run Pipeline** — the system extracts, normalises, merges, and projects the data.
        4. Review the profile, download the output files.
        """)


# ═══════════════════════════════════════════════════════════════════════════
# Main area
# ═══════════════════════════════════════════════════════════════════════════

st.title("Multi-Source Candidate Data Transformer")
st.caption("Eightfold AI — Senior Software Engineering Assignment")

if not run_btn:
    # Landing state
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**Step 1** — Upload a recruiter CSV and/or a resume PDF in the sidebar.")
    with c2:
        st.info("**Step 2** — Optionally supply a config.json to rename or exclude fields.")
    with c3:
        st.info("**Step 3** — Click **Run Pipeline** and download the merged profile.")
    st.stop()


# ── Run the pipeline ───────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))

from src.services import PipelineOrchestrator, PipelineInput  # noqa: E402

progress_bar = st.progress(0, text="Starting…")
status_text  = st.empty()

def _on_progress(message: str, pct: int) -> None:
    progress_bar.progress(pct / 100, text=message)
    status_text.caption(f"⏳ {message}")


with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    csv_path = pdf_path = cfg_path = None

    if csv_file:
        csv_path = tmp / Path(csv_file.name).name
        csv_path.write_bytes(csv_file.getvalue())
    if pdf_file:
        pdf_path = tmp / Path(pdf_file.name).name
        pdf_path.write_bytes(pdf_file.getvalue())
    if cfg_file:
        cfg_path = tmp / Path(cfg_file.name).name
        cfg_path.write_bytes(cfg_file.getvalue())

    out_dir = tmp / "outputs"

    try:
        result = PipelineOrchestrator().run(
            PipelineInput(
                csv_path=csv_path,
                resume_path=pdf_path,
                config_path=cfg_path,
                output_dir=out_dir,
            ),
            progress=_on_progress,
        )
    except Exception as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(f"**Pipeline error:** {exc}")
        st.stop()

    progress_bar.empty()
    status_text.empty()

    c = result.candidate

    # ── Header metrics strip ───────────────────────────────────────────────
    st.success(f"Pipeline complete — **{c.full_name or 'Unknown'}** processed in "
               f"{result.metrics.get('execution_time_seconds', 0):.3f}s")

    m1, m2, m3, m4, m5 = st.columns(5)
    conf_pct = int(c.overall_confidence * 100)
    m1.metric("Overall Confidence", f"{conf_pct}%")
    m2.metric("Skills Found",       len(c.skills))
    m3.metric("Experiences",        len(c.experience))
    m4.metric("Educations",         len(c.education))
    m5.metric("Warnings",           len(result.warnings))

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_profile, tab_skills, tab_exp, tab_edu, tab_metrics, tab_explain, tab_json, tab_dl = st.tabs([
        "👤 Profile",
        "🛠 Skills",
        "💼 Experience",
        "🎓 Education",
        "📊 Metrics",
        "🔍 Explanations",
        "{ } Raw JSON",
        "📥 Downloads",
    ])

    # ── TAB: Profile ──────────────────────────────────────────────────────
    with tab_profile:
        col_info, col_conf = st.columns([2, 1])

        with col_info:
            st.markdown(f"## {c.full_name or 'Unknown Candidate'}")
            if c.headline:
                st.markdown(f"*{c.headline}*")

            st.markdown('<p class="section-header">Contact</p>', unsafe_allow_html=True)
            if c.emails:
                st.markdown("**Emails:** " + " | ".join(c.emails))
            if c.phones:
                st.markdown("**Phones:** " + " | ".join(c.phones))
            if c.location:
                parts = []
                if c.location.city:
                    parts.append(c.location.city)
                if c.location.country_code:
                    parts.append(c.location.country_code)
                st.markdown("**Location:** " + ", ".join(parts))
            if c.years_experience is not None:
                st.markdown(f"**Experience:** {c.years_experience:.0f} years")

            if c.links:
                st.markdown('<p class="section-header">Links</p>', unsafe_allow_html=True)
                for lnk in c.links:
                    label = lnk.platform.title() if lnk.platform else "Link"
                    st.markdown(f"🔗 [{label}]({lnk.url})")

        with col_conf:
            st.markdown('<p class="section-header">Confidence Breakdown</p>', unsafe_allow_html=True)
            conf_color = "#1a7f37" if conf_pct >= 85 else "#9a6700" if conf_pct >= 65 else "#cf222e"
            st.markdown(
                f'<div class="conf-bar-outer">'
                f'<div class="conf-bar-inner" style="width:{conf_pct}%;background:{conf_color}"></div>'
                f'</div><p style="color:{conf_color};font-weight:700;font-size:1.3rem;margin-top:6px">'
                f'{conf_pct}%</p>',
                unsafe_allow_html=True,
            )
            for field_name, fc in c.confidence.items():
                score = int(fc.score * 100)
                bar_color = "#1a7f37" if score >= 85 else "#9a6700" if score >= 65 else "#cf222e"
                st.markdown(
                    f'<div style="margin-bottom:8px">'
                    f'<small style="color:#57606a">{field_name}</small>'
                    f'<div class="conf-bar-outer"><div class="conf-bar-inner" '
                    f'style="width:{score}%;background:{bar_color}"></div></div>'
                    f'<small style="color:{bar_color};font-weight:600">{score}%</small></div>',
                    unsafe_allow_html=True,
                )

        if result.warnings:
            st.divider()
            with st.expander(f"⚠ {len(result.warnings)} Warning(s)", expanded=False):
                for w in result.warnings:
                    st.warning(w, icon="⚠️")

    # ── TAB: Skills ───────────────────────────────────────────────────────
    with tab_skills:
        if not c.skills:
            st.info("No skills extracted.")
        else:
            st.markdown(f"**{len(c.skills)} canonical skills** identified:")
            pills = "".join(
                f'<span class="skill-pill">{s.name}</span>'
                for s in sorted(c.skills, key=lambda s: s.name)
            )
            st.markdown(f'<div style="margin-top:12px">{pills}</div>', unsafe_allow_html=True)

            if any(s.raw_name != s.name for s in c.skills):
                st.divider()
                st.caption("Normalisation mapping:")
                rows = [
                    {"Raw Input": s.raw_name, "Canonical Name": s.name}
                    for s in c.skills if s.raw_name != s.name
                ]
                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── TAB: Experience ───────────────────────────────────────────────────
    with tab_exp:
        if not c.experience:
            st.info("No work experience data found.")
        else:
            for exp in c.experience:
                dates = ""
                if exp.start_date:
                    dates = f"{exp.start_date} – {'Present' if exp.is_current else (exp.end_date or '')}"
                st.markdown(
                    f'<div class="tl-item">'
                    f'<div class="tl-title">{exp.title or "(Title unknown)"}</div>'
                    f'<div class="tl-company">{exp.company or "(Company unknown)"}</div>'
                    f'<div class="tl-dates">{dates}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── TAB: Education ────────────────────────────────────────────────────
    with tab_edu:
        if not c.education:
            st.info("No education data found.")
        else:
            for edu in c.education:
                deg = edu.degree or ""
                fos = f" in {edu.field_of_study}" if edu.field_of_study else ""
                dates = f" ({edu.end_date})" if edu.end_date else ""
                st.markdown(f"**{deg}{fos}**{dates}  \n{edu.institution or ''}")
                st.divider()

    # ── TAB: Metrics ──────────────────────────────────────────────────────
    with tab_metrics:
        m = result.metrics
        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.metric("Records Processed",  m.get("records_processed", 0))
        r1c2.metric("Conflicts Resolved", m.get("conflicts_resolved", 0))
        r1c3.metric("Elapsed (s)",        f"{m.get('execution_time_seconds', 0):.3f}")

        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.metric("Normalized Skills",  m.get("normalized_skills", 0))
        r2c2.metric("Invalid Fields",     m.get("invalid_fields", 0))
        r2c3.metric("Validation",         m.get("validation_summary", "—"))

        st.divider()
        st.caption(f"Pipeline version: {m.get('pipeline_version', '—')} | "
                   f"Run at: {m.get('timestamp', '—')}")

    # ── TAB: Explanations ─────────────────────────────────────────────────
    with tab_explain:
        if not result.merge_result.explanation:
            st.info("No explanation data.")
        else:
            for field_name, info in result.merge_result.explanation.items():
                if not isinstance(info, dict):
                    continue
                conf = info.get("confidence")
                had_conflict = info.get("had_conflict", False)
                label = f"🔴 {field_name}" if had_conflict else f"✅ {field_name}"
                with st.expander(
                    f"{label}  —  confidence: {f'{conf:.3f}' if isinstance(conf, float) else '—'}"
                ):
                    st.markdown(f"**Chosen value:** `{info.get('chosen_value', '—')}`")
                    st.markdown(f"**Reason:** {info.get('reason', '—')}")
                    alts = info.get("alternatives", [])
                    if alts:
                        st.markdown("**Discarded alternatives:**")
                        st.dataframe(alts, use_container_width=True, hide_index=True)

    # ── TAB: Raw JSON ─────────────────────────────────────────────────────
    with tab_json:
        st.json(result.projected)

    # ── TAB: Downloads ────────────────────────────────────────────────────
    with tab_dl:
        st.markdown("Download all output artefacts:")
        for key, path in sorted(result.output_paths.items()):
            data = path.read_bytes()
            mime = "text/html" if path.suffix == ".html" else "application/json"
            st.download_button(
                label=f"⬇  {path.name}",
                data=data,
                file_name=path.name,
                mime=mime,
                use_container_width=True,
            )
