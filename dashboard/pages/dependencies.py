import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from dashboard.components.styles import inject_styles
from dashboard.components.graph_2d import render_2d_topology
from simulator.topology import SERVICES, DEPENDENCIES

inject_styles()

st.title("Service dependencies")
st.caption("View service topology and SLA baselines")

st.write("**Select a service:**")
selected = st.selectbox(
    "Service",
    list(SERVICES.keys()),
    label_visibility="collapsed",
)

fig = render_2d_topology(selected_service=selected)
st.plotly_chart(fig, use_container_width=True)

# Details
if selected:
    st.divider()
    baseline = SERVICES[selected]
    deps = DEPENDENCIES.get(selected, [])
    callers = [s for s, d in DEPENDENCIES.items() if selected in d]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("RPS", baseline.get('rps', '—'))
        st.metric("p50", f"{baseline.get('latency_p50', '—')}ms")
    with col2:
        st.metric("p99", f"{baseline.get('latency_p99', '—')}ms")
        st.metric("Error", f"{baseline.get('error_rate', 0):.2%}")
    with col3:
        st.metric("CPU", f"{baseline.get('cpu', '—')}%")
        st.metric("Memory", f"{baseline.get('memory', '—')}%")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Dependencies**")
        for d in (deps or ["—"]):
            st.caption(d)
    with col2:
        st.write("**Callers**")
        for c in (callers or ["—"]):
            st.caption(c)
