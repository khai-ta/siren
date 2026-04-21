import streamlit as st
from feedback.store import FeedbackStore


def render_feedback_form(incident_id: str, reported_root_cause: str) -> None:
    """Capture engineer feedback on diagnosis."""
    st.subheader("Was this diagnosis helpful?")

    store = FeedbackStore()
    existing = store.get_feedback_for_incident(incident_id)

    if existing:
        st.info(
            f"You marked this as **{existing['verdict']}**"
            + (f" (actual cause: {existing['correct_root_cause']})" if existing["correct_root_cause"] else "")
        )
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Yes, correct", use_container_width=True, key=f"fb_yes_{incident_id}"):
            store.save_feedback(incident_id, verdict="correct")
            st.rerun()

    with col2:
        if st.button("Partially helpful", use_container_width=True, key=f"fb_partial_{incident_id}"):
            st.session_state[f"fb_form_{incident_id}"] = "partial"

    with col3:
        if st.button("Not correct", use_container_width=True, key=f"fb_wrong_{incident_id}"):
            st.session_state[f"fb_form_{incident_id}"] = "incorrect"

    if st.session_state.get(f"fb_form_{incident_id}") in ("partial", "incorrect"):
        verdict = st.session_state[f"fb_form_{incident_id}"]
        with st.form(f"override_{incident_id}"):
            correct = st.text_input("What was the actual root cause?")
            notes = st.text_area("Any other details? (optional)")
            if st.form_submit_button("Save feedback"):
                store.save_feedback(
                    incident_id,
                    verdict=verdict,
                    correct_root_cause=correct,
                    engineer_notes=notes,
                )
                del st.session_state[f"fb_form_{incident_id}"]
                st.rerun()
