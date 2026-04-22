import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_data_table, render_status_dot
from feedback.store import FeedbackStore

inject_styles()

st.title("Past investigations")

try:
    store = FeedbackStore()
    investigations = store.list_investigations(limit=500)
except Exception as e:
    st.error("Cannot connect to database. Make sure PostgreSQL is running.")
    st.stop()

if not investigations:
    st.info("No past investigations. Start a new one from Investigate an incident.")
    st.stop()

df = pd.DataFrame(investigations)

# Filter section
st.subheader("Filter")
col1, col2 = st.columns(2)

with col1:
    st.write("**Type**")
    type_options = sorted(df["incident_type"].unique().tolist())
    type_selected = st.multiselect(
        "Filter by type",
        type_options,
        label_visibility="collapsed",
        key="type_filter",
    )

with col2:
    st.write("**Status**")
    verdict_options = sorted([v for v in df["verdict"].dropna().unique().tolist()])
    verdict_selected = st.multiselect(
        "Filter by status",
        verdict_options,
        label_visibility="collapsed",
        key="verdict_filter",
    )

# Apply filters
filtered_df = df.copy()
if type_selected:
    filtered_df = filtered_df[filtered_df["incident_type"].isin(type_selected)]
if verdict_selected:
    filtered_df = filtered_df[filtered_df["verdict"].isin(verdict_selected)]

# Investigations table
st.subheader(f"All cases ({len(filtered_df)})")

if len(filtered_df) > 0:
    rows = []
    for _, inv in filtered_df.iterrows():
        date_str = str(inv.get("created_at", "—"))[:10]
        inv_type = inv.get("incident_type", "—")
        root_cause = inv.get("reported_root_cause", "—")[:60]
        confidence = inv.get("reported_confidence", 0)
        verdict = inv.get("verdict")

        rows.append([
            date_str,
            inv_type,
            root_cause,
            f"{confidence:.0%}",
            f"{render_status_dot(verdict)} {verdict or '—'}",
        ])

    st.html(render_data_table(
        ["Date", "Type", "Root cause", "Confidence", "Status"],
        rows,
        classes=["", "", "", "col-data", "col-muted"],
    ))
else:
    st.info("No investigations match the filter criteria.")

# Detail view
st.divider()
st.subheader("Investigation details")

selected_id = st.selectbox(
    "Select an investigation:",
    filtered_df["incident_id"].tolist() if len(filtered_df) > 0 else [],
    format_func=lambda x: x.split("_")[0] if isinstance(x, str) else str(x),
    label_visibility="collapsed",
)

if selected_id:
    inv = store.get_investigation(selected_id)
    if inv:
        with st.expander("View full report", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Reported confidence", f"{inv.get('reported_confidence', 0):.0%}")
            with col2:
                st.metric("Steps taken", inv.get("steps_taken", 0))
            with col3:
                feedback = store.get_feedback_for_incident(selected_id)
                if feedback:
                    st.metric("Verdict", feedback.get("verdict", "—"))
                else:
                    st.metric("Verdict", "—")

            st.divider()
            st.markdown(inv.get("final_report", "No report available"))

            if feedback := store.get_feedback_for_incident(selected_id):
                st.divider()
                st.subheader("Engineer feedback")
                st.write(f"**Verdict:** {feedback.get('verdict')}")
                if feedback.get("correct_root_cause"):
                    st.write(f"**Actual root cause:** {feedback.get('correct_root_cause')}")
                if feedback.get("engineer_notes"):
                    st.write(f"**Notes:** {feedback.get('engineer_notes')}")
