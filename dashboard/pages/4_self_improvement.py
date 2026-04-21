from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import altair as alt

from feedback.store import FeedbackStore
from feedback.stats import (
    compute_accuracy_trend,
    compute_confidence_calibration,
    compute_source_effectiveness,
)
from feedback.optimizer import RetrievalOptimizer


st.title("Self-improvement metrics")
st.caption("How Siren learns from engineer feedback")

store = FeedbackStore()

# Accuracy trend
st.subheader("Accuracy over time")
trend = compute_accuracy_trend(store)
if trend:
    df = pd.DataFrame(trend)
    chart = alt.Chart(df).mark_line(point=True).encode(
        x="date:T", y=alt.Y("accuracy:Q", scale=alt.Scale(domain=[0, 1])),
        tooltip=["date", "accuracy", "total"],
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("Need more reviewed investigations to show trend.")

# Confidence calibration
st.subheader("Confidence calibration")
st.caption("Does Siren's confidence match its actual accuracy?")
calib = compute_confidence_calibration(store)
if calib:
    df = pd.DataFrame(calib)
    chart = alt.Chart(df).mark_circle(size=100).encode(
        x=alt.X("confidence:Q", scale=alt.Scale(domain=[0, 1]), title="Predicted confidence"),
        y=alt.Y("actual_accuracy:Q", scale=alt.Scale(domain=[0, 1]), title="Actual accuracy"),
        size="sample_size:Q",
        tooltip=["confidence", "actual_accuracy", "sample_size"],
    )
    # Overlay y=x reference line
    line = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        strokeDash=[5, 5], color="gray"
    ).encode(x="x", y="y")
    st.altair_chart(chart + line, use_container_width=True)
else:
    st.info("Need feedback across multiple confidence levels.")

# Source effectiveness
st.subheader("Tool effectiveness")
st.caption("Which retrieval tools lead to correct investigations?")
sources = compute_source_effectiveness(store)
if sources:
    df = pd.DataFrame(sources).sort_values("success_rate", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Collecting tool effectiveness data...")

# Retrain button
st.divider()
st.subheader("Retrain retrieval weights")
st.caption("Use collected feedback to adjust which sources get weighted more heavily.")
if st.button("Recompute retrieval weights"):
    optimizer = RetrievalOptimizer(store)
    weights = optimizer.recompute_weights()
    st.success(f"Updated {len(weights)} (source, incident_type) weights.")
    if weights:
        weights_df = pd.DataFrame([
            {"source": k[0], "incident_type": k[1], "weight": v}
            for k, v in weights.items()
        ])
        st.dataframe(weights_df, use_container_width=True, hide_index=True)
