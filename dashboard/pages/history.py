import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_data_table, render_status_dot
from feedback.store import FeedbackStore

inject_styles()

st.title("Investigation history")
st.caption("Review past investigations and system verdicts")

try:
    store = FeedbackStore()
    investigations = store.list_investigations(limit=500)
except Exception as e:
    st.error("Cannot connect to database.")
    st.stop()

# Filter out seed investigations
investigations = [i for i in investigations if "seed" not in i.get("incident_id", "").lower()]

if not investigations:
    st.info("No investigations yet.")
    st.stop()

# Filters
st.write("**Filter results:**")
col1, col2 = st.columns(2)
with col1:
    type_filter = st.multiselect(
        "Type",
        sorted(set(i["incident_type"] for i in investigations)),
        label_visibility="collapsed",
    )
with col2:
    verdict_filter = st.multiselect(
        "Verdict",
        sorted(set(i["verdict"] for i in investigations if i.get("verdict"))),
        label_visibility="collapsed",
    )

# Apply filters
filtered = investigations
if type_filter:
    filtered = [i for i in filtered if i["incident_type"] in type_filter]
if verdict_filter:
    filtered = [i for i in filtered if i.get("verdict") in verdict_filter]

# Tabs for cases and details
tab1, tab2 = st.tabs(["Cases", "Details"])

with tab1:
    # Search filter
    search_query = st.text_input(
        "Search",
        placeholder="Search by date, type, or root cause",
        label_visibility="collapsed",
    )

    # Apply search filter
    searched = filtered
    if search_query:
        search_lower = search_query.lower()
        searched = [i for i in filtered if (
            search_lower in str(i.get("created_at", "")).lower() or
            search_lower in str(i.get("incident_type", "")).lower() or
            search_lower in str(i.get("reported_root_cause", "")).lower()
        )]

    st.subheader(f"Cases ({len(searched)})")

    # Build simple table
    rows = []
    for inv in sorted(searched, key=lambda x: x.get("created_at", ""), reverse=True):
        verdict_text = inv.get("verdict", "pending")
        rows.append([
            str(inv.get("created_at", "—"))[:10],
            inv.get("incident_type", "—"),
            f"{inv.get('reported_confidence', 0):.0%}",
            f"{render_status_dot(inv.get('verdict'))} {verdict_text}",
        ])

    st.html(render_data_table(
        ["Date", "Type", "Confidence", "Verdict"],
        rows,
        classes=["", "", "col-data", "col-muted"],
    ))

with tab2:
    st.subheader("Investigation details")
    selected = st.selectbox(
        "Select an investigation:",
        [i["incident_id"] for i in searched] if searched else [i["incident_id"] for i in filtered],
        format_func=lambda x: x.split("_")[0],
        label_visibility="collapsed",
    )

    if selected:
        inv = store.get_investigation(selected)
        st.markdown(inv.get("final_report", "No report"))
