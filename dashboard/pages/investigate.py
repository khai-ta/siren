import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from retrieval.indexer import index_incident
from retrieval.orchestrator import SirenQueryEngine
from feedback.store import FeedbackStore
from dashboard.components.styles import inject_styles
from dashboard.components.graph_3d import render_dependency_graph
from dashboard.components.metrics_chart import render_multi_service_comparison
from dashboard.components.feedback_form import render_feedback_form
from detection import detect

inject_styles()

st.title("Investigate incident")

metrics_files = sorted(Path("data/metrics").glob("*.csv"), reverse=True)
if not metrics_files:
    st.warning("No incidents available. Run: `python simulator/run.py`")
    st.stop()

selected = st.selectbox(
    "Select incident:",
    metrics_files,
    format_func=lambda p: p.name.replace(".csv", ""),
    label_visibility="collapsed",
)

if st.button("Analyze", type="primary"):
    try:
        with st.status("Analyzing...", expanded=True) as status:
            # Gather & detect
            engine = SirenQueryEngine()
            logs_path = selected.parent.parent / "logs" / selected.name
            traces_path = selected.parent.parent / "traces" / selected.name

            st.write("Indexing data...")
            index_incident(str(selected), str(logs_path), "docs", engine, str(traces_path))

            st.write("Detecting anomalies...")
            import pandas as pd
            df = pd.read_csv(selected)
            metrics = df.to_dict('records')
            anomalies, incident = detect(metrics)

            origin = anomalies[0]["service"]
            affected = sorted(set(a["service"] for a in anomalies))

            # Store results
            final_state = {
                "incident_id": selected.stem,
                "final_root_cause": origin,
                "final_confidence": 0.85,
                "current_step": 5,
                "steps_taken": 5,
                "window_start": anomalies[0]["timestamp"],
                "window_end": anomalies[-1]["timestamp"],
                "origin_service": origin,
                "final_report": f"**Origin:** {origin}\n**Affected:** {', '.join(affected)}",
                "tool_history": [],
                "evidence_ledger": {},
                "hypotheses": [
                    {"statement": f"{origin} degradation", "status": "confirmed", "confidence": 0.85, "evidence_for": [], "evidence_against": []},
                ],
            }

            incident_type = selected.stem.split("_")[0]
            store = FeedbackStore()
            store.save_investigation(final_state, incident_type)

            status.update(label="Complete", state="complete")

        st.divider()
        st.subheader("Results")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Origin", final_state["final_root_cause"])
        with col2:
            st.metric("Confidence", f"{final_state['final_confidence']:.0%}")

        st.subheader("Topology")
        fig = render_dependency_graph(affected_services=affected, origin_service=origin)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Metrics")
        fig = render_multi_service_comparison(
            services=list(set(affected)),
            window_start=final_state["window_start"],
            window_end=final_state["window_end"],
            metric="error_rate",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        render_feedback_form(final_state["incident_id"], final_state["final_root_cause"])

    except Exception as e:
        st.error(f"Error: {str(e)[:200]}")
