import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_data_table, render_kpi_strip
from feedback.store import FeedbackStore
from feedback.stats import compute_accuracy_trend, compute_source_effectiveness
from feedback.optimizer import RetrievalOptimizer

inject_styles()

st.title("System analysis")
st.caption("Performance metrics and improvement recommendations")

store = FeedbackStore()
investigations = store.list_investigations(limit=500)

# Filter out seed investigations
investigations = [i for i in investigations if "seed" not in i.get("incident_id", "").lower()]

if not investigations:
    st.info("No investigations yet")
    st.stop()

reviewed = [i for i in investigations if i.get("verdict")]
failures = [i for i in reviewed if i.get("verdict") == "incorrect"]
high_conf_failures = [f for f in failures if f.get("reported_confidence", 0) > 0.7]

# Performance summary
st.subheader("Performance summary")
kpi_metrics = [
    {"label": "Total reviewed", "value": str(len(reviewed)), "delta": None},
    {"label": "Failures", "value": str(len(failures)), "delta": None},
    {"label": "High-conf errors", "value": str(len(high_conf_failures)), "delta": None},
]
st.html(render_kpi_strip(kpi_metrics))

st.divider()

# Accuracy trend
st.subheader("Accuracy trend")
trend = compute_accuracy_trend(store)
if trend and len(trend) > 0:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[t["date"] for t in trend],
        y=[t["accuracy"] for t in trend],
        mode="lines+markers",
        line=dict(color="#E84545", width=2),
        marker=dict(size=8, line=dict(color="#0A0A0C", width=2)),
        hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.0%}<extra></extra>",
    ))
    fig.update_layout(
        height=250,
        margin=dict(l=40, r=20, t=0, b=40),
        paper_bgcolor="#0A0A0C",
        plot_bgcolor="#0A0A0C",
        xaxis=dict(showgrid=False, showline=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", range=[0, 1]),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# Failure analysis - PROMINENT
st.subheader("Failures")
st.caption("Identifies incorrect investigations to find patterns and improve detection logic")

if failures:
    failure_rows = []
    for inv in sorted(failures, key=lambda x: -x.get("reported_confidence", 0))[:15]:
        failure_rows.append([
            str(inv.get("created_at", "—"))[:10],
            inv.get("incident_type", "—"),
            f"{inv.get('reported_confidence', 0):.0%}",
            inv.get("reported_root_cause", "—")[:35],
        ])

    st.html(render_data_table(
        ["Date", "Type", "Confidence", "Predicted"],
        failure_rows,
        classes=["", "", "col-data", "col-muted"],
    ))

    # Key insight
    if high_conf_failures:
        st.warning(
            f"Systematic issue detected: {len(high_conf_failures)} failures with >70% confidence. "
            f"System is overconfident. Review retrieval sources."
        )

st.divider()

# Confidence gaps - ACTIONABLE
st.subheader("Confidence gaps")
st.caption("Shows high-confidence predictions that were wrong")

if high_conf_failures:
    gap_rows = []
    for inv in sorted(high_conf_failures, key=lambda x: -x.get("reported_confidence", 0))[:10]:
        gap_rows.append([
            str(inv.get("created_at", "—"))[:10],
            f"{inv.get('reported_confidence', 0):.0%}",
            inv.get("incident_type", "—"),
            inv.get("reported_root_cause", "—")[:25],
            inv.get("correct_root_cause", "—")[:25],
        ])

    st.html(render_data_table(
        ["Date", "Conf", "Type", "Predicted", "Actual"],
        gap_rows,
        classes=["", "col-data", "", "col-muted", "col-muted"],
    ))
else:
    st.success("No high-confidence errors detected")

st.divider()

# Tool effectiveness
st.subheader("Tool effectiveness")
st.caption("Measures which retrieval tools contribute to successful investigations")

sources = compute_source_effectiveness(store)
if sources:
    sources_sorted = sorted(sources, key=lambda x: x["success_rate"], reverse=True)
    rows = []
    for src in sources_sorted:
        rows.append([
            src["source"],
            str(src["usage_count"]),
            f"{src['success_rate']:.0%}",
        ])
    st.html(render_data_table(
        ["Tool", "Uses", "Success"],
        rows,
        classes=["", "col-data", "col-data"],
    ))

    # Recommendation
    underperformers = [s for s in sources_sorted if s["success_rate"] < 0.5]
    if underperformers:
        st.info(
            f"Consider disabling or improving: {', '.join(s['source'] for s in underperformers)}"
        )
else:
    st.info("Collecting data...")

st.divider()

# Retraining
st.subheader("Optimization")
st.caption("Update retrieval weights based on feedback to improve future investigations")

if "confirm_retrain" not in st.session_state:
    st.session_state.confirm_retrain = False

if not st.session_state.confirm_retrain:
    if st.button("Recompute weights", type="primary"):
        st.session_state.confirm_retrain = True
        st.rerun()
else:
    st.warning("Recompute retrieval weights?")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Confirm"):
            try:
                optimizer = RetrievalOptimizer(store)
                weights = optimizer.recompute_weights()
                st.success(f"Weights updated: {len(weights)} source-type pairs optimized")
                st.session_state.confirm_retrain = False
                st.rerun()
            except Exception as e:
                st.error(str(e))
    with col2:
        if st.button("Cancel"):
            st.session_state.confirm_retrain = False
            st.rerun()
