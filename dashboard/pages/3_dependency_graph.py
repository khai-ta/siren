import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from dashboard.components.graph_3d import render_dependency_graph
from simulator.topology import SERVICES, DEPENDENCIES

st.title("System dependencies")
st.caption("Drag to rotate, scroll to zoom")

fig = render_dependency_graph()
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Service information")

selected = st.selectbox("Select a service:", list(SERVICES.keys()), label_visibility="collapsed")
baseline = SERVICES[selected]
deps = DEPENDENCIES.get(selected, [])
callers = [s for s, d in DEPENDENCIES.items() if selected in d]

col1, col2 = st.columns(2)
with col1:
    st.markdown("**SLA targets**")
    for key, value in baseline.items():
        st.caption(f"{key}: {value}")
with col2:
    st.markdown("**Connections**")
    st.caption(f"Depends on: {', '.join(deps) if deps else 'none'}")
    st.caption(f"Used by: {', '.join(callers) if callers else 'none'}")
