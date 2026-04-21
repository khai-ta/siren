import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from retrieval.timescale_store import TimescaleStore


def render_metric_timeline(
    service: str,
    window_start: str,
    window_end: str,
    metric: str = "latency_p99",
) -> go.Figure:
    store = TimescaleStore()
    rows = store.query_window(service, window_start, window_end)
    df = pd.DataFrame(rows)
    
    fig = px.line(
        df, x="timestamp", y=metric,
        title=f"{service} — {metric}",
    )
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=40, b=40))
    return fig


def render_multi_service_comparison(
    services: list[str],
    window_start: str,
    window_end: str,
    metric: str = "error_rate",
) -> go.Figure:
    store = TimescaleStore()
    dfs = []
    for service in services:
        rows = store.query_window(service, window_start, window_end)
        df = pd.DataFrame(rows)
        df["service"] = service
        dfs.append(df)
    
    combined = pd.concat(dfs, ignore_index=True)
    fig = px.line(
        combined, x="timestamp", y=metric, color="service",
        title=f"{metric} across affected services",
    )
    fig.update_layout(height=400)
    return fig
