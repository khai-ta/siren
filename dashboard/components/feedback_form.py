import streamlit as st
from feedback.store import FeedbackStore


def render_feedback_form(incident_id: str, reported_root_cause: str) -> None:
    """Capture engineer feedback on Siren's diagnosis."""
    st.subheader("Your feedback")
    
    store = FeedbackStore()
    existing = store.get_feedback_for_incident(incident_id)
    
    if existing:
        st.success(
            f"You already submitted: **{existing['verdict']}**"
            + (f" — correct cause was {existing['correct_root_cause']}" if existing["correct_root_cause"] else "")
        )
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Correct", use_container_width=True):
            store.save_feedback(incident_id, verdict="correct")
            st.rerun()
    
    with col2:
        if st.button("Partial", use_container_width=True):
            st.session_state[f"fb_form_{incident_id}"] = "partial"
    
    with col3:
        if st.button("Wrong", use_container_width=True):
            st.session_state[f"fb_form_{incident_id}"] = "incorrect"
    
    # Show override form if partial/incorrect
    if st.session_state.get(f"fb_form_{incident_id}") in ("partial", "incorrect"):
        verdict = st.session_state[f"fb_form_{incident_id}"]
        with st.form(f"override_{incident_id}"):
            correct = st.text_input("What was the actual root cause service?")
            notes = st.text_area("Notes (optional)")
            if st.form_submit_button("Submit feedback"):
                store.save_feedback(
                    incident_id,
                    verdict=verdict,
                    correct_root_cause=correct,
                    engineer_notes=notes,
                )
                del st.session_state[f"fb_form_{incident_id}"]
                st.rerun()
