import streamlit as st


def render_reasoning_trace(tool_history: list[dict], evidence_ledger: dict) -> None:
    """Render the agent's step-by-step investigation in an expandable timeline."""
    st.subheader("Investigation trace")
    
    for step in tool_history:
        with st.expander(
            f"Step {step['step']} — called `{step['tool_name']}`",
            expanded=False,
        ):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.caption(f"**Arguments:**")
                st.json(step["arguments"])
            with col2:
                st.caption("**Result summary:**")
                st.write(step["result_summary"])
                
                # Look up full evidence if available
                evidence_id = f"ev_{step['step']}"
                if evidence_id in evidence_ledger:
                    with st.expander("Full evidence payload"):
                        st.json(evidence_ledger[evidence_id])


def render_hypothesis_ledger(hypotheses: list[dict]) -> None:
    """Show the current state of each hypothesis."""
    st.subheader("Hypotheses considered")
    
    for hyp in hypotheses:
        status_map = {"confirmed": "✓", "rejected": "✗", "open": "→"}
        status_symbol = status_map[hyp["status"]]
        st.markdown(
            f"**{status_symbol} {hyp['statement']}** — "
            f"confidence: {hyp['confidence']:.0%} "
            f"({len(hyp['evidence_for'])} for / {len(hyp['evidence_against'])} against)"
        )
