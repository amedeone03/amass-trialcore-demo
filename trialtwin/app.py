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
    MatchProfile,
    NeighborhoodShift,
    build_match_profile,
    build_similarity_coverage_points,
    build_spotlight_rank_flow_data,
    calculate_neighborhood_shift,
    scatter_is_informative,
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


def _hex_rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def apply_protocol_to_widgets(protocol: Protocol) -> None:
    st.session_state.protocol_stage = protocol.disease_stage
    st.session_state.protocol_biomarker = "Required" if protocol.biomarker_strategy else "Not required"
    st.session_state.protocol_duration = protocol.duration_months
    st.session_state.protocol_endpoint = protocol.primary_endpoint
    st.session_state.protocol_n = protocol.sample_size
    st.session_state.protocol_intervention = protocol.intervention


def _smooth_path(y0: float, y1: float, steps: int = 28) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for index in range(steps + 1):
        t = index / steps
        eased = t * t * (3.0 - 2.0 * t)
        xs.append(t)
        ys.append(y0 + (y1 - y0) * eased)
    return xs, ys


def _pct(value: float | None, decimals: int) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{decimals}f}%"


def rank_shift_chart(shift: NeighborhoodShift) -> go.Figure:
    flow = build_spotlight_rank_flow_data(shift)
    fig = go.Figure()
    ranks = [
        rank
        for row in flow
        for rank in (row.before_rank, row.after_rank)
        if rank is not None
    ]
    ymax = max(ranks) if ranks else shift.chart_k
    ordered = sorted(
        flow,
        key=lambda row: (row.contextual, row.moved_out_top3, not row.moved_in_top3),
    )
    for row in ordered:
        accent = not row.contextual
        width = 5.2 if accent else 1.8
        node = 22 if accent else 11
        ring = 3 if row.moved_in_top3 else 2 if accent else 1
        color = _hex_rgba(row.color, 1.0 if accent else 0.38)
        glow = _hex_rgba(row.color, 0.18 if accent else 0.06)
        hover_lines = [row.full_title]
        if row.before_rank is not None:
            hover_lines.append(f"Before rank #{row.before_rank}")
        if row.after_rank is not None:
            hover_lines.append(f"After rank #{row.after_rank}")
        if row.before_similarity is not None:
            hover_lines.append(f"Before similarity {_pct(row.before_similarity, 1)}")
        if row.after_similarity is not None:
            hover_lines.append(f"After similarity {_pct(row.after_similarity, 1)}")
        if row.before_coverage is not None:
            hover_lines.append(f"Before coverage {_pct(row.before_coverage, 0)}")
        if row.after_coverage is not None:
            hover_lines.append(f"After coverage {_pct(row.after_coverage, 0)}")
        hover = "<br>".join(hover_lines) + "<extra></extra>"
        if row.before_rank is not None and row.after_rank is not None:
            xs, ys = _smooth_path(float(row.before_rank), float(row.after_rank))
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    line=dict(color=glow, width=width + 10, shape="spline"),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    line=dict(color=color, width=width, shape="spline"),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        node_x: list[float] = []
        node_y: list[float] = []
        if row.before_rank is not None:
            node_x.append(0.0)
            node_y.append(float(row.before_rank))
        if row.after_rank is not None:
            node_x.append(1.0)
            node_y.append(float(row.after_rank))
        if node_x:
            fig.add_trace(
                go.Scatter(
                    x=node_x,
                    y=node_y,
                    mode="markers",
                    marker=dict(
                        size=node,
                        color=color,
                        line=dict(width=ring, color="#E0F2FE" if row.moved_in_top3 else color),
                    ),
                    hovertemplate=hover,
                    showlegend=False,
                    cliponaxis=False,
                )
            )

    annotations = [
        dict(
            x=0,
            y=1.08,
            xref="x",
            yref="paper",
            text="<b>BEFORE</b>",
            showarrow=False,
            font=dict(size=13, color="#67E8F9"),
            xanchor="center",
        ),
        dict(
            x=1,
            y=1.08,
            xref="x",
            yref="paper",
            text="<b>AFTER</b>",
            showarrow=False,
            font=dict(size=13, color="#67E8F9"),
            xanchor="center",
        ),
    ]
    for row in flow:
        label_color = "#E5E7EB" if not row.contextual else "#94A3B8"
        label_size = 13 if not row.contextual else 11
        if row.left_label and row.before_rank is not None:
            annotations.append(
                dict(
                    x=-0.12,
                    y=row.before_rank,
                    xref="x",
                    yref="y",
                    text=row.left_label,
                    showarrow=False,
                    xanchor="right",
                    yanchor="middle",
                    font=dict(size=label_size, color=label_color),
                )
            )
        if row.right_label and row.after_rank is not None:
            annotations.append(
                dict(
                    x=1.12,
                    y=row.after_rank,
                    xref="x",
                    yref="y",
                    text=row.right_label,
                    showarrow=False,
                    xanchor="left",
                    yanchor="middle",
                    font=dict(size=label_size, color=label_color),
                )
            )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8,12,24,0.35)",
        font=dict(color="#E5E7EB", size=12, family="IBM Plex Sans"),
        height=500,
        margin=dict(l=196, r=196, t=48, b=16),
        showlegend=False,
        annotations=annotations,
        xaxis=dict(
            range=[-1.02, 2.02],
            tickvals=[],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            visible=False,
        ),
        yaxis=dict(
            autorange="reversed",
            range=[0.35, ymax + 0.55],
            tickvals=[],
            showticklabels=False,
            title="",
            showgrid=False,
            zeroline=False,
            showline=False,
            ticks="",
            visible=False,
        ),
        shapes=[
            dict(
                type="line",
                x0=0,
                x1=0,
                y0=0.45,
                y1=ymax + 0.35,
                line=dict(color="rgba(103,232,249,0.16)", width=1),
                layer="below",
            ),
            dict(
                type="line",
                x0=1,
                x1=1,
                y0=0.45,
                y1=ymax + 0.35,
                line=dict(color="rgba(103,232,249,0.16)", width=1),
                layer="below",
            ),
        ],
    )
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


