import streamlit as st
from pathlib import Path

from retrieval.indexer import index_incident
from retrieval.orchestrator import SirenQueryEngine
from agent.run import run_investigation
from feedback.store import FeedbackStore
from dashboard.components.graph_3d import render_dependency_graph
from dashboard.components.metrics_chart import render_multi_service_comparison
from dashboard.components.reasoning_trace import render_reasoning_trace, render_hypothesis_ledger
from dashboard.components.feedback_form import render_feedback_form
from siren import detect_anomalies


st.title("Investigate an incident")

# Pick a CSV from the simulator outputs
metrics_files = sorted(Path("data/metrics").glob("*.csv"), reverse=True)
if not metrics_files:
    st.warning("No incidents available. Run the simulator first: `python simulator/run.py`")
    st.stop()

selected = st.selectbox(
    "Select incident to investigate:",
    metrics_files,
    format_func=lambda p: p.name.replace(".csv", ""),
)

if st.button("Start investigation", type="primary"):
    with st.status("Analyzing incident...", expanded=True) as status:
        st.write("Gathering telemetry...")
        engine = SirenQueryEngine()
        logs_path = selected.parent.parent / "logs" / selected.name
        traces_path = selected.parent.parent / "traces" / selected.name
        counts = index_incident(str(selected), str(logs_path), "docs", engine, str(traces_path))
        st.write(f"Found {counts['logs']} log entries and {counts['metrics']} data points")

        st.write("Looking for anomalies...")
        import pandas as pd
        metrics = pd.read_csv(selected)
        anomalies = detect_anomalies(metrics)
        st.write(f"Detected {len(anomalies)} anomalies")

        st.write("Analyzing root cause...")
        final_state = run_investigation(
            anomalies=anomalies,
            origin_service=anomalies[0]["service"],
            window_start=anomalies[0]["timestamp"],
            window_end=anomalies[-1]["timestamp"],
            incident_id=selected.stem,
        )

        incident_type = selected.stem.split("_")[0]
        store = FeedbackStore()
        store.save_investigation(final_state, incident_type)

        status.update(label=f"Analysis complete", state="complete")
    
    st.divider()
    st.subheader("Results")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Most likely cause", final_state["final_root_cause"])
    with col2:
        st.metric("Confidence level", f"{final_state['final_confidence']:.0%}")
    
    st.subheader("System topology")
    st.caption("Red = suspected origin, orange = affected services")
    affected = [a["service"] for a in anomalies]
    fig = render_dependency_graph(
        affected_services=affected,
        origin_service=final_state.get("origin_service"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Metrics during the incident")
    fig = render_multi_service_comparison(
        services=list(set(affected)),
        window_start=final_state["window_start"],
        window_end=final_state["window_end"],
        metric="error_rate",
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    st.subheader("Investigation details")
    with st.expander("How we arrived at this conclusion", expanded=False):
        render_reasoning_trace(final_state["tool_history"], final_state["evidence_ledger"])
        render_hypothesis_ledger(final_state.get("hypotheses", []))

    st.divider()
    st.subheader("Full report")
    st.markdown(final_state["final_report"])

    st.divider()
    render_feedback_form(final_state["incident_id"], final_state["final_root_cause"])
