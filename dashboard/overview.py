import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv
import plotly.graph_objects as go

from dashboard.components.styles import inject_styles
from dashboard.components.ui_utils import (
    render_kpi_strip,
    render_status_dot,
    render_data_table,
    render_progress_bar,
)

load_dotenv()

st.set_page_config(
    page_title="Siren: AI Incident Investigator",
    page_icon="⚙",
    layout="wide",
)

inject_styles()

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
    reviewed = [i for i in investigations if i.get("verdict")]

    # KPI strip with metrics
    kpi_metrics = [
        {
            "label": "Total Cases",
            "value": str(len(investigations)),
            "delta": None,
        },
        {
            "label": "Reviewed",
            "value": str(len(reviewed)),
            "delta": None,
        },
    ]

    if trend:
        latest = trend[-1]["accuracy"]
        kpi_metrics.append({
            "label": "Accuracy (today)",
            "value": f"{latest:.0%}",
            "delta": None,
        })
    else:
        kpi_metrics.append({
            "label": "Accuracy (today)",
            "value": "—",
            "delta": None,
        })

    if reviewed:
        overall = sum(1 for i in reviewed if i["verdict"] == "correct") / len(reviewed)
        kpi_metrics.append({
            "label": "Accuracy (all time)",
            "value": f"{overall:.0%}",
            "delta": None,
        })
    else:
        kpi_metrics.append({
            "label": "Accuracy (all time)",
            "value": "—",
            "delta": None,
        })

    st.html(render_kpi_strip(kpi_metrics))

    # Accuracy trend
    if trend and len(trend) > 0:
        st.subheader("Accuracy trend")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[t["date"] for t in trend],
            y=[t["accuracy"] for t in trend],
            mode="lines+markers",
            name="Accuracy",
            line=dict(color="#E84545", width=2),
            marker=dict(size=8, color="#E84545", line=dict(color="#0A0A0C", width=2)),
            hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.0%}<extra></extra>",
        ))
        fig.update_layout(
            height=200,
            margin=dict(l=40, r=20, t=0, b=40),
            paper_bgcolor="#0A0A0C",
            plot_bgcolor="#0A0A0C",
            xaxis=dict(showgrid=False, showline=False, zeroline=False, tickformat="%Y-%m-%d"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", range=[0, 1]),
            hovermode="x unified",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Incident type breakdown
    st.subheader("Incident types")
    type_counts = {}
    for inv in investigations:
        t = inv.get("incident_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    breakdown_html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">'
    for incident_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = count / len(investigations) * 100 if investigations else 0
        breakdown_html += f'''
<div>
  <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
    <span style="color: var(--text)">{incident_type}</span>
    <span style="color: var(--text-muted); font-family: var(--font-data);">{count} ({pct:.0f}%)</span>
  </div>
  {render_progress_bar(count, max(1, max(type_counts.values())))}
</div>
'''
    breakdown_html += '</div>'
    st.html(breakdown_html)

    # Recent investigations
    st.subheader("Recent investigations")
    if investigations:
        rows = []
        for inv in sorted(investigations, key=lambda x: x.get("created_at", ""), reverse=True)[:20]:
            date_str = str(inv.get("created_at", "—"))[:10]
            inv_type = inv.get("incident_type", "—")
            root_cause = inv.get("reported_root_cause", "—")[:50]
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
            ["Date", "Type", "Root Cause", "Confidence", "Verdict"],
            rows,
            classes=["", "", "", "col-data", "col-muted"],
        ))
    else:
        st.info("No investigations yet.")

except Exception as e:
    st.warning(f"Database unavailable. Start with: `docker-compose up`")