def match_profile_chart(profile: MatchProfile) -> go.Figure:
    """Polar display of engine feature resemblance (0–1 shown as 0–100)."""
    labels = [axis.label for axis in profile.axes]
    r_values: list[float | None] = []
    theta_values: list[str] = []
    hover: list[str] = []
    for axis in profile.axes:
        if not axis.available or axis.display_pct is None:
            continue
        r_values.append(axis.display_pct)
        theta_values.append(axis.label)
        hover.append(
            f"{axis.label}<br>Resemblance {axis.display_pct:.0f}%<br>{axis.status}"
        )
    if r_values:
        r_values.append(r_values[0])
        theta_values.append(theta_values[0])
        hover.append(hover[0])

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=r_values,
            theta=theta_values,
            fill="toself",
            mode="lines+markers",
            name="Feature-level resemblance",
            line=dict(color="#A78BFA", width=2),
            fillcolor="rgba(167, 139, 250, 0.28)",
            marker=dict(size=8, color="#22D3EE"),
            hovertext=hover,
            hoverinfo="text",
        )
    )
    ticktext = [
        axis.label if axis.available else f"{axis.label} · unk"
        for axis in profile.axes
    ]
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="rgba(8,12,24,0.45)",
            radialaxis=dict(
                range=[0, 100],
                tickvals=[0, 25, 50, 75, 100],
                showline=False,
                gridcolor="rgba(148,163,184,0.28)",
                tickfont=dict(size=10, color="#9CA3AF"),
            ),
            angularaxis=dict(
                categoryorder="array",
                categoryarray=labels,
                tickvals=labels,
                ticktext=ticktext,
                rotation=90,
                direction="clockwise",
                gridcolor="rgba(148,163,184,0.22)",
                linecolor="rgba(148,163,184,0.35)",
                tickfont=dict(size=11, color="#E5E7EB"),
            ),
        ),
        showlegend=False,
        font=dict(color="#E5E7EB", family="IBM Plex Sans"),
        height=340,
        margin=dict(l=48, r=48, t=28, b=28),
    )
    return fig


