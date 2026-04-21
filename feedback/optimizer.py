import dspy
from .store import FeedbackStore


class RootCauseSignature(dspy.Signature):
    """Given incident context, predict the most likely root cause service"""
    incident_summary = dspy.InputField(desc="Anomaly data and affected services")
    retrieved_evidence = dspy.InputField(desc="Evidence from retrieval tools")
    root_cause = dspy.OutputField(desc="The name of the root cause service")


class RootCausePredictor(dspy.Module):
    """DSPy module that learns from feedback to predict root causes"""

    def __init__(self):
        super().__init__()
        self.predictor = dspy.ChainOfThought(RootCauseSignature)

    def forward(self, incident_summary, retrieved_evidence):
        return self.predictor(
            incident_summary=incident_summary,
            retrieved_evidence=retrieved_evidence,
        )


class RetrievalOptimizer:
    """Reweights retrieval sources based on which ones led to correct investigations"""

    def __init__(self, store: FeedbackStore):
        self.store = store

    def recompute_weights(self, min_samples: int = 5) -> dict[tuple[str, str], float]:
        """Look at all investigations with feedback, adjust source weights

        For each (source, incident_type) pair:
          weight = (correct investigations using this source) / (total using this source)

        Sources that consistently appear in correct investigations get boosted
        Sources in wrong investigations get attenuated
        """
        investigations = self.store.list_investigations(limit=1000)

        # Tally: (source, incident_type) -> {correct, total}
        tally = {}
        for inv in investigations:
            if not inv.get("verdict"):
                continue

            incident_type = inv["incident_type"]
            is_correct = inv["verdict"] == "correct"

            for tool_call in inv.get("tool_history", []):
                source = tool_call["tool_name"]
                key = (source, incident_type)
                if key not in tally:
                    tally[key] = {"correct": 0, "total": 0}
                tally[key]["total"] += 1
                if is_correct:
                    tally[key]["correct"] += 1

        # Compute weights with Laplace smoothing
        new_weights = {}
        for (source, incident_type), counts in tally.items():
            if counts["total"] < min_samples:
                continue

            # Smoothed success rate, centered at 1.0
            # +1 / +2 = Laplace smoothing for small samples
            success_rate = (counts["correct"] + 1) / (counts["total"] + 2)
            # Scale: 0.5 raw success → weight 1.0, 1.0 → weight 1.5, 0.0 → weight 0.5
            weight = 0.5 + success_rate

            new_weights[(source, incident_type)] = weight
            self.store.update_retrieval_weight(source, incident_type, weight)

        return new_weights

    def apply_weights_to_query(
        self,
        candidates: list[dict],
        source: str,
        incident_type: str,
    ) -> list[dict]:
        """Boost or attenuate candidate scores based on learned weights"""
        weight = self.store.get_retrieval_weight(source, incident_type)
        return [
            {**c, "score": c["score"] * weight, "weight_applied": weight}
            for c in candidates
        ]
