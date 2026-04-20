"""RAGAS scoring for retrieval quality"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness


METRICS = [context_precision, context_recall, faithfulness, answer_relevancy]


def score_investigation(
    query: str,
    retrieved_contexts: Sequence[str],
    generated_answer: str | dict[str, Any],
    ground_truth: str,
) -> dict[str, Any]:
    if isinstance(generated_answer, dict):
        generated_answer = str(generated_answer.get("report", ""))

    dataset = Dataset.from_dict(
        {
            "question": [query],
            "contexts": [list(retrieved_contexts)],
            "answer": [generated_answer],
            "ground_truth": [ground_truth],
            "ground_truths": [[ground_truth]],
        }
    )

    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
    )
    return result.to_pandas().to_dict(orient="records")[0]


def score_agent_investigation(final_state: dict, ground_truth_root_cause: str) -> dict:
    """Score an agent investigation output against known ground truth"""
    retrieved_contexts = [
        f"{ev['tool']}: {str(ev['data'])[:500]}"
        for ev in final_state["evidence_ledger"].values()
    ]

    return score_investigation(
        query=f"What is the root cause of incident {final_state['incident_id']}?",
        retrieved_contexts=retrieved_contexts,
        generated_answer=final_state["final_root_cause"],
        ground_truth=ground_truth_root_cause,
    )
