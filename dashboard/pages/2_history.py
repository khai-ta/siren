import streamlit as st
import pandas as pd
from feedback.store import FeedbackStore

st.title("Investigation history")

store = FeedbackStore()
investigations = store.list_investigations(limit=500)

if not investigations:
    st.info("No investigations yet. Run one from the Live incident page.")
    st.stop()

df = pd.DataFrame(investigations)
df = df[["incident_id", "incident_type", "reported_root_cause", "reported_confidence", "steps_taken", "verdict", "created_at"]]

# Filter controls
col1, col2 = st.columns(2)
with col1:
    incident_filter = st.multiselect("Filter by incident type", df["incident_type"].unique())
with col2:
    verdict_filter = st.multiselect("Filter by verdict", df["verdict"].dropna().unique())

if incident_filter:
    df = df[df["incident_type"].isin(incident_filter)]
if verdict_filter:
    df = df[df["verdict"].isin(verdict_filter)]

st.dataframe(df, use_container_width=True, hide_index=True)

# Click-to-view details
st.divider()
selected_id = st.selectbox("View investigation details:", df["incident_id"].tolist())
if selected_id:
    inv = store.get_investigation(selected_id)
    st.markdown(inv["final_report"])
