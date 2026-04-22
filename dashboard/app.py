import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Siren — AI Incident Investigator",
    page_icon="⚙",
    layout="wide",
)

st.title("Siren")
st.caption("Incident investigation assistant")

st.markdown("""
Siren helps you quickly diagnose system incidents by analyzing metrics, logs, and traces
to pinpoint the root cause. Browse past investigations or start a new one from the sidebar.
""")

st.divider()

try:
    from feedback.store import FeedbackStore
    from feedback.stats import compute_accuracy_trend

    store = FeedbackStore()
    trend = compute_accuracy_trend(store)
    investigations = store.list_investigations(limit=1000)

    st.subheader("Overview")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total cases", len(investigations))
    with col2:
        reviewed = [i for i in investigations if i.get("verdict")]
        st.metric("Reviewed", len(reviewed))
    with col3:
        if trend:
            latest = trend[-1]["accuracy"]
            st.metric("Accuracy (today)", f"{latest:.0%}")
        else:
            st.metric("Accuracy (today)", "—")
    with col4:
        if reviewed:
            overall = sum(1 for i in reviewed if i["verdict"] == "correct") / len(reviewed)
            st.metric("Accuracy (all time)", f"{overall:.0%}")
        else:
            st.metric("Accuracy (all time)", "—")
except Exception as e:
    st.warning(f"Database unavailable. Start with: `docker-compose up`")
