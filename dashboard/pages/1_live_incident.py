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
from siren_v1 import detect_anomalies


st.title("Live incident investigation")

# Pick a CSV from the simulator outputs
metrics_files = sorted(Path("data/metrics").glob("*.csv"), reverse=True)
if not metrics_files:
    st.warning("No metric files found. Run the simulator first: `python simulator/run.py`")
    st.stop()

selected = st.selectbox(
    "Choose incident data:",
    metrics_files,
    format_func=lambda p: p.name,
)

if st.button("Run investigation", type="primary"):
    with st.status("Running investigation...", expanded=True) as status:
        # Index
        st.write("Indexing telemetry into Pinecone + TimescaleDB + Neo4j...")
        engine = SirenQueryEngine()
        logs_path = selected.parent.parent / "logs" / selected.name
        traces_path = selected.parent.parent / "traces" / selected.name
        counts = index_incident(str(selected), str(logs_path), "docs", engine, str(traces_path))
        st.write(f"   Indexed {counts['logs']} logs, {counts['metrics']} metric rows")
        
        # Detect anomalies
        st.write("Detecting anomalies...")
        from siren_v1 import generate_metrics
        metrics = _load_metrics_from_csv(selected)
        anomalies = detect_anomalies(metrics)
        st.write(f"   Found {len(anomalies)} anomalies")
        
        # Run agent
        st.write("Running autonomous agent investigation...")
        final_state = run_investigation(
            anomalies=anomalies,
            origin_service=anomalies[0]["service"],
            window_start=anomalies[0]["timestamp"],
            window_end=anomalies[-1]["timestamp"],
            incident_id=selected.stem,
        )
        
        # Save to store
        incident_type = selected.stem.split("_")[0]
        store = FeedbackStore()
        store.save_investigation(final_state, incident_type)
        
        status.update(label=f"Investigation complete in {final_state['current_step']} steps", state="complete")
    
    # Display results
    st.divider()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Root cause", final_state["final_root_cause"])
    with col2:
        st.metric("Confidence", f"{final_state['final_confidence']:.0%}")
    
    # 3D graph
    st.subheader("Service topology")
    affected = [a["service"] for a in anomalies]
    fig = render_dependency_graph(
        affected_services=affected,
        origin_service=final_state.get("origin_service"),
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Metrics comparison
    st.subheader("Metric evolution during incident")
    fig = render_multi_service_comparison(
        services=list(set(affected)),
        window_start=final_state["window_start"],
        window_end=final_state["window_end"],
        metric="error_rate",
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Reasoning trace
    render_reasoning_trace(final_state["tool_history"], final_state["evidence_ledger"])
    render_hypothesis_ledger(final_state.get("hypotheses", []))
    
    # Full report
    st.divider()
    st.markdown("### Full RCA report")
    st.markdown(final_state["final_report"])
    
    # Feedback
    st.divider()
    render_feedback_form(final_state["incident_id"], final_state["final_root_cause"])
