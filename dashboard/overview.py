import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Siren — Incident Investigator",
    page_icon="⚙",
    layout="wide",
)

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import render_kpi_strip, render_status_dot, render_data_table, render_status_badge
from detection import detect

inject_styles()

st.title("Siren")
st.caption("Autonomous incident investigation system")

try:
    from feedback.store import FeedbackStore
    from feedback.stats import compute_accuracy_trend

    store = FeedbackStore()
    investigations = store.list_investigations(limit=500)

    # Filter out seed investigations
    investigations = [i for i in investigations if "seed" not in i.get("incident_id", "").lower()]

    if not investigations:
        st.info("No investigations yet. Start from the Investigate page.")
        st.stop()

    reviewed = [i for i in investigations if i.get("verdict")]
    trend = compute_accuracy_trend(store)

    # Key metrics
    kpi_metrics = [
        {"label": "Total", "value": str(len(investigations)), "delta": None},
        {"label": "Reviewed", "value": str(len(reviewed)), "delta": None},
    ]

    if reviewed:
        accuracy = sum(1 for i in reviewed if i["verdict"] == "correct") / len(reviewed)
        kpi_metrics.append({"label": "Accuracy", "value": f"{accuracy:.0%}", "delta": None})

    st.html(render_kpi_strip(kpi_metrics))

    st.divider()

    # Recent investigations
    st.subheader("Recent investigations")
    rows = []
    for inv in sorted(investigations, key=lambda x: x.get("created_at", ""), reverse=True)[:15]:
        date_str = str(inv.get("created_at", "—"))[:10]
        inv_type = inv.get("incident_type", "—")
        verdict = inv.get("verdict")

        rows.append([
            date_str,
            inv_type,
            f"{inv.get('reported_confidence', 0):.0%}",
            render_status_badge(verdict),
        ])

    st.html(render_data_table(
        ["Date", "Type", "Confidence", "Verdict"],
        rows,
        classes=["", "", "col-data", ""],
    ))

except Exception as e:
    st.error("Database unavailable. Run: `docker-compose up`")
