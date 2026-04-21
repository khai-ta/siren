import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json


@dataclass
class InvestigationRecord:
    incident_id: str
    incident_type: str
    reported_root_cause: str
    reported_confidence: float
    steps_taken: int
    final_report: str
    tool_history: list
    evidence_ledger: dict
    created_at: datetime


class FeedbackStore:
    def __init__(self) -> None:
        self.conn = psycopg2.connect(os.getenv("FEEDBACK_URI"))
        self.conn.autocommit = True

    def save_investigation(self, final_state: dict, incident_type: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO investigations (
                  incident_id, incident_type, reported_root_cause,
                  reported_confidence, steps_taken, final_report,
                  tool_history, evidence_ledger
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (incident_id) DO UPDATE SET
                  reported_root_cause = EXCLUDED.reported_root_cause,
                  reported_confidence = EXCLUDED.reported_confidence,
                  final_report = EXCLUDED.final_report,
                  tool_history = EXCLUDED.tool_history,
                  evidence_ledger = EXCLUDED.evidence_ledger
                """,
                (
                    final_state["incident_id"],
                    incident_type,
                    final_state["final_root_cause"],
                    final_state["final_confidence"],
                    final_state["current_step"],
                    final_state["final_report"],
                    Json(final_state["tool_history"]),
                    Json(final_state["evidence_ledger"]),
                ),
            )

    def save_feedback(
        self,
        incident_id: str,
        verdict: str,
        correct_root_cause: Optional[str] = None,
        engineer_notes: Optional[str] = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (
                  incident_id, verdict, correct_root_cause, engineer_notes
                ) VALUES (%s, %s, %s, %s)
                """,
                (incident_id, verdict, correct_root_cause, engineer_notes),
            )

    def get_investigation(self, incident_id: str) -> Optional[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM investigations WHERE incident_id = %s", (incident_id,))
            return cur.fetchone()

    def list_investigations(self, limit: int = 50) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT i.*, f.verdict, f.correct_root_cause
                FROM investigations i
                LEFT JOIN feedback f ON i.incident_id = f.incident_id
                ORDER BY i.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()

    def get_feedback_for_incident(self, incident_id: str) -> Optional[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM feedback WHERE incident_id = %s ORDER BY created_at DESC LIMIT 1",
                (incident_id,),
            )
            return cur.fetchone()

    def get_retrieval_weight(self, source: str, incident_type: str) -> float:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT weight FROM retrieval_weights WHERE source = %s AND incident_type = %s",
                (source, incident_type),
            )
            row = cur.fetchone()
            return row[0] if row else 1.0

    def update_retrieval_weight(self, source: str, incident_type: str, weight: float) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_weights (source, incident_type, weight)
                VALUES (%s, %s, %s)
                ON CONFLICT (source, incident_type) DO UPDATE
                SET weight = EXCLUDED.weight, updated_at = NOW()
                """,
                (source, incident_type, weight),
            )
