from collections import defaultdict
from typing import Dict, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import os

from feedback.store import FeedbackStore


class RetrievalOptimizer:
    """DSPy-powered retrieval weight optimizer

    Learns from engineer feedback to reweight which retrieval sources
    are most effective for each incident type
    """
    
    def __init__(self, store: FeedbackStore):
        self.store = store
        self.conn = psycopg2.connect(os.getenv("FEEDBACK_URI"))
    
    def recompute_weights(self) -> Dict[Tuple[str, str], float]:
        """Analyze feedback and compute new retrieval weights

        Returns: dict of {(source, incident_type): weight}

        This is a stub for Slice 5B. The full implementation will:
        1. Extract which retrieval sources were used for each investigation
        2. Compare them against engineer feedback (correct/incorrect)
        3. Use DSPy to reweight sources that correlate with correct diagnoses
        4. Store weights in retrieval_weights table
        """
        # Placeholder: equal weights for all sources
        sources = ["pinecone-logs", "pinecone-traces", "pinecone-metrics", "neo4j-graph"]
        incident_types = ["latency_spike", "error_rate_increase", "network_spike"]
        
        weights = {}
        for source in sources:
            for incident_type in incident_types:
                weights[(source, incident_type)] = 1.0
                self._save_weight(source, incident_type, 1.0)
        
        return weights
    
    def _save_weight(self, source: str, incident_type: str, weight: float) -> None:
        """Save weight to database"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_weights (source, incident_type, weight)
                VALUES (%s, %s, %s)
                ON CONFLICT (source, incident_type) DO UPDATE SET
                  weight = EXCLUDED.weight,
                  updated_at = NOW()
                """,
                (source, incident_type, weight),
            )
        self.conn.commit()
    
    def get_weights(self, incident_type: str = None) -> Dict[Tuple[str, str], float]:
        """Retrieve current weights from database"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if incident_type:
                cur.execute(
                    "SELECT source, incident_type, weight FROM retrieval_weights WHERE incident_type = %s",
                    (incident_type,),
                )
            else:
                cur.execute("SELECT source, incident_type, weight FROM retrieval_weights")
            
            weights = {}
            for row in cur.fetchall():
                key = (row["source"], row["incident_type"])
                weights[key] = row["weight"]
            return weights
