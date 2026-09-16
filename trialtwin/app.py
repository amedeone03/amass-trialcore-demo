"""TrialTwin Streamlit presentation layer.

Protocol construction, ranking, and trial retrieval stay in the backend
modules. This file only renders results.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trialtwin.amass_client import get_historical_trials, load_local_trials
from trialtwin.engine import (
    STATUS_MARK,
    compare_protocol_scenarios,
    rank_historical_trials,
    summarize_historical_neighborhood,
)
from trialtwin.models import HistoricalTrial, Protocol

TOP_K = 5
LOCKED_DISEASE = "Alzheimer's disease"
LOCKED_PHASE = "Phase III"

STATUS_GLYPH = {
    "match": "✓",
    "partial": "~",
    "mismatch": "✗",
    "unknown": "?",
}

FEATURE_LABEL = {
    "disease": "Disease",
    "phase": "Phase",
    "disease_stage": "Stage",
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

OUTCOME_COLORS = {
    "favorable": "#3D9A6A",
    "unfavorable": "#E05A5A",
    "unclear": "#D4A017",
    "unknown": "#8A97AB",
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
    """Show a field or an explicit gap. Never invent a clinical value."""
    if isinstance(value, bool):
        return "Required" if value else "Not required"
    if _is_unreliable(value):
        return "Not available"
    return str(value)


def target_choices(trials: list[HistoricalTrial]) -> list[str]:
    options = []
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
    """Cache Amass/local retrieval. Protocol edits must not refetch."""
    result = get_historical_trials(use_live=use_live)
    return tuple(result.trials), result.source, result.note


def source_caption(source: str) -> tuple[str, str]:
    if source == "LIVE AMASS":
        return "AMASS TRIALCORE", "blue"
    return "LOCAL DEMO DATA", "gray"


def evidence_source_label(source: str) -> str:
    if source == "LIVE AMASS":
        return "Amass TrialCore"
    return "TrialTwin local demo dataset"


def render_why(result) -> None:
    for item in result.feature_comparisons:
        glyph = STATUS_GLYPH[item.status]
        label = FEATURE_LABEL[item.feature_name]
        mark = STATUS_MARK[item.status]
        st.markdown(
            f"{glyph} **{label}** — {mark}  \n"
            f":small[protocol {item.protocol_value} · historical {item.historical_value} "
            f"· contribution {item.contribution:.3f}]"
        )


def render_evidence(trial: HistoricalTrial, source: str) -> None:
    rows = [
        ("Trial", trial.title),
        ("Identifier", trial.id),
        ("Phase", display_value(trial.phase)),
        ("Participants", display_value(trial.sample_size)),
        ("Population / stage", display_value(trial.disease_stage)),
        ("Biomarker", display_value(trial.biomarker_strategy)),
        ("Duration", "Not available" if trial.duration_months is None else f"{trial.duration_months} months"),
        ("Primary endpoint", display_value(trial.primary_endpoint)),
        ("Historical outcome", OUTCOME_BADGE.get(trial.outcome_class, ("UNKNOWN", "gray"))[0]),
        ("Why stopped", display_value(trial.why_stopped)),
        ("Source", evidence_source_label(source)),
    ]
    for label, value in rows:
        st.markdown(f"**{label}**  \n{value}")


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


PARAM_TITLES = {
    "disease_stage": "Disease stage",
    "biomarker_strategy": "Biomarker confirmation",
    "duration_months": "Duration",
    "primary_endpoint": "Primary endpoint",
    "sample_size": "Sample size",
    "target": "Target",
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
    if len(title) > 46:
        return title[:43] + "..."
    return title


def neighborhood_chart(results, title: str) -> go.Figure:
    items = list(reversed(results[:TOP_K]))
    fig = go.Figure()
    for result in items:
        outcome = result.historical_outcome_class
        fig.add_trace(
            go.Bar(
                x=[result.similarity_score * 100],
                y=[short_label(result)],
                orientation="h",
                marker_color=OUTCOME_COLORS.get(outcome, "#8A97AB"),
                name=outcome.upper(),
                hovertemplate=(
                    f"{result.trial_title}<br>"
                    f"Historical similarity: {result.similarity_score * 100:.1f}%"
                    f"<br>Historical outcome: {outcome}<extra></extra>"
                ),
                showlegend=False,
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title="Historical similarity (%)",
        yaxis_title="Historical trial",
        xaxis=dict(range=[0, 100], ticksuffix="%"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(21,29,46,0.65)",
        font=dict(color="#E8EEF7", size=12),
        height=max(260, 52 * len(items) + 80),
        margin=dict(l=16, r=16, t=48, b=40),
        bargap=0.4,
    )
    fig.update_xaxes(gridcolor="#243044", zeroline=False)
    fig.update_yaxes(gridcolor="#243044")
    return fig


def render_rank_list(results) -> None:
    for result in results[:TOP_K]:
        outcome_text, _ = OUTCOME_BADGE.get(result.historical_outcome_class, ("UNKNOWN", "gray"))
        st.markdown(
            f"**{short_label(result)}**  \n"
            f"{result.similarity_score * 100:.1f}% historical similarity · {outcome_text}"
        )


def render_what_if(protocol_a: Protocol, protocol_b: Protocol, trials: list[HistoricalTrial]) -> None:
    if protocol_fingerprint(protocol_a) == protocol_fingerprint(protocol_b):
        with st.container(border=True):
            st.header("What if?")
            st.caption("Change one protocol parameter to recompute the historical neighborhood.")
        return

    comparison = compare_protocol_scenarios(protocol_a, protocol_b, trials, top_k=TOP_K)
    changes = describe_protocol_changes(protocol_a, protocol_b)
    scores_a = {item.trial_id: item.similarity_score for item in comparison.ranking_a}
    scores_b = {item.trial_id: item.similarity_score for item in comparison.ranking_b}
    titles = {item.trial_id: item.trial_title for item in comparison.ranking_a}
    rank_a = {item.trial_id: index + 1 for index, item in enumerate(comparison.ranking_a)}
    rank_b = {item.trial_id: index + 1 for index, item in enumerate(comparison.ranking_b)}

    with st.container(border=True):
        st.header("What if?")
        for title, before, after in changes:
            st.markdown(f"**{title}**")
            st.markdown(f"{before} → {after}")
        st.subheader("Historical neighborhood changed")
        st.markdown(
            "Changing this protocol parameter changed the historical trials "
            "most similar to your design."
        )
        st.caption("This is a recomputation of historical similarity, not a clinical prediction.")

        before_col, after_col = st.columns(2)
        with before_col:
            st.markdown("**Before**")
            st.caption("Top historical designs")
            render_rank_list(comparison.ranking_a)
        with after_col:
            st.markdown("**After**")
            st.caption("Top historical designs")
            render_rank_list(comparison.ranking_b)

        st.markdown("**Neighborhood movement**")
        entered = comparison.top_matches_only_in_b
        left = comparison.top_matches_only_in_a

        def name_for(trial_id: str) -> str:
            raw = titles.get(trial_id, trial_id)
            return raw[:46] + ("..." if len(raw) > 46 else "")

        if entered:
            for trial_id in entered:
                st.markdown(f"Moved into top {TOP_K}: **{name_for(trial_id)}**")
        if left:
            for trial_id in left:
                st.markdown(f"Moved out of top {TOP_K}: **{name_for(trial_id)}**")
        if not entered and not left:
            st.caption(
                f"The same trials remain in the top {TOP_K}. Rank order or similarity values may still have changed."
            )

        moved = []
        for change in comparison.changed_rankings:
            delta_pts = (scores_b[change.trial_id] - scores_a[change.trial_id]) * 100
            if change.rank_a > change.rank_b:
                direction = "Moved up in ranking"
            else:
                direction = "Moved down in ranking"
            sign = "+" if delta_pts >= 0 else ""
            moved.append((change.trial_id, direction, sign, delta_pts, change.rank_a, change.rank_b))
        if moved:
            st.caption("Rank movement uses the full historical list. Similarity change is in percentage points.")
            for trial_id, direction, sign, delta_pts, ra, rb in moved[:12]:
                st.markdown(
                    f"{direction}: **{titles[trial_id][:46]}**  \n"
                    f":small[{ra} → {rb} · similarity changed {sign}{delta_pts:.1f} points]"
                )

        chart_a, chart_b = st.columns(2)
        with chart_a:
            st.plotly_chart(
                neighborhood_chart(comparison.ranking_a, "Before"),
                config={"displayModeBar": False},
            )
        with chart_b:
            st.plotly_chart(
                neighborhood_chart(comparison.ranking_b, "After"),
                config={"displayModeBar": False},
            )
        st.caption(
            "Bar length is historical similarity. Color is historical outcome class "
            "(green favorable, red unfavorable, amber unclear, gray unknown). "
            "Color does not imply causality."
        )

        st.markdown("**Why did the neighborhood change?**")
        if len(changes) == 1:
            st.markdown(f"Changed parameter: **{changes[0][0]}**")
        else:
            st.markdown("Changed parameters: **" + ", ".join(item[0] for item in changes) + "**")
        st.markdown("Effect on similarity:")
        union_ids = list(dict.fromkeys(
            [item.trial_id for item in comparison.ranking_a[:TOP_K]]
            + [item.trial_id for item in comparison.ranking_b[:TOP_K]]
        ))
        deltas = sorted(
            union_ids,
            key=lambda trial_id: abs(scores_b[trial_id] - scores_a[trial_id]),
            reverse=True,
        )
        for trial_id in deltas:
            delta_pts = (scores_b[trial_id] - scores_a[trial_id]) * 100
            sign = "+" if delta_pts >= 0 else ""
            st.markdown(f"**{titles[trial_id][:56]}**  \n{sign}{delta_pts:.1f} points")
        if all(abs(scores_b[trial_id] - scores_a[trial_id]) < 1e-12 for trial_id in deltas):
            st.caption(
                "This parameter did not enter the score for these records "
                "(unknown or unused in the historical data), so the neighborhood ranking stayed the same."
            )
        st.caption("These changes result from the deterministic feature weights used by TrialTwin.")


def render_match_card(result, trial_by_id: dict[str, HistoricalTrial], source: str) -> None:
    outcome_text, outcome_color = OUTCOME_BADGE.get(
        result.historical_outcome_class, ("UNKNOWN", "gray")
    )
    with st.container(border=True):
        title_col, score_col = st.columns([3.4, 1.2], vertical_alignment="center")
        with title_col:
            st.markdown(f"**{result.trial_title}**")
            st.caption(result.trial_id)
            st.badge(outcome_text, color=outcome_color)
        with score_col:
            st.markdown(f"**{result.similarity_score * 100:.1f}%**")
            st.caption("historical similarity")
        with st.expander("Why this match?"):
            render_why(result)
        trial = trial_by_id.get(result.trial_id)
        with st.expander("Evidence"):
            if trial is None:
                st.markdown("Evidence record is not available.")
            else:
                render_evidence(trial, source)


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

    if st.session_state.pop("apply_demo", False):
        st.session_state.matches_requested = True
        st.session_state.demo_pending = True

    cached_trials: tuple[HistoricalTrial, ...] | None = None
    source = ""
    note = ""
    if st.session_state.matches_requested:
        cached_trials, source, note = load_cached_historical_set(True)

    if st.session_state.demo_pending and cached_trials is not None:
        options = target_choices(list(cached_trials)) or ["amyloid-beta"]
        demo_target = "amyloid-beta" if "amyloid-beta" in options else options[0]
        st.session_state.protocol_stage = "Early"
        st.session_state.protocol_duration = 18
        st.session_state.protocol_endpoint = "CDR-SB"
        st.session_state.protocol_n = 1200
        st.session_state.protocol_target = demo_target
        st.session_state.protocol_biomarker = "Not required"
        st.session_state.scenario_a = Protocol(
            disease=LOCKED_DISEASE,
            phase=LOCKED_PHASE,
            target=demo_target,
            disease_stage="Early",
            biomarker_strategy=True,
            sample_size=1200,
            duration_months=18,
            primary_endpoint="CDR-SB",
        )
        st.session_state.demo_pending = False

    st.html(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="stHeader"] { background: transparent; }
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; }
        </style>
        """
    )

    header_left, header_right = st.columns([3, 1], vertical_alignment="center")
    with header_left:
        st.title("TrialTwin")
        st.subheader("Historical Protocol Sandbox")
        st.caption("Explore how your proposed trial compares with historical evidence.")
    with header_right:
        source_placeholder = st.empty()

    protocol_col, neighborhood_col = st.columns([0.42, 0.58], gap="large")

    with protocol_col:
        with st.container(border=True):
            st.header("Your protocol")
            st.caption("Alzheimer’s disease · Phase III are locked for this prototype.")
            st.markdown(f"**Disease**  \n{LOCKED_DISEASE}")
            st.markdown(f"**Phase**  \n{LOCKED_PHASE}")

            stage = st.segmented_control(
                "Disease stage",
                ["Early", "Late"],
                default="Early",
                key="protocol_stage",
            ) or "Early"
            biomarker_label = st.segmented_control(
                "Biomarker",
                ["Required", "Not required"],
                default="Required",
                key="protocol_biomarker",
            ) or "Required"
            duration_months = st.segmented_control(
                "Duration",
                [12, 18, 24, 36],
                default=18,
                key="protocol_duration",
                help="Follow-up duration in months.",
            ) or 18
            endpoint = st.segmented_control(
                "Primary endpoint",
                ["CDR-SB", "ADAS-Cog"],
                default="CDR-SB",
                key="protocol_endpoint",
            ) or "CDR-SB"
            sample_size = st.slider(
                "Sample size",
                min_value=200,
                max_value=4000,
                value=1200,
                step=50,
                key="protocol_n",
            )
            target_source = list(cached_trials) if cached_trials else load_local_trials()
            target_options = target_choices(target_source) or ["amyloid-beta"]
            default_target = "amyloid-beta" if "amyloid-beta" in target_options else target_options[0]
            if st.session_state.get("protocol_target") not in target_options:
                st.session_state.protocol_target = default_target
            target = st.selectbox(
                "Target",
                target_options,
                key="protocol_target",
                help="Options come from the historical dataset. No invented targets.",
            )

            find_col, demo_col = st.columns(2)
            with find_col:
                if st.button(
                    "Find historical matches",
                    type="primary",
                    icon=":material/search:",
                    width="stretch",
                ):
                    st.session_state.matches_requested = True
                    st.session_state.capture_scenario_a = True
                    st.rerun()
            with demo_col:
                if st.button(
                    "Demo scenario",
                    icon=":material/science:",
                    width="stretch",
                    help="Scenario A: biomarker required. Scenario B: biomarker not required.",
                ):
                    st.session_state.apply_demo = True
                    st.rerun()

            st.caption(
                "Historical similarity is a resemblance heuristic. It is not a probability of "
                "success or failure, and historical outcomes are not causal."
            )

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
        if not st.session_state.matches_requested or cached_trials is None:
            source_placeholder.badge("SOURCE PENDING", icon=":material/cloud_off:", color="gray")
            with st.container(border=True):
                st.markdown("Configure a protocol, then find historical matches.")
                st.caption("The first request loads Amass or the local demo dataset. Later edits re-rank locally.")
            return

        trials = cached_trials
        badge_label, badge_color = source_caption(source)
        source_placeholder.badge(badge_label, icon=":material/database:", color=badge_color)
        if note:
            st.caption(note)

        if not trials:
            st.info("No historical trials are available from the current source.")
            return

        ranked = rank_historical_trials(protocol, list(trials))
        summary = summarize_historical_neighborhood(ranked, top_k=TOP_K)
        trial_by_id = {trial.id: trial for trial in trials}

        st.caption("Closest historical neighbors for the current protocol. Colors label historical outcomes only.")
        for result in ranked[:TOP_K]:
            render_match_card(result, trial_by_id, source)

        with st.container(border=True):
            st.subheader("Historical outcome profile")
            st.caption("Outcome profile among closest historical designs. Descriptive evidence only.")
            count_cols = st.columns(4)
            count_cols[0].metric("Favorable", summary.favorable)
            count_cols[1].metric("Unfavorable", summary.unfavorable)
            count_cols[2].metric("Unclear", summary.unclear)
            count_cols[3].metric("Unknown", summary.unknown)
            st.caption(
                "These counts describe nearby historical designs. They are not a "
                "success probability, failure probability, risk score, or prediction."
            )

    protocol_a = st.session_state.scenario_a
    if protocol_a is None:
        protocol_a = protocol
        st.session_state.scenario_a = protocol_a
    render_what_if(protocol_a, protocol, list(trials))


if __name__ == "__main__":
    main()
