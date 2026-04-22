"""UI utility functions for the dark-mode design system."""

def get_severity_level(confidence: float) -> tuple[str, str]:
    """
    Determine severity level and color from confidence score.
    Returns (severity_name, bg_color_class)
    """
    if confidence >= 0.9:
        return "critical", "severity-critical"
    elif confidence >= 0.75:
        return "high", "severity-high"
    elif confidence >= 0.6:
        return "medium", "severity-medium"
    else:
        return "low", "severity-low"


def render_status_badge(verdict: str | None) -> str:
    """Render a small status badge for verdict."""
    if verdict == "correct":
        return '<span class="badge badge-correct">Correct</span>'
    elif verdict == "incorrect":
        return '<span class="badge badge-incorrect">Incorrect</span>'
    elif verdict == "partial":
        return '<span class="badge badge-partial">Partial</span>'
    else:
        return '<span class="badge badge-pending">Pending</span>'


def render_kpi_strip(metrics: list[dict]) -> str:
    """
    Render a KPI strip with evenly-spaced cells.

    Args:
        metrics: list of dicts with keys:
            - label: str (e.g. "Total Cases")
            - value: str (e.g. "42")
            - delta: str | None (e.g. "+3 today")
            - delta_type: "positive" | "negative" | None

    Returns:
        HTML string
    """
    cols = min(len(metrics), 4)
    html = f'<div class="kpi-strip" style="grid-template-columns: repeat({cols}, 1fr) !important;">'
    for metric in metrics[:4]:  # Limit to 4 cells
        delta_html = ""
        if metric.get("delta"):
            delta_class = f"kpi-delta {metric.get('delta_type', '')}"
            delta_html = f'<div class="{delta_class}">{metric["delta"]}</div>'

        html += f'''
<div class="kpi-cell">
  <div class="kpi-label">{metric["label"]}</div>
  <div class="kpi-value">{metric["value"]}</div>
  {delta_html}
</div>
'''
    html += '</div>'
    return html


def render_status_dot(verdict: str | None) -> str:
    """Render a status dot with class based on verdict."""
    if verdict == "correct":
        return '<span class="dot-correct">●</span>'
    elif verdict == "partial":
        return '<span class="dot-partial">●</span>'
    elif verdict == "incorrect":
        return '<span class="dot-incorrect">●</span>'
    else:
        return '<span class="dot-partial">●</span>'


def render_data_table(headers: list[str], rows: list[list], classes: list[str] | None = None) -> str:
    """
    Render a styled HTML data table.

    Args:
        headers: list of column headers
        rows: list of lists (each inner list is a row)
        classes: list of CSS classes for each column (e.g. ["", "col-data", "col-muted"])

    Returns:
        HTML string
    """
    if classes is None:
        classes = [""] * len(headers)

    html = '<table class="data-table"><thead><tr>'
    for header in headers:
        html += f'<th>{header}</th>'
    html += '</tr></thead><tbody>'

    for row in rows:
        html += '<tr>'
        for i, cell in enumerate(row):
            cls = f' class="{classes[i]}"' if i < len(classes) and classes[i] else ""
            html += f'<td{cls}>{cell}</td>'
        html += '</tr>'

    html += '</tbody></table>'
    return html


def render_data_table_with_severity(
    headers: list[str],
    rows: list[list],
    severity_levels: list[str],
    classes: list[str] | None = None,
    table_id: str = "data-table",
) -> str:
    """
    Render a data table with severity-based row coloring and clickable rows.

    Args:
        headers: list of column headers
        rows: list of lists (each inner list is a row)
        severity_levels: list of severity class names (e.g. ["severity-critical", "severity-high", ...])
        classes: list of CSS classes for each column
        table_id: HTML id for the table (used for JavaScript clicks)

    Returns:
        HTML string with embedded JavaScript for row clicks
    """
    if classes is None:
        classes = [""] * len(headers)

    html = f'<table class="data-table" id="{table_id}"><thead><tr>'
    for header in headers:
        html += f'<th>{header}</th>'
    html += '</tr></thead><tbody>'

    for idx, row in enumerate(rows):
        severity_class = severity_levels[idx] if idx < len(severity_levels) else ""
        html += f'<tr class="{severity_class}" data-row-index="{idx}">'
        for i, cell in enumerate(row):
            cls = f' class="{classes[i]}"' if i < len(classes) and classes[i] else ""
            html += f'<td{cls}>{cell}</td>'
        html += '</tr>'

    html += '</tbody></table>'

    # JavaScript to handle row clicks
    html += f'''
<script>
const table = document.getElementById("{table_id}");
if (table) {{
  const rows = table.querySelectorAll("tbody tr");
  rows.forEach((row, idx) => {{
    row.style.cursor = "pointer";
    row.addEventListener("click", () => {{
      window.parent.postMessage({{type: "row_click", rowIndex: idx, tableId: "{table_id}"}}, "*");
    }});
  }});
}}
</script>
'''

    return html


def render_progress_bar(value: float, max_value: float = 1.0, label: str = "") -> str:
    """
    Render an inline progress bar.

    Args:
        value: numeric value
        max_value: maximum value (default 1.0)
        label: optional label to display

    Returns:
        HTML string
    """
    percent = (value / max_value * 100) if max_value > 0 else 0
    percent = min(100, max(0, percent))  # Clamp 0-100

    html = f'<div class="progress-bar"><div class="progress-fill" style="width: {percent}%"></div></div>'
    if label:
        html = f'{label} {html}'
    return html


def render_progress_steps(steps: list[str], current_step: int) -> str:
    """
    Render a horizontal progress steps strip.

    Args:
        steps: list of step names
        current_step: 0-indexed current step (or -1 if not started)

    Returns:
        HTML string
    """
    html = '<div class="steps-strip">'
    for i, step in enumerate(steps):
        if i < current_step:
            status = "done"
            indicator = "✓"
        elif i == current_step:
            status = "active"
            indicator = str(i + 1)
        else:
            status = ""
            indicator = str(i + 1)

        status_class = f' {status}' if status else ''
        html += f'''<div class="step{status_class}">
<span class="step-indicator">{indicator}</span>{step}</div>'''

    html += '</div>'
    return html


def render_bar_chart(label: str, value: float, max_value: float = 1.0) -> str:
    """
    Render a horizontal bar for tables (success rate visualization).

    Args:
        label: label text
        value: numeric value
        max_value: maximum value (default 1.0 for percentages)

    Returns:
        HTML string with label and bar
    """
    percent = (value / max_value * 100) if max_value > 0 else 0
    percent = min(100, max(0, percent))

    pct_text = f"{percent:.0f}%"

    return f'''<div style="display: flex; align-items: center; gap: 0.5rem;">
<div style="flex: 1;">
  <div class="progress-bar" style="margin: 0;">
    <div class="progress-fill" style="width: {percent}%; height: 8px;"></div>
  </div>
</div>
<span style="font-family: var(--font-data); min-width: 40px;">{pct_text}</span>
</div>'''
