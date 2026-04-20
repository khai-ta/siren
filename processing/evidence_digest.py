"""Compress evidence ledger into rolling digest

By step 15, the ledger can contain 10KB of evidence, much unreferenced.
This module keeps only high-signal evidence and summarizes the rest
"""

from __future__ import annotations

from typing import Any


def digest_evidence(evidence_ledger: dict[str, Any], current_step: int) -> str:
    """Create compressed summary of evidence ledger

    Args:
        evidence_ledger: Dict mapping evidence IDs to {step, tool, data}
        current_step: Current investigation step number

    Returns:
        Compressed evidence summary (vs full ledger JSON dump)
    """
    pass
