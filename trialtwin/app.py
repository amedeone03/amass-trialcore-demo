"""TrialTwin Streamlit presentation layer. Matching stays in the engine."""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trialtwin.amass_client import AmassError, get_historical_trials, load_local_trials
from trialtwin.engine import (
    compare_protocol_scenarios,
    rank_historical_trials,
    summarize_historical_neighborhood,
)
from trialtwin.models import HistoricalTrial, Protocol
from trialtwin.presentation import (
    DATA_CACHE_VERSION,
    DEMO_PROTOCOL_A,
    DEMO_PROTOCOL_B,
    DEMO_SOURCE,
    FEATURE_LABEL,
    PARAM_TITLES,
    candidate_set_caption,
    coverage_line,
    evidence_source_label,
    format_why_value,
    intervention_choices,
    low_coverage_warning,
    migrate_owned_session_state,
    provenance_rows,
    should_show_demo_outcomes,
    source_badge,
    source_is_live,
)
from trialtwin.visualization import (
    NeighborhoodShift,
    build_match_fingerprint,
    build_similarity_coverage_points,
    calculate_neighborhood_shift,
    neighborhood_change_caption,
    shorten_title,
)

DISPLAY_TOP = 3
LOCKED_DISEASE = "Alzheimer's disease"
LOCKED_PHASE = "Phase III"

STATUS_GLYPH = {
    "match": ":green[✓]",
    "partial": ":blue[~]",
    "mismatch": ":red[—]",
    "unknown": ":gray[?]",
}

OUTCOME_BADGE = {
    "favorable": ("FAVORABLE", "green"),
    "unfavorable": ("UNFAVORABLE", "red"),
    "unclear": ("UNCLEAR", "orange"),
    "unknown": ("UNKNOWN", "gray"),
}


