import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_data_table, render_bar_chart
from feedback.store import FeedbackStore
from feedback.stats import (
    compute_accuracy_trend,
    compute_confidence_calibration,
    compute_source_effectiveness,
)
from feedback.optimizer import RetrievalOptimizer

inject_styles()

st.title("Self-improvement metrics")
st.caption("How Siren learns from engineer feedback")

store = FeedbackStore()

# Accuracy trend
st.subheader("Accuracy over time")
trend = compute_accuracy_trend(store)
if trend:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[t["date"] for t in trend],
        y=[t["accuracy"] for t in trend],
        mode="lines+markers",
        name="Accuracy",
        line=dict(color="#E84545", width=2),
        marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.0%}<extra></extra>",
    ))
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=0, b=40),
        paper_bgcolor="#0A0A0C",
        plot_bgcolor="#0A0A0C",
        xaxis=dict(showgrid=False, showline=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", range=[0, 1]),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Need more reviewed investigations to show trend.")

# Confidence calibration
st.subheader("Confidence calibration")
st.caption("Does Siren's confidence match its actual accuracy?")
calib = compute_confidence_calibration(store)
if calib:
    df_calib = pd.DataFrame(calib)

    # Create scatter plot
    fig = go.Figure()

    # Confidence calibration scatter
    fig.add_trace(go.Scatter(
        x=df_calib["confidence"],
        y=df_calib["actual_accuracy"],
        mode="markers",
        name="Data",
        marker=dict(
            size=df_calib["sample_size"].apply(lambda x: max(4, min(20, x / 2))),
            color="#E84545",
            opacity=0.6,
        ),
        hovertemplate="Confidence: %{x:.0%}<br>Actual: %{y:.0%}<extra></extra>",
    ))

    # Reference y=x line
    fig.add_trace(go.Scatter(
        x=[0, 1],
        y=[0, 1],
        mode="lines",
        name="Perfect calibration",
        line=dict(color="rgba(255,255,255,0.15)", dash="dash", width=1),
        hoverinfo="skip",
    ))

    fig.update_layout(
        height=400,
        margin=dict(l=40, r=20, t=0, b=40),
        paper_bgcolor="#0A0A0C",
        plot_bgcolor="#0A0A0C",
        xaxis=dict(
            title="Predicted confidence",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            range=[0, 1],
        ),
        yaxis=dict(
            title="Actual accuracy",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            range=[0, 1],
        ),
        hovermode="closest",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Need feedback across multiple confidence levels.")

# Source effectiveness
st.subheader("Tool effectiveness")
st.caption("Which retrieval tools lead to correct investigations?")
sources = compute_source_effectiveness(store)
if sources:
    sources_sorted = sorted(sources, key=lambda x: x["success_rate"], reverse=True)

    rows = []
    for src in sources_sorted:
        tool_name = src["source"]
        usage = src["usage_count"]
        success_rate = src["success_rate"]

        rows.append([
            tool_name,
            str(usage),
            render_bar_chart("", success_rate, 1.0),
        ])

    st.html(render_data_table(
        ["Tool", "Uses", "Success rate"],
        rows,
        classes=["", "col-data", ""],
    ))
else:
    st.info("Collecting tool effectiveness data...")

# Retrain button with confirmation
st.divider()
st.subheader("Retrain retrieval weights")
st.caption("Use collected feedback to adjust which sources get weighted more heavily.")

if "confirm_retrain" not in st.session_state:
    st.session_state.confirm_retrain = False

if not st.session_state.confirm_retrain:
    if st.button("Recompute retrieval weights", key="retrain_initial"):
        st.session_state.confirm_retrain = True
        st.rerun()
else:
    st.warning("⚠️ This will update retrieval weights. Continue?")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("✓ Confirm", key="retrain_confirm"):
            try:
                optimizer = RetrievalOptimizer(store)
                weights = optimizer.recompute_weights()
                st.session_state.confirm_retrain = False

                st.success(f"Updated {len(weights)} (source, incident_type) weights.")

                if weights:
                    weights_list = [
                        {"source": k[0], "incident_type": k[1], "weight": f"{v:.3f}"}
                        for k, v in sorted(weights.items())
                    ]
                    weights_rows = [[w["source"], w["incident_type"], w["weight"]] for w in weights_list]
                    st.html(render_data_table(
                        ["Source", "Type", "Weight"],
                        weights_rows,
                        classes=["", "", "col-data"],
                    ))
            except Exception as e:
                st.error(f"Error retraining: {str(e)}")
                st.session_state.confirm_retrain = False

    with col2:
        if st.button("✗ Cancel", key="retrain_cancel"):
            st.session_state.confirm_retrain = False
            st.rerun()
