import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_data_table
from feedback.store import FeedbackStore
from feedback.stats import compute_accuracy_trend, compute_source_effectiveness
from feedback.optimizer import RetrievalOptimizer

inject_styles()

st.title("Learning & optimization")
st.caption("System performance and improvement")

store = FeedbackStore()

# Accuracy trend
st.subheader("Accuracy over time")
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
else:
    st.info("Not enough data yet")

# Tool effectiveness
st.subheader("Tool effectiveness")
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
    st.html(render_data_table(["Tool", "Uses", "Success"], rows, classes=["", "col-data", "col-data"]))
else:
    st.info("Collecting data...")

# Retrain section
st.divider()
st.subheader("Optimization")

if "confirm_retrain" not in st.session_state:
    st.session_state.confirm_retrain = False

if not st.session_state.confirm_retrain:
    st.caption("Recompute retrieval weights based on feedback")
    if st.button("Recompute weights", type="primary", use_container_width=False):
        st.session_state.confirm_retrain = True
        st.rerun()
else:
    st.warning("⚠️ This will update retrieval weights. Confirm?")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Confirm", key="confirm_retrain_btn"):
            try:
                optimizer = RetrievalOptimizer(store)
                weights = optimizer.recompute_weights()
                st.success(f"Updated {len(weights)} weights")
                st.session_state.confirm_retrain = False
                st.rerun()
            except Exception as e:
                st.error(str(e))
    with col2:
        if st.button("Cancel", key="cancel_retrain_btn"):
            st.session_state.confirm_retrain = False
            st.rerun()
