import streamlit as st
from dashboard.components.graph_3d import render_dependency_graph
from simulator.topology import SERVICES, DEPENDENCIES

st.title("AcmeCloud dependency graph")
st.caption("Click and drag to rotate. Scroll to zoom.")

fig = render_dependency_graph()
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Service details")

selected = st.selectbox("Service:", list(SERVICES.keys()))
baseline = SERVICES[selected]
deps = DEPENDENCIES.get(selected, [])
callers = [s for s, d in DEPENDENCIES.items() if selected in d]

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Baselines**")
    for key, value in baseline.items():
        st.text(f"{key}: {value}")
with col2:
    st.markdown(f"**Depends on:** {', '.join(deps) if deps else '(none)'}")
    st.markdown(f"**Called by:** {', '.join(callers) if callers else '(none)'}")
