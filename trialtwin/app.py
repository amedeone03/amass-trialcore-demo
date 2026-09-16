"""TrialTwin Streamlit presentation layer. Matching stays in the engine."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trialtwin.amass_client import get_historical_trials, load_local_trials
from trialtwin.engine import (
    compare_protocol_scenarios,
    rank_historical_trials,
    summarize_historical_neighborhood,
)
from trialtwin.models import HistoricalTrial, Protocol

DISPLAY_TOP = 3
LOCKED_DISEASE = "Alzheimer's disease"
LOCKED_PHASE = "Phase III"
PURPLE = "#7C3AED"
CYAN = "#06B6D4"

STATUS_GLYPH = {
    "match": ":green[✓]",
    "partial": ":blue[~]",
    "mismatch": ":red[—]",
    "unknown": ":gray[?]",
}

FEATURE_LABEL = {
    "disease": "Disease",
    "phase": "Phase",
    "disease_stage": "Disease stage",
    "biomarker_strategy": "Biomarker",
    "primary_endpoint": "Endpoint",
    "duration_months": "Duration",
    "sample_size": "Sample size",
    "target": "Target",
}

OUTCOME_BADGE = {
    "favorable": ("FAVORABLE", "green"),
    "unfavorable": ("UNFAVORABLE", "red"),
    "unclear": ("UNCLEAR", "orange"),
    "unknown": ("UNKNOWN", "gray"),
}

PARAM_TITLES = {
    "disease_stage": "Disease stage",
    "biomarker_strategy": "Biomarker confirmation",
    "duration_months": "Duration",
    "primary_endpoint": "Primary endpoint",
    "sample_size": "Sample size",
    "target": "Target",
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


def format_why_value(feature_name: str, raw: str) -> str:
    if raw in {"unknown", "true", "false"} or raw.startswith("ambiguous:"):
        if raw == "true":
            return "Required"
        if raw == "false":
            return "Not required"
        return "Unknown in source data"
    if feature_name == "duration_months" and raw.isdigit():
        return f"{raw} months"
    return raw


def target_choices(trials: list[HistoricalTrial]) -> list[str]:
    options: list[str] = []
    seen: set[str] = set()
    for trial in trials:
        if _is_unreliable(trial.target):
            continue
        if trial.target not in seen:
            seen.add(trial.target)
            options.append(trial.target)
    return options


@st.cache_data(ttl="1h", max_entries=4, show_spinner="Retrieving historical trials...")
def load_cached_historical_set(use_live: bool) -> tuple[tuple[HistoricalTrial, ...], str, str]:
    result = get_historical_trials(use_live=use_live)
    return tuple(result.trials), result.source, result.note


def load_trials_safely() -> tuple[tuple[HistoricalTrial, ...], str, str]:
    try:
        return load_cached_historical_set(True)
    except Exception:
        local = tuple(load_local_trials())
        return local, "LOCAL DEMO DATA", "Live retrieval failed. Showing the TrialTwin prototype dataset."


def source_caption(source: str) -> tuple[str, str]:
    if source == "LIVE AMASS":
        return "AMASS TRIALCORE", "blue"
    return "LOCAL DEMO DATA", "gray"


def evidence_source_label(source: str) -> str:
    if source == "LIVE AMASS":
        return "Amass TrialCore"
    return "TrialTwin prototype dataset"


def build_protocol(
    *,
    stage: str,
    biomarker_label: str,
    duration_months: int,
    endpoint: str,
    sample_size: int,
    target: str,
) -> Protocol:
    return Protocol(
        disease=LOCKED_DISEASE,
        phase=LOCKED_PHASE,
        target=target,
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
        protocol.target,
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
        "target": protocol.target,
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
    return title[:40] + "..." if len(title) > 40 else title


def apply_protocol_to_widgets(protocol: Protocol) -> None:
    st.session_state.protocol_stage = protocol.disease_stage
    st.session_state.protocol_biomarker = "Required" if protocol.biomarker_strategy else "Not required"
    st.session_state.protocol_duration = protocol.duration_months
    st.session_state.protocol_endpoint = protocol.primary_endpoint
    st.session_state.protocol_n = protocol.sample_size
    st.session_state.protocol_target = protocol.target


def neighborhood_shift_score(protocol_a: Protocol, protocol_b: Protocol, trials: list[HistoricalTrial]) -> float:
    comparison = compare_protocol_scenarios(protocol_a, protocol_b, trials, top_k=DISPLAY_TOP)
    set_a = {item.trial_id for item in comparison.ranking_a[:DISPLAY_TOP]}
    set_b = {item.trial_id for item in comparison.ranking_b[:DISPLAY_TOP]}
    changed = len(set_a.symmetric_difference(set_b))
    avg_a = sum(item.similarity_score for item in comparison.ranking_a[:DISPLAY_TOP]) / DISPLAY_TOP
    avg_b = sum(item.similarity_score for item in comparison.ranking_b[:DISPLAY_TOP]) / DISPLAY_TOP
    return changed * 10 + abs(avg_a - avg_b)


def pick_demo_protocols(trials: list[HistoricalTrial], target: str) -> tuple[Protocol, Protocol]:
    """Choose a one-parameter flip that actually moves the neighborhood."""
    base = Protocol(
        disease=LOCKED_DISEASE,
        phase=LOCKED_PHASE,
        target=target,
        disease_stage="Early",
        biomarker_strategy=True,
        sample_size=1200,
        duration_months=18,
        primary_endpoint="CDR-SB",
    )
    candidates = [
        replace(base, biomarker_strategy=False),
        replace(base, duration_months=36),
        replace(base, disease_stage="Late"),
        replace(base, primary_endpoint="ADAS-Cog"),
    ]
    best_b = candidates[0]
    best_score = -1.0
    for candidate in candidates:
        score = neighborhood_shift_score(base, candidate, trials)
        if score > best_score:
            best_score = score
            best_b = candidate
    return base, best_b


def before_after_chart(ranking_a, ranking_b) -> go.Figure:
    scores_a = {item.trial_id: item.similarity_score * 100 for item in ranking_a}
    scores_b = {item.trial_id: item.similarity_score * 100 for item in ranking_b}
    titles = {item.trial_id: short_label(item) for item in list(ranking_a) + list(ranking_b)}
    ordered_ids: list[str] = []
    for item in list(ranking_b[:DISPLAY_TOP]) + list(ranking_a[:DISPLAY_TOP]):
        if item.trial_id not in ordered_ids:
            ordered_ids.append(item.trial_id)
    ordered_ids = list(reversed(ordered_ids))
    labels = [titles[trial_id] for trial_id in ordered_ids]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Before",
            x=[scores_a.get(trial_id, 0.0) for trial_id in ordered_ids],
            y=labels,
            orientation="h",
            marker_color=PURPLE,
            hovertemplate="Before: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="After",
            x=[scores_b.get(trial_id, 0.0) for trial_id in ordered_ids],
            y=labels,
            orientation="h",
            marker_color=CYAN,
            hovertemplate="After: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(
        barmode="group",
        xaxis_title="Historical similarity (%)",
        xaxis=dict(range=[0, 100]),
        legend=dict(orientation="h", y=1.14, bgcolor="rgba(0,0,0,0)"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,12,24,0.55)",
        font=dict(color="#E5E7EB", size=12, family="IBM Plex Sans"),
        height=max(300, 64 * len(ordered_ids) + 96),
        margin=dict(l=8, r=8, t=36, b=36),
        bargap=0.22,
        bargroupgap=0.08,
    )
    fig.update_xaxes(gridcolor="rgba(38,50,68,0.7)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(38,50,68,0.35)")
    return fig


def render_why(result) -> None:
    st.caption(":green[✓] Exact  ·  :blue[~] Similar  ·  :red[—] Different  ·  :gray[?] Unknown")
    lines = [
        "| Feature | Your protocol | Historical trial | |",
        "| --- | --- | --- | --- |",
    ]
    for item in result.feature_comparisons:
        lines.append(
            f"| {FEATURE_LABEL[item.feature_name]} | "
            f"{format_why_value(item.feature_name, item.protocol_value)} | "
            f"{format_why_value(item.feature_name, item.historical_value)} | "
            f"{STATUS_GLYPH[item.status]} |"
        )
    st.markdown("\n".join(lines))


def render_evidence(trial: HistoricalTrial, source: str) -> None:
    duration = (
        "Unknown in source data"
        if trial.duration_months is None
        else f"{trial.duration_months} months"
    )
    rows = [
        ("Phase", display_value(trial.phase)),
        ("Participants", display_value(trial.sample_size)),
        ("Population / disease stage", display_value(trial.disease_stage)),
        ("Biomarker", display_value(trial.biomarker_strategy)),
        ("Duration", duration),
        ("Primary endpoint", display_value(trial.primary_endpoint)),
        ("Historical outcome", OUTCOME_BADGE.get(trial.outcome_class, ("UNKNOWN", "gray"))[0]),
        ("Source", evidence_source_label(source)),
    ]
    for label, value in rows:
        st.markdown(f"**{label}**  \n{value}")


def render_rank_list(results) -> None:
    for result in results[:DISPLAY_TOP]:
        st.markdown(
            f"**{short_label(result)}**  \n"
            f"{result.similarity_score * 100:.1f}%"
        )


def render_match_card(
    result, trial_by_id: dict[str, HistoricalTrial], source: str, rank: int
) -> None:
    outcome_text, outcome_color = OUTCOME_BADGE.get(
        result.historical_outcome_class, ("UNKNOWN", "gray")
    )
    rank_color = "violet" if rank == 1 else "blue" if rank == 2 else "gray"
    with st.container(border=True):
        title_col, score_col = st.columns([3.2, 1.2], vertical_alignment="center")
        with title_col:
            st.badge(f"Match {rank}", color=rank_color)
            st.markdown(f"**{result.trial_title}**")
            st.badge(outcome_text, color=outcome_color)
        with score_col:
            st.metric("Historical similarity", f"{result.similarity_score * 100:.1f}%")
        st.progress(min(max(result.similarity_score, 0.0), 1.0))
        with st.expander("Why this match?", expanded=rank == 1):
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
        st.caption("Change one design choice and see how the historical neighborhood changes.")
        if protocol_fingerprint(protocol_a) == protocol_fingerprint(protocol_b):
            st.markdown("Adjust one control on the left to recompute historical similarity.")
            return

        comparison = compare_protocol_scenarios(protocol_a, protocol_b, trials, top_k=DISPLAY_TOP)
        changes = describe_protocol_changes(protocol_a, protocol_b)
        set_a = {item.trial_id for item in comparison.ranking_a[:DISPLAY_TOP]}
        set_b = {item.trial_id for item in comparison.ranking_b[:DISPLAY_TOP]}
        changed_count = len(set_a - set_b)
        avg_a = sum(item.similarity_score for item in comparison.ranking_a[:DISPLAY_TOP]) / max(len(comparison.ranking_a[:DISPLAY_TOP]), 1)
        avg_b = sum(item.similarity_score for item in comparison.ranking_b[:DISPLAY_TOP]) / max(len(comparison.ranking_b[:DISPLAY_TOP]), 1)
        top_changed = comparison.ranking_a[0].trial_id != comparison.ranking_b[0].trial_id

        for title, before, after in changes:
            st.markdown(f":violet-background[**{title}**]  {before}  →  :blue[**{after}**]")

        st.subheader("Historical neighborhood changed")
        metric_cols = st.columns(3)
        metric_cols[0].metric(f"Top {DISPLAY_TOP} neighbors changed", f"{changed_count} of {DISPLAY_TOP}")
        metric_cols[1].metric("Top match changed", "Yes" if top_changed else "No")
        metric_cols[2].metric(
            "Average similarity",
            f"{avg_b * 100:.1f}%",
            delta=f"{(avg_b - avg_a) * 100:+.1f} points",
            delta_color="off",
        )
        st.caption(
            "Changing this protocol parameter changed the historical trials most similar to your design."
        )

        before_col, after_col = st.columns(2)
        with before_col:
            st.markdown(":violet[**Before**]")
            render_rank_list(comparison.ranking_a)
        with after_col:
            st.markdown(":blue[**After**]")
            render_rank_list(comparison.ranking_b)

        st.plotly_chart(before_after_chart(comparison.ranking_a, comparison.ranking_b), config={"displayModeBar": False})
        st.caption("Bars are historical similarity only (purple = before, cyan = after). Not a clinical outcome.")

        entered = comparison.top_matches_only_in_b
        left = comparison.top_matches_only_in_a
        labels = {
            item.trial_id: short_label(item)
            for item in list(comparison.ranking_a) + list(comparison.ranking_b)
        }
        if entered or left:
            for trial_id in entered:
                st.badge(f"Moved in · {labels.get(trial_id, trial_id)}", color="blue")
            for trial_id in left:
                st.badge(f"Moved out · {labels.get(trial_id, trial_id)}", color="orange")


def main() -> None:
    st.set_page_config(
        page_title="TrialTwin",
        page_icon=":material/biotech:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.session_state.setdefault("matches_requested", False)
    st.session_state.setdefault("scenario_a", None)
    st.session_state.setdefault("demo_pending", False)
    st.session_state.setdefault("protocol_stage", "Early")
    st.session_state.setdefault("protocol_biomarker", "Required")
    st.session_state.setdefault("protocol_duration", 18)
    st.session_state.setdefault("protocol_endpoint", "CDR-SB")
    st.session_state.setdefault("protocol_n", 1200)

    if st.session_state.pop("apply_demo", False):
        st.session_state.matches_requested = True
        st.session_state.demo_pending = True

    cached_trials: tuple[HistoricalTrial, ...] | None = None
    source = ""
    note = ""
    if st.session_state.matches_requested:
        cached_trials, source, note = load_trials_safely()

    if st.session_state.demo_pending and cached_trials is not None:
        options = target_choices(list(cached_trials)) or ["amyloid-beta"]
        demo_target = "amyloid-beta" if "amyloid-beta" in options else options[0]
        protocol_a, protocol_b = pick_demo_protocols(list(cached_trials), demo_target)
        st.session_state.scenario_a = protocol_a
        apply_protocol_to_widgets(protocol_b)
        st.session_state.demo_pending = False

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
        </style>
        <div class="tt-hero">
          <div class="tt-kicker">Amass TrialCore · prototype</div>
          <h1>TrialTwin</h1>
          <p>Explore how a proposed trial compares with historical evidence. Change one design choice and watch the neighborhood move.</p>
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
            ) or 18
            endpoint = st.segmented_control(
                "Primary endpoint",
                ["CDR-SB", "ADAS-Cog"],
                key="protocol_endpoint",
            ) or "CDR-SB"
            sample_size = st.slider("Sample size", min_value=200, max_value=4000, step=50, key="protocol_n")
            target_source = list(cached_trials) if cached_trials else load_local_trials()
            target_options = target_choices(target_source) or ["amyloid-beta"]
            default_target = "amyloid-beta" if "amyloid-beta" in target_options else target_options[0]
            if st.session_state.get("protocol_target") not in target_options:
                st.session_state.protocol_target = default_target
            target = st.selectbox("Target", target_options, key="protocol_target")
            recap = st.container(horizontal=True)
            with recap:
                st.badge(str(stage), color="violet")
                st.badge(str(biomarker_label), color="blue")
                st.badge(f"{duration_months} months")
                st.badge(str(endpoint), color="gray")

            find_col, demo_col = st.columns(2)
            with find_col:
                if st.button("Find historical matches", type="primary", icon=":material/search:", width="stretch"):
                    st.session_state.matches_requested = True
                    st.session_state.capture_scenario_a = True
                    st.rerun()
            with demo_col:
                if st.button("Demo scenario", icon=":material/science:", width="stretch"):
                    st.session_state.apply_demo = True
                    st.rerun()

    protocol = build_protocol(
        stage=stage,
        biomarker_label=biomarker_label,
        duration_months=int(duration_months),
        endpoint=endpoint,
        sample_size=int(sample_size),
        target=target,
    )
    if st.session_state.pop("capture_scenario_a", False):
        st.session_state.scenario_a = protocol

    with neighborhood_col:
        st.header("Historical neighborhood")
        st.caption("Historical trials with the most similar protocol designs.")
        if not st.session_state.matches_requested or cached_trials is None:
            source_placeholder.badge("SOURCE PENDING", color="gray")
            with st.container(border=True):
                st.markdown("### Ready when you are")
                st.markdown("Find historical matches to load evidence, then change **one** design choice.")
                st.caption("Historical similarity is a resemblance heuristic, not a probability of success or failure.")
            return

        trials = cached_trials
        badge_label, badge_color = source_caption(source)
        source_placeholder.badge(badge_label, color=badge_color)
        if note:
            st.caption(note)
        if not trials:
            st.info("No historical trials are available from the current source.")
            return

        ranked = rank_historical_trials(protocol, list(trials))
        summary = summarize_historical_neighborhood(ranked, top_k=DISPLAY_TOP)
        trial_by_id = {trial.id: trial for trial in trials}
        st.caption("Historical similarity is a resemblance heuristic, not a probability of success or failure.")
        for index, result in enumerate(ranked[:DISPLAY_TOP], start=1):
            render_match_card(result, trial_by_id, source, index)

        with st.container(border=True):
            st.markdown("**Historical outcome profile**")
            st.caption("Descriptive counts among the closest historical designs.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Favorable", summary.favorable)
            c2.metric("Unfavorable", summary.unfavorable)
            c3.metric("Unclear", summary.unclear)
            c4.metric("Unknown", summary.unknown)

    protocol_a = st.session_state.scenario_a or protocol
    st.session_state.scenario_a = protocol_a
    render_what_if(protocol_a, protocol, list(trials))


if __name__ == "__main__":
    main()
