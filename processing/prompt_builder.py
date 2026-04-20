"""Assemble investigation prompts with delta-only updates

Normally, hypothesis state is re-sent every step (10 steps = 10× waste).
This module tracks hypothesis deltas and only sends changes
"""

from __future__ import annotations

from typing import Any


def build_investigator_prompt(
    state: dict[str, Any],
    system_template: str,
    previous_state: dict[str, Any] | None = None,
) -> str:
    """Build investigator system prompt with delta-only updates

    Args:
        state: Current investigation state
        system_template: System prompt template with format placeholders
        previous_state: Previous state (for delta computation)

    Returns:
        Assembled prompt using deltas where possible
    """
    pass
