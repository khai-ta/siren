import streamlit as st

st.set_page_config(
    page_title="Siren — AI Incident Investigator",
    page_icon="⚙",
    layout="wide",
)

st.title("Siren")
st.caption("Autonomous AI Site Reliability Engineer")

st.markdown("""
Siren investigates distributed system incidents autonomously — detecting anomalies, 
forming hypotheses, gathering evidence, and producing root cause analysis reports.

Use the sidebar to navigate:
- **Live incident** — run a new investigation
- **History** — past investigations with feedback
- **Dependency graph** — interactive 3D topology
- **Self-improvement** — learning curves and metrics
""")

# Quick stats
from feedback.store import FeedbackStore
from feedback.stats import compute_accuracy_trend

store = FeedbackStore()
trend = compute_accuracy_trend(store)
investigations = store.list_investigations(limit=1000)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total investigations", len(investigations))
with col2:
    reviewed = [i for i in investigations if i.get("verdict")]
    st.metric("Reviewed", len(reviewed))
with col3:
    if trend:
        latest = trend[-1]["accuracy"]
        st.metric("Latest daily accuracy", f"{latest:.0%}")
    else:
        st.metric("Latest daily accuracy", "—")
with col4:
    if reviewed:
        overall = sum(1 for i in reviewed if i["verdict"] == "correct") / len(reviewed)
        st.metric("Overall accuracy", f"{overall:.0%}")
    else:
        st.metric("Overall accuracy", "—")
