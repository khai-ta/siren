import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from datetime import datetime

from retrieval.indexer import index_incident
from retrieval.orchestrator import SirenQueryEngine
from feedback.store import FeedbackStore
from dashboard.components.styles import inject_styles
from dashboard.components.graph_3d import render_dependency_graph
from dashboard.components.metrics_chart import render_multi_service_comparison
from dashboard.components.feedback_form import render_feedback_form
from detection import detect
from simulator.topology import DEPENDENCIES

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
            # Step 1: Gather
            st.write("Gathering telemetry...")
            engine = SirenQueryEngine()
            logs_path = selected.parent.parent / "logs" / selected.name
            traces_path = selected.parent.parent / "traces" / selected.name
            counts = index_incident(str(selected), str(logs_path), "docs", engine, str(traces_path))

            # Step 2: Detect
            st.write("Detecting anomalies...")
            import pandas as pd
            df = pd.read_csv(selected)
            metrics = df.to_dict('records')
            anomalies, incident = detect(metrics)

            # Analyze data
            origin = anomalies[0]["service"]
            affected = sorted(set(a["service"] for a in anomalies))
            anomaly_types = set(a["metric"] for a in anomalies)
            avg_zscore = sum(abs(a.get("zscore", 0)) for a in anomalies) / len(anomalies) if anomalies else 0
            max_zscore = max((abs(a.get("zscore", 0)) for a in anomalies), default=0)

            # Calculate confidence based on anomaly strength and clarity
            # Base: how clear is the origin (single vs multiple origins)
            origin_clarity = 1.0 if len(affected) <= 3 else 0.8

            # Strength: average z-score (higher = more confident)
            strength = min(1.0, avg_zscore / 8)

            # Combine: clarity matters more for high confidence
            confidence = (0.5 + strength * 0.4) * origin_clarity
            confidence = max(0.45, min(0.95, confidence))

            # Determine downstream impact
            downstream = []
            for service in affected:
                downstream.extend([s for s, deps in DEPENDENCIES.items() if service in deps])
            downstream = sorted(set(downstream))

            # Build tool history
            tool_history = [
                {
                    "step": 1,
                    "tool_name": "index_incident",
                    "arguments": {"logs": counts.get("logs", 0), "traces": counts.get("trace_rows", 0)},
                    "result_summary": f"Indexed {counts.get('logs', 0)} logs and {counts.get('trace_rows', 0)} traces",
                },
                {
                    "step": 2,
                    "tool_name": "detect_anomalies",
                    "arguments": {"services": affected, "anomaly_count": len(anomalies)},
                    "result_summary": f"Detected {len(anomalies)} anomalies across {len(affected)} services",
                },
                {
                    "step": 3,
                    "tool_name": "analyze_origin",
                    "arguments": {"origin_service": origin, "max_zscore": max_zscore},
                    "result_summary": f"Identified {origin} as origin (z-score: {max_zscore:.1f})",
                },
                {
                    "step": 4,
                    "tool_name": "assess_impact",
                    "arguments": {"affected": affected, "downstream": downstream},
                    "result_summary": f"Impact reaches {len(downstream)} downstream services",
                },
            ]

            # Build hypotheses
            hypotheses = [
                {
                    "statement": f"{origin} degradation causing cascade",
                    "status": "confirmed",
                    "confidence": confidence,
                    "evidence_for": [1, 2, 3, 4],
                    "evidence_against": [],
                },
            ]

            if len(anomaly_types) > 1:
                hypotheses.append({
                    "statement": f"Multiple failure modes: {', '.join(anomaly_types)}",
                    "status": "open",
                    "confidence": 0.6,
                    "evidence_for": [2],
                    "evidence_against": [],
                })

            if downstream:
                hypotheses.append({
                    "statement": f"Cascade affecting {len(downstream)} downstream services",
                    "status": "confirmed",
                    "confidence": 0.8,
                    "evidence_for": [4],
                    "evidence_against": [],
                })

            # Build detailed report
            severity = "critical" if max_zscore > 5 else "high" if max_zscore > 3 else "medium"
            report_lines = [
                f"## Incident Analysis Report",
                f"",
                f"**Origin Service:** `{origin}`",
                f"**Incident Type:** {incident.get('anomaly_type', 'unknown')}",
                f"**Severity:** {severity.upper()}",
                f"**Confidence:** {confidence:.0%}",
                f"",
                f"### Anomalies Detected",
                f"- **Count:** {len(anomalies)} anomalies",
                f"- **Types:** {', '.join(anomaly_types)}",
                f"- **Max Z-score:** {max_zscore:.2f}",
                f"- **Avg Z-score:** {avg_zscore:.2f}",
                f"",
                f"### Affected Services",
                f"- **Direct:** {', '.join(affected)}",
                f"- **Downstream:** {', '.join(downstream) if downstream else 'none'}",
                f"",
                f"### Root Cause Analysis",
                f"The degradation originates from `{origin}` with anomalies in {', '.join(anomaly_types)}.",
                f"This cascades to {len(downstream)} downstream services.",
                f"",
                f"### Recommended Actions",
                f"1. Review recent changes to {origin}",
                f"2. Check resource utilization and quotas",
                f"3. Examine error logs for {origin}",
                f"4. Verify dependencies are healthy",
            ]
            final_report = "\n".join(report_lines)

            # Calculate steps taken
            steps_taken = len(tool_history)

            # Store results
            incident_type = selected.stem.split("_")[0]
            final_state = {
                "incident_id": selected.stem,
                "final_root_cause": origin,
                "final_confidence": confidence,
                "current_step": steps_taken,
                "steps_taken": steps_taken,
                "window_start": anomalies[0]["timestamp"],
                "window_end": anomalies[-1]["timestamp"],
                "origin_service": origin,
                "final_report": final_report,
                "tool_history": tool_history,
                "evidence_ledger": {
                    "anomaly_count": len(anomalies),
                    "affected_count": len(affected),
                    "max_zscore": max_zscore,
                    "anomaly_types": list(anomaly_types),
                },
                "hypotheses": hypotheses,
            }

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
        import traceback
        st.code(traceback.format_exc()[:500])
