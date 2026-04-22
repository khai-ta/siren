import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from dashboard.components.styles import inject_styles
from dashboard.components.graph_2d import render_2d_topology
from simulator.topology import SERVICES, DEPENDENCIES

inject_styles()

st.title("System dependencies")
st.caption("Click any service to view details")

# Topology graph
selected = st.selectbox(
    "Select a service:",
    list(SERVICES.keys()),
    label_visibility="collapsed",
)

fig = render_2d_topology(selected_service=selected)
st.plotly_chart(fig, use_container_width=True)

# Service detail panel
if selected:
    st.divider()
    st.subheader(f"Service: {selected}")

    baseline = SERVICES[selected]
    deps = DEPENDENCIES.get(selected, [])
    callers = [s for s, d in DEPENDENCIES.items() if selected in d]

    # SLA baselines grid
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("RPS", f"{baseline.get('rps', '—')} req/sec")
        st.metric("Latency p50", f"{baseline.get('latency_p50', '—')} ms")

    with col2:
        st.metric("Latency p99", f"{baseline.get('latency_p99', '—')} ms")
        st.metric("Error rate", f"{baseline.get('error_rate', 0):.3%}")

    with col3:
        st.metric("CPU", f"{baseline.get('cpu', '—')} %")
        st.metric("Memory", f"{baseline.get('memory', '—')} %")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Dependencies (calls)")
        if deps:
            for dep in deps:
                st.caption(f"→ {dep}")
        else:
            st.caption("No dependencies")

    with col2:
        st.subheader("Callers (used by)")
        if callers:
            for caller in callers:
                st.caption(f"← {caller}")
        else:
            st.caption("No callers")
