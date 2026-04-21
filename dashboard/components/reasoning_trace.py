import streamlit as st


def render_reasoning_trace(tool_history: list[dict], evidence_ledger: dict) -> None:
    """Render the step-by-step investigation."""
    for step in tool_history:
        with st.expander(
            f"Step {step['step']}: {step['tool_name']}",
            expanded=False,
        ):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.caption("Looked up:")
                st.json(step["arguments"])
            with col2:
                st.caption("Found:")
                st.write(step["result_summary"])

                evidence_id = f"ev_{step['step']}"
                if evidence_id in evidence_ledger:
                    with st.expander("Raw data"):
                        st.json(evidence_ledger[evidence_id])


def render_hypothesis_ledger(hypotheses: list[dict]) -> None:
    """Show what we considered."""
    st.markdown("**Hypotheses we explored:**")

    for hyp in hypotheses:
        status_map = {"confirmed": "✓", "rejected": "✗", "open": "→"}
        status_symbol = status_map[hyp["status"]]
        st.markdown(
            f"{status_symbol} {hyp['statement']} "
            f"({hyp['confidence']:.0%} likely)"
        )
