from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
from feedback.store import FeedbackStore

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
df = df[["incident_id", "incident_type", "reported_root_cause", "reported_confidence", "steps_taken", "verdict", "created_at"]]

st.subheader("Filter")
col1, col2 = st.columns(2)
with col1:
    incident_filter = st.multiselect("Type", df["incident_type"].unique(), key="type_filter")
with col2:
    verdict_filter = st.multiselect("Status", df["verdict"].dropna().unique(), key="verdict_filter")

if incident_filter:
    df = df[df["incident_type"].isin(incident_filter)]
if verdict_filter:
    df = df[df["verdict"].isin(verdict_filter)]

st.subheader(f"All cases ({len(df)})")
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()
selected_id = st.selectbox("View details:", df["incident_id"].tolist(), format_func=lambda x: x.split("_")[0])
if selected_id:
    inv = store.get_investigation(selected_id)
    st.subheader("Report")
    st.markdown(inv["final_report"])