def _is_unreliable(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return True
        lowered = text.casefold()
        return lowered == "unknown" or lowered.startswith("ambiguous:")
    return False


def display_value(value: object) -> str:
    if isinstance(value, bool):
        return "Required" if value else "Not required"
    if _is_unreliable(value):
        return "Unknown in source data"
    return str(value)


@st.cache_data(ttl="1h", max_entries=4, show_spinner="Retrieving historical trials...")
def load_cached_historical_set(
    use_live: bool,
    schema_version: str,
) -> tuple[tuple[HistoricalTrial, ...], str, str]:
    """schema_version is unused internally; it is part of the Streamlit cache key."""
    _ = schema_version
    result = get_historical_trials(use_live=use_live)
    return tuple(result.trials), result.source, result.note


def load_trials_safely() -> tuple[tuple[HistoricalTrial, ...], str, str]:
    """Live load with fallback only for expected Amass access failures."""
    try:
        return load_cached_historical_set(True, DATA_CACHE_VERSION)
    except AmassError:
        local = tuple(load_local_trials())
        return (
            local,
            DEMO_SOURCE,
            "Live retrieval failed. Showing synthetic demonstration records.",
        )


def demo_scenario_bundle() -> tuple[
    tuple[HistoricalTrial, ...], str, str, Protocol, Protocol
]:
    """Deterministic Demo scenario. Always local JSON; never calls Amass."""
    trials = tuple(load_local_trials())
    return (
        trials,
        DEMO_SOURCE,
        "Synthetic demonstration records. Not live TrialCore.",
        DEMO_PROTOCOL_A,
        DEMO_PROTOCOL_B,
    )


def build_protocol(
    *,
    stage: str,
    biomarker_label: str,
    duration_months: int,
    endpoint: str,
    sample_size: int,
    intervention: str,
) -> Protocol:
    return Protocol(
        disease=LOCKED_DISEASE,
        phase=LOCKED_PHASE,
        intervention=intervention,
        disease_stage=stage,
        biomarker_strategy=biomarker_label == "Required",
        sample_size=sample_size,
        duration_months=duration_months,
        primary_endpoint=endpoint,
    )


def protocol_fingerprint(protocol: Protocol) -> tuple:
    return (
        protocol.disease,
        protocol.phase,
        protocol.intervention,
        protocol.disease_stage,
        protocol.biomarker_strategy,
        protocol.sample_size,
        protocol.duration_months,
        protocol.primary_endpoint,
    )


def protocol_field_labels(protocol: Protocol) -> dict[str, str]:
    return {
        "disease_stage": protocol.disease_stage,
        "biomarker_strategy": "Required" if protocol.biomarker_strategy else "Not required",
        "duration_months": f"{protocol.duration_months} months",
        "primary_endpoint": protocol.primary_endpoint,
        "sample_size": str(protocol.sample_size),
        "intervention": protocol.intervention,
    }


def describe_protocol_changes(protocol_a: Protocol, protocol_b: Protocol) -> list[tuple[str, str, str]]:
    before = protocol_field_labels(protocol_a)
    after = protocol_field_labels(protocol_b)
    return [
        (PARAM_TITLES[key], before[key], after[key])
        for key in PARAM_TITLES
        if before[key] != after[key]
    ]


def short_label(result) -> str:
    title = result.trial_title.strip() or result.trial_id
    return shorten_title(title, 40)


def apply_protocol_to_widgets(protocol: Protocol) -> None:
    st.session_state.protocol_stage = protocol.disease_stage
    st.session_state.protocol_biomarker = "Required" if protocol.biomarker_strategy else "Not required"
    st.session_state.protocol_duration = protocol.duration_months
    st.session_state.protocol_endpoint = protocol.primary_endpoint
    st.session_state.protocol_n = protocol.sample_size
    st.session_state.protocol_intervention = protocol.intervention


def rank_shift_chart(shift: NeighborhoodShift) -> go.Figure:
    fig = go.Figure()
    ranks = [
        rank
        for row in shift.rows
        for rank in (row.rank_before, row.rank_after)
        if rank is not None
    ]
    ymax = max(ranks) if ranks else shift.chart_k
    for row in shift.rows:
        if row.rank_before is None or row.rank_after is None:
            continue
        dash = "dash" if row.movement != "stayed" else "solid"
        sim_a = "—" if row.similarity_before is None else f"{row.similarity_before * 100:.1f}%"
        sim_b = "—" if row.similarity_after is None else f"{row.similarity_after * 100:.1f}%"
        cov_a = "—" if row.coverage_before is None else f"{row.coverage_before * 100:.0f}%"
        cov_b = "—" if row.coverage_after is None else f"{row.coverage_after * 100:.0f}%"
        fig.add_trace(
            go.Scatter(
                x=["Before", "After"],
                y=[row.rank_before, row.rank_after],
                mode="lines+markers+text",
                name=row.short_title,
                line=dict(color=row.color, width=3, dash=dash),
                marker=dict(size=11, color=row.color),
                text=["", row.short_title],
                textposition="middle right",
                textfont=dict(color="#E5E7EB", size=11),
                hovertemplate=(
                    f"{row.title}<br>"
                    f"Rank {row.rank_before} → {row.rank_after}<br>"
                    f"Similarity {sim_a} → {sim_b}<br>"
                    f"Coverage {cov_a} → {cov_b}"
                    "<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        title=dict(text="Historical neighborhood shift", font=dict(size=16, color="#E5E7EB")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,12,24,0.55)",
        font=dict(color="#E5E7EB", size=12, family="IBM Plex Sans"),
        height=max(320, 56 * max(len(shift.rows), 1) + 80),
        margin=dict(l=48, r=220, t=48, b=40),
        showlegend=False,
        transition=dict(duration=400),
        xaxis=dict(type="category", tickfont=dict(size=13)),
        yaxis=dict(
            title="Rank",
            autorange="reversed",
            dtick=1,
            range=[0.5, ymax + 0.5],
            gridcolor="rgba(38,50,68,0.7)",
            zeroline=False,
        ),
    )
    fig.update_xaxes(gridcolor="rgba(38,50,68,0.35)")
    return fig


def coverage_scatter_chart(points) -> go.Figure:
    fig = go.Figure()
    rest = [point for point in points if not point.is_top]
    top = [point for point in points if point.is_top]
    if rest:
        fig.add_trace(
            go.Scatter(
                x=[point.similarity_pct for point in rest],
                y=[point.coverage_pct for point in rest],
                mode="markers",
                name="Retrieved candidates",
                marker=dict(size=9, color="#64748B"),
                customdata=[[point.title, point.intervention] for point in rest],
                hovertemplate="%{customdata[0]}<br>Similarity %{x:.1f}%<br>Coverage %{y:.0f}%<br>Intervention %{customdata[1]}<extra></extra>",
            )
        )
    if top:
        fig.add_trace(
            go.Scatter(
                x=[point.similarity_pct for point in top],
                y=[point.coverage_pct for point in top],
                mode="markers",
                name="Top matches",
                marker=dict(size=13, color="#A78BFA", line=dict(width=1, color="#22D3EE")),
                customdata=[[point.title, point.intervention] for point in top],
                hovertemplate="%{customdata[0]}<br>Similarity %{x:.1f}%<br>Coverage %{y:.0f}%<br>Intervention %{customdata[1]}<extra></extra>",
            )
        )
    fig.update_layout(
        title=dict(text="Similarity × coverage", font=dict(size=15, color="#E5E7EB")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,12,24,0.55)",
        font=dict(color="#E5E7EB", size=12, family="IBM Plex Sans"),
        height=340,
        margin=dict(l=48, r=16, t=48, b=48),
        legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title="Historical similarity (%)", range=[0, 100], gridcolor="rgba(38,50,68,0.7)"),
        yaxis=dict(title="Comparison coverage (%)", range=[0, 100], gridcolor="rgba(38,50,68,0.7)"),
    )
    return fig


def render_why(result) -> None:
    st.markdown("**Match fingerprint**")
    st.caption("Exact · Similar · Different · Unknown — status only, not a separate score.")
    bars = ['<div class="tt-fp">']
    for row in build_match_fingerprint(result):
        width = row.fill * 10
        bars.append(
            "<div class='tt-fp-row'>"
            f"<span class='tt-fp-label'>{row.label}</span>"
            "<span class='tt-fp-track'>"
            f"<span class='tt-fp-fill' style='width:{width}%'></span>"
            "</span>"
            f"<span class='tt-fp-status'>{row.status}</span>"
            "</div>"
        )
    bars.append("</div>")
    st.html("".join(bars))
    with st.expander("Feature table"):
        lines = [
            "| Feature | Your protocol | Historical trial | Status |",
            "| --- | --- | --- | --- |",
        ]
        for item in result.feature_comparisons:
            status = "Unknown" if item.status == "unknown" else item.status.title()
            lines.append(
                f"| {FEATURE_LABEL[item.feature_name]} | "
                f"{format_why_value(item.feature_name, item.protocol_value)} | "
                f"{format_why_value(item.feature_name, item.historical_value)} | "
                f"{STATUS_GLYPH[item.status]} {status} |"
            )
        st.markdown("\n".join(lines))


def render_evidence(trial: HistoricalTrial, source: str) -> None:
    duration = (
        "Unavailable in TrialCore (not inferred from calendar dates)"
        if trial.duration_months is None
        else f"{trial.duration_months} months"
    )
    span = (
        "Unknown in source data"
        if trial.study_span_months is None
        else f"{trial.study_span_months} months"
    )
    endpoint_raw = trial.primary_endpoint_raw or trial.primary_endpoint
    rows = [
        ("Phase", display_value(trial.phase)),
        ("Participants", display_value(trial.sample_size)),
        ("Population / disease stage", display_value(trial.disease_stage)),
        ("Biomarker", display_value(trial.biomarker_strategy)),
        ("Protocol duration", duration),
        ("Study calendar span", span),
        ("Primary endpoint (canonical)", display_value(trial.primary_endpoint)),
        ("Primary endpoint (source)", display_value(endpoint_raw)),
        ("Intervention", display_value(trial.intervention)),
        ("Source", evidence_source_label(source)),
    ]
    for label, value in rows:
        st.markdown(f"**{label}**  \n{value}")

    if should_show_demo_outcomes(source):
        outcome = OUTCOME_BADGE.get(trial.outcome_class, ("UNKNOWN", "gray"))[0]
        st.markdown(f"**Demo outcome labels**  \n{outcome}")
        st.caption("Synthetic demonstration labels. Not inferred from a live registry status.")
    else:
        st.caption(
            "Validated historical outcome classification is not available from the current TrialCore record."
        )

    for label, value in provenance_rows(trial):
        st.markdown(f"**{label}**  \n{value}")
    if trial.source_url:
        st.link_button("Open original trial record ↗", trial.source_url)
    elif source_is_live(source):
        st.caption("Source URL unavailable")


def render_match_card(
    result, trial_by_id: dict[str, HistoricalTrial], source: str, rank: int
) -> None:
    rank_color = "violet" if rank == 1 else "blue" if rank == 2 else "gray"
    warning = low_coverage_warning(result)
    with st.container(border=True):
        title_col, score_col = st.columns([3.2, 1.2], vertical_alignment="center")
        with title_col:
            st.badge(f"Match {rank}", color=rank_color)
            st.markdown(f"**{result.trial_title}**")
            if should_show_demo_outcomes(source):
                outcome_text, outcome_color = OUTCOME_BADGE.get(
                    result.historical_outcome_class, ("UNKNOWN", "gray")
                )
                st.badge(f"Demo · {outcome_text}", color=outcome_color)
            if warning:
                st.badge("LOW COVERAGE", color="orange")
        with score_col:
            st.metric("Historical similarity", f"{result.similarity_score * 100:.1f}%")
            st.metric("Comparison coverage", coverage_line(result))
        if warning:
            st.caption(warning)
        else:
            st.progress(min(max(result.similarity_score, 0.0), 1.0))
        with st.expander("Why this match?", expanded=False):
            render_why(result)
        trial = trial_by_id.get(result.trial_id)
        with st.expander("Evidence"):
            if trial is None:
                st.markdown("Unknown in source data")
            else:
                render_evidence(trial, source)


def render_what_if(protocol_a: Protocol, protocol_b: Protocol, trials: list[HistoricalTrial]) -> None:
    with st.container(border=True):
        st.header("What if?")
        if protocol_fingerprint(protocol_a) == protocol_fingerprint(protocol_b):
            st.markdown("Adjust one control on the left to recompute historical similarity.")
            return

        comparison = compare_protocol_scenarios(protocol_a, protocol_b, trials, top_k=DISPLAY_TOP)
        if not comparison.ranking_a or not comparison.ranking_b:
            st.info("Not enough historical trials to compare neighborhoods.")
            return

        changes = describe_protocol_changes(protocol_a, protocol_b)
        shift = calculate_neighborhood_shift(
            comparison.ranking_a, comparison.ranking_b, top_k=DISPLAY_TOP, chart_k=5
        )
        labels = {
            item.trial_id: short_label(item)
            for item in list(comparison.ranking_a) + list(comparison.ranking_b)
        }

        st.info("Protocol changed — historical neighborhood recomputed.")
        with st.container(border=True):
            st.markdown("**One design decision changed**")
            if not changes:
                st.markdown("No labeled protocol fields differ.")
            for title, before, after in changes:
                st.markdown(f"### {title}")
                st.markdown(f"## {before}  →  {after}")

        st.subheader("Historical neighborhood shift")
        st.markdown(f"# {shift.changed_count} of {shift.top_k}")
        st.markdown("**top historical neighbors changed**")
        st.caption(
            f"{neighborhood_change_caption(shift)}. "
            f"Top match changed: {'yes' if shift.top_match_changed else 'no'}. "
            "These are neighborhood changes, not improvements."
        )

        context = st.container(horizontal=True)
        with context:
            st.markdown(
                f"**Before**  \nAverage similarity: {shift.avg_similarity_before * 100:.0f}%  \n"
                f"Average coverage: {shift.avg_coverage_before * 100:.0f}%"
            )
            st.markdown(
                f"**After**  \nAverage similarity: {shift.avg_similarity_after * 100:.0f}%  \n"
                f"Average coverage: {shift.avg_coverage_after * 100:.0f}%"
            )

        if not shift.can_draw:
            st.caption(shift.empty_reason)
        else:
            st.plotly_chart(rank_shift_chart(shift), config={"displayModeBar": False})

        badge_row = st.container(horizontal=True)
        with badge_row:
            for trial_id in shift.moved_in_ids:
                st.badge(f"Moved in · {labels.get(trial_id, trial_id)}", color="blue")
            for trial_id in shift.moved_out_ids:
                st.badge(f"Moved out · {labels.get(trial_id, trial_id)}", color="gray")


def main() -> None:
    st.set_page_config(
        page_title="TrialTwin",
        page_icon=":material/biotech:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    migrate_owned_session_state(st.session_state)
    st.session_state.setdefault("matches_requested", False)
    st.session_state.setdefault("scenario_a", None)
    st.session_state.setdefault("demo_pending", False)
    st.session_state.setdefault("current_mode", "live")
    st.session_state.setdefault("protocol_stage", "Early")
    st.session_state.setdefault("protocol_biomarker", "Required")
    st.session_state.setdefault("protocol_duration", 18)
    st.session_state.setdefault("protocol_endpoint", "CDR-SB")
    st.session_state.setdefault("protocol_n", 1200)

    if st.session_state.pop("apply_demo", False):
        st.session_state.current_mode = "demo"
        st.session_state.matches_requested = True
        st.session_state.demo_pending = True

    cached_trials: tuple[HistoricalTrial, ...] | None = None
    source = ""
    note = ""
    if st.session_state.matches_requested:
        if st.session_state.get("current_mode") == "demo":
            cached_trials, source, note, protocol_a_demo, protocol_b_demo = demo_scenario_bundle()
            if st.session_state.demo_pending:
                st.session_state.scenario_a = protocol_a_demo
                apply_protocol_to_widgets(protocol_b_demo)
                st.session_state.demo_pending = False
        else:
            cached_trials, source, note = load_trials_safely()

    st.html(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="stHeader"] { background: transparent; }
        .stApp {
          background:
            radial-gradient(1100px 460px at 8% -8%, rgba(124,58,237,.34), transparent 56%),
            radial-gradient(900px 380px at 96% 0%, rgba(6,182,212,.18), transparent 52%),
            #070b16;
        }
        .block-container { padding-top: 1rem; padding-bottom: 2.4rem; max-width: 1440px; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: linear-gradient(180deg, rgba(17,24,39,.94), rgba(11,16,32,.92));
          border: 1px solid rgba(124,58,237,.22) !important;
          box-shadow: 0 18px 50px rgba(0,0,0,.28);
        }
        .tt-hero h1 {
          margin: 0;
          font-size: 2.35rem;
          letter-spacing: -0.04em;
          background: linear-gradient(90deg, #F5F3FF 10%, #A78BFA 55%, #22D3EE 100%);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        .tt-hero p { margin: .35rem 0 0; color: #9CA3AF; }
        .tt-kicker {
          color: #67E8F9;
          font-size: .72rem;
          font-weight: 600;
          letter-spacing: .16em;
          text-transform: uppercase;
        }
        div[data-testid="stProgressBar"] > div { background: linear-gradient(90deg, #7C3AED, #06B6D4); }
        .tt-fp { display: flex; flex-direction: column; gap: 0.45rem; margin: 0.35rem 0 0.6rem; }
        .tt-fp-row { display: grid; grid-template-columns: 7.2rem minmax(4rem,1fr) 5.2rem; gap: 0.7rem; align-items: center; }
        .tt-fp-label { color: #D1D5DB; font-size: 0.86rem; }
        .tt-fp-track { height: 0.55rem; border-radius: 999px; background: rgba(148,163,184,.22); overflow: hidden; }
        .tt-fp-fill { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7C3AED, #22D3EE); }
        .tt-fp-status { color: #A5B4FC; font-size: 0.8rem; letter-spacing: .04em; text-transform: uppercase; }
        </style>
        <div class="tt-hero">
          <div class="tt-kicker">DTU Skylab × Cursor × Amass · Hackathon prototype</div>
          <h1>TrialTwin</h1>
          <p>Change your protocol, and see which historical trials it starts to resemble.</p>
        </div>
        """
    )

    header_left, header_right = st.columns([3.2, 1.1], vertical_alignment="center")
    with header_left:
        st.caption("Alzheimer's disease · Phase III historical protocol sandbox")
    with header_right:
        st.badge("PROTOTYPE", color="violet")
        source_placeholder = st.empty()

    protocol_col, neighborhood_col = st.columns([0.40, 0.60], gap="medium")

    with protocol_col:
        with st.container(border=True):
            st.header("Your hypothetical protocol")
            st.caption(f"{LOCKED_DISEASE} · {LOCKED_PHASE}")

            stage = st.segmented_control("Disease stage", ["Early", "Late"], key="protocol_stage") or "Early"
            biomarker_label = st.segmented_control(
                "Biomarker confirmation",
                ["Required", "Not required"],
                key="protocol_biomarker",
            ) or "Required"
            duration_months = st.segmented_control(
                "Duration (months)",
                [12, 18, 24, 36],
                key="protocol_duration",
                help="Protocol duration is compared only when a semantically equivalent historical duration is available.",
            ) or 18
            endpoint = st.segmented_control(
                "Primary endpoint",
                ["CDR-SB", "ADAS-Cog"],
                key="protocol_endpoint",
            ) or "CDR-SB"
            sample_size = st.slider("Sample size", min_value=200, max_value=4000, step=50, key="protocol_n")
            intervention_source = list(cached_trials) if cached_trials else load_local_trials()
            intervention_options = intervention_choices(intervention_source) or ["amyloid-beta"]
            default_intervention = (
                "amyloid-beta" if "amyloid-beta" in intervention_options else intervention_options[0]
            )
            if st.session_state.get("protocol_intervention") not in intervention_options:
                st.session_state.protocol_intervention = default_intervention
            intervention = st.selectbox("Intervention", intervention_options, key="protocol_intervention")
            recap = st.container(horizontal=True)
            with recap:
                st.badge(str(stage), color="violet")
                st.badge(str(biomarker_label), color="blue")
                st.badge(f"{duration_months} months")
                st.badge(str(endpoint), color="gray")

            find_col, demo_col = st.columns(2)
            with find_col:
                if st.button("Find historical matches", type="primary", icon=":material/search:", width="stretch"):
                    st.session_state.current_mode = "live"
                    st.session_state.matches_requested = True
                    st.session_state.capture_scenario_a = True
                    st.rerun()
            with demo_col:
                if st.button("Run demo", icon=":material/science:", width="stretch"):
                    st.session_state.apply_demo = True
                    st.rerun()

    protocol = build_protocol(
        stage=stage,
        biomarker_label=biomarker_label,
        duration_months=int(duration_months),
        endpoint=endpoint,
        sample_size=int(sample_size),
        intervention=intervention,
    )
    if st.session_state.pop("capture_scenario_a", False):
        st.session_state.scenario_a = protocol

    with neighborhood_col:
        st.header("Historical neighborhood")
        if not st.session_state.matches_requested or cached_trials is None:
            source_placeholder.badge("SOURCE PENDING", color="gray")
            with st.container(border=True):
                st.markdown("### Ready when you are")
                st.markdown("Find historical matches for live TrialCore, or **Run demo** for a local synthetic walkthrough.")
            return

        trials = cached_trials
        badge_label, badge_color = source_badge(source)
        source_placeholder.badge(badge_label, color=badge_color)
        st.caption(candidate_set_caption(len(trials)))
        if note:
            st.caption(note)
        if not trials:
            st.info("No historical trials are available from the current source.")
            return

        ranked = rank_historical_trials(protocol, list(trials))
        trial_by_id = {trial.id: trial for trial in trials}
        st.caption(
            "Similarity measures historical resemblance. Coverage shows how much comparable data was available."
        )
        for index, result in enumerate(ranked[:DISPLAY_TOP], start=1):
            render_match_card(result, trial_by_id, source, index)

        if should_show_demo_outcomes(source):
            summary = summarize_historical_neighborhood(ranked, top_k=DISPLAY_TOP)
            with st.expander("Demo outcome labels"):
                st.caption("Synthetic demonstration counts. Not a live TrialCore classification.")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Favorable", summary.favorable)
                c2.metric("Unfavorable", summary.unfavorable)
                c3.metric("Unclear", summary.unclear)
                c4.metric("Unknown", summary.unknown)
        else:
            st.caption(
                "Validated historical outcome classification is not available from the current TrialCore record."
            )

    protocol_a = st.session_state.scenario_a or protocol
    st.session_state.scenario_a = protocol_a
    render_what_if(protocol_a, protocol, list(trials))
    points = build_similarity_coverage_points(ranked, list(trials), top_k=DISPLAY_TOP)
    with st.expander("Explore evidence"):
        if points:
            st.plotly_chart(coverage_scatter_chart(points), config={"displayModeBar": False})
            st.caption("Similarity and comparison coverage are separate quantities.")
        else:
            st.caption("No candidates to plot.")


if __name__ == "__main__":
    main()
