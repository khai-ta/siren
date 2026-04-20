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
