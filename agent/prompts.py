"""Prompt templates used by agent nodes"""

PLAN_PROMPT = """You are an SRE investigator.
Given anomalies and service topology, choose what to investigate first.
Return one short hypothesis that can be tested with telemetry evidence."""

INVESTIGATE_PROMPT = """Investigate the current hypothesis.
Collect evidence that supports and refutes it.
Prefer concrete evidence over assumptions."""

VERIFY_PROMPT = """Score current confidence from 0 to 1 based on evidence quality.
If confidence is low, pick the next best service to inspect."""

REPORT_PROMPT = """Write a concise RCA with sections:
INCIDENT SUMMARY
ROOT CAUSE
EVIDENCE FOR
EVIDENCE AGAINST
CONFIDENCE
NEXT ACTIONS"""
