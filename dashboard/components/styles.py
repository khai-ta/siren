import streamlit as st


def inject_styles():
    """Inject minimal dark-mode CSS without breaking Streamlit."""
    css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #0A0A0C;
  --surface: #111113;
  --border: rgba(255, 255, 255, 0.06);
  --text: #E4E4E7;
  --text-muted: #71717A;
  --accent: #E84545;
  --font-ui: 'Inter', system-ui;
  --font-data: 'JetBrains Mono', monospace;
}

/* Global */
body, .stApp {
  background: var(--bg) !important;
  color: var(--text) !important;
  font-family: var(--font-ui) !important;
}

/* Data values */
[data-testid="stMetricValue"] {
  font-family: var(--font-data) !important;
}

/* KPI Strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  margin: 2rem 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
}

.kpi-cell {
  padding: 1.5rem;
  border-right: 1px solid var(--border);
}

.kpi-cell:last-child { border-right: none; }

.kpi-label {
  color: var(--text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.kpi-value {
  font-family: var(--font-data);
  font-size: 1.875rem;
  color: var(--text);
  margin-bottom: 0.25rem;
}

.kpi-delta {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: var(--font-data);
}

/* Progress bar */
.progress-bar {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #52525B 0%, #71717A 100%);
  border-radius: 2px;
}

/* Status dots */
.dot-correct, .dot-partial, .dot-incorrect { font-size: 0.75rem; }
.dot-correct { color: var(--text); }
.dot-partial { color: var(--text-muted); }
.dot-incorrect { color: var(--accent); }

/* Table */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  margin: 1rem 0;
}

.data-table th {
  background: transparent;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  padding: 1rem 0.75rem;
  text-align: left;
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.data-table td {
  padding: 0.875rem 0.75rem;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}

.data-table tr:hover td { background: rgba(255, 255, 255, 0.02); }

.col-data { font-family: var(--font-data); }
.col-muted { color: var(--text-muted); }

/* Progress steps */
.steps-strip {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 1.5rem 0;
  padding: 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 3px;
}

.step {
  display: flex;
  align-items: center;
  color: var(--text-muted);
  font-size: 0.875rem;
  white-space: nowrap;
}

.step::after {
  content: '';
  width: 20px;
  height: 1px;
  background: var(--border);
  margin: 0 1rem;
}

.step:last-child::after { display: none; }

.step-indicator {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--border);
  margin-right: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-family: var(--font-data);
  flex-shrink: 0;
}

.step.done .step-indicator {
  background: transparent;
  border-color: var(--accent);
  color: var(--accent);
}

.step.active {
  color: var(--text);
}

.step.active .step-indicator {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* Bar chart */
.bar-fill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  background: var(--accent);
  opacity: 0.3;
  border-radius: 2px;
  min-width: 20px;
}
</style>
"""
    st.html(css)