def render_why(result) -> None:
    profile = build_match_profile(result)
    st.markdown("**Match profile**")
    st.caption(
        "Feature-level resemblance for this historical match. Missing features are not scored."
    )
    st.caption(
        f"Comparison coverage {result.comparison_coverage * 100:.0f}% · "
        f"{result.comparable_feature_count} / {result.total_feature_count} features available"
    )
    if profile.can_draw:
        st.plotly_chart(match_profile_chart(profile), config={"displayModeBar": False})
    else:
        st.caption(profile.empty_reason)
    status_left, status_right = st.columns(2)
    for index, axis in enumerate(profile.axes):
        target = status_left if index % 2 == 0 else status_right
        target.markdown(f"{axis.label} — {axis.status}")
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
        st.markdown(f"**Synthetic demo metadata**  \nOutcome label: {outcome}")
        st.caption("Synthetic demonstration metadata. Not a live TrialCore classification or prediction.")
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
        title_col, score_col = st.columns([2.6, 1.5], vertical_alignment="center")
        with title_col:
            st.badge(f"Match {rank}", color=rank_color)
            st.markdown(f"**{result.trial_title}**")
            if warning:
                st.badge("LOW COVERAGE", color="orange")
        with score_col:
            st.metric("Historical similarity", f"{result.similarity_score * 100:.1f}%")
            st.metric("Comparison coverage", f"{result.comparison_coverage * 100:.0f}%")
            st.caption(
                f"{result.comparable_feature_count} / {result.total_feature_count} features available"
            )
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
            comparison.ranking_a, comparison.ranking_b, top_k=DISPLAY_TOP, chart_k=6
        )

        st.caption("Protocol changed — historical neighborhood recomputed.")
        with st.container(border=True):
            st.markdown("**One design decision changed**")
            if not changes:
                st.markdown("No labeled protocol fields differ.")
            for title, before, after in changes:
                st.markdown(f"**{title}**")
                st.markdown(f"## {before}  →  {after}")

        st.subheader("Historical neighborhood shift")
        st.html(
            f"""
            <div class="tt-shift-hero">
              <div class="tt-shift-count">{shift.changed_count} of {shift.top_k}</div>
              <div class="tt-shift-kicker">Top historical neighbors changed</div>
            </div>
            """
        )

        if not shift.can_draw:
            st.caption(shift.empty_reason)
        else:
            st.plotly_chart(
                rank_shift_chart(shift),
                use_container_width=True,
                config={"displayModeBar": False},
            )

        st.caption(f"Top match changed: {'Yes' if shift.top_match_changed else 'No'}")
        st.caption("These are neighborhood changes, not improvements.")

        flow = build_spotlight_rank_flow_data(shift)
        moved_in = sorted(
            [row for row in flow if row.moved_in_top3],
            key=lambda row: row.after_rank or 99,
        )
        moved_out = sorted(
            [row for row in flow if row.moved_out_top3],
            key=lambda row: row.before_rank or 99,
        )
        moved_in_col, moved_out_col = st.columns(2)
        with moved_in_col:
            st.caption("MOVED IN")
            if not moved_in:
                st.markdown("None")
            for row in moved_in:
                st.markdown(f"**{row.short_label}**")
        with moved_out_col:
            st.caption("MOVED OUT")
            if not moved_out:
                st.markdown("None")
            for row in moved_out:
                st.markdown(f"**{row.short_label}**")

        with st.expander("Top-3 mean resemblance"):
            st.caption("Secondary context. Not an improvement score.")
            mean_cols = st.columns(2)
            mean_cols[0].markdown(
                f"**Before**  \n"
                f"Top-3 mean historical similarity: {shift.avg_similarity_before * 100:.0f}%  \n"
                f"Top-3 mean comparison coverage: {shift.avg_coverage_before * 100:.0f}%"
            )
            mean_cols[1].markdown(
                f"**After**  \n"
                f"Top-3 mean historical similarity: {shift.avg_similarity_after * 100:.0f}%  \n"
                f"Top-3 mean comparison coverage: {shift.avg_coverage_after * 100:.0f}%"
            )


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
        .block-container { padding-top: 0.55rem; padding-bottom: 1.2rem; max-width: 1440px; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: linear-gradient(180deg, rgba(17,24,39,.94), rgba(11,16,32,.92));
          border: 1px solid rgba(124,58,237,.22) !important;
          box-shadow: 0 18px 50px rgba(0,0,0,.28);
        }
        .tt-hero h1 {
          margin: 0;
          font-size: 2.05rem;
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
        .tt-shift-hero { margin: 0.15rem 0 0.35rem; }
        .tt-shift-count {
          font-size: 2.85rem;
          font-weight: 650;
          letter-spacing: -0.04em;
          line-height: 1.05;
          color: #F5F3FF;
        }
        .tt-shift-kicker {
          color: #67E8F9;
          font-size: 0.78rem;
          font-weight: 650;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          margin-top: 0.15rem;
        }
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
        for index, result in enumerate(ranked[:DISPLAY_TOP], start=1):
            render_match_card(result, trial_by_id, source, index)

    protocol_a = st.session_state.scenario_a or protocol
    st.session_state.scenario_a = protocol_a
    render_what_if(protocol_a, protocol, list(trials))
    points = build_similarity_coverage_points(ranked, list(trials), top_k=DISPLAY_TOP)
    if scatter_is_informative(points):
        with st.expander("Explore evidence"):
            st.plotly_chart(coverage_scatter_chart(points), config={"displayModeBar": False})
            st.caption("Similarity and comparison coverage are separate quantities.")


if __name__ == "__main__":
    main()
