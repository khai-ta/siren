import plotly.graph_objects as go
from simulator.topology import SERVICES, DEPENDENCIES, CRITICAL_EDGES


def render_2d_topology(selected_service: str = None) -> go.Figure:
    """
    Render a 2D SVG-style topology graph.

    Args:
        selected_service: service name to highlight (optional)

    Returns:
        Plotly Figure
    """
    # Fixed 2D positions: 3-tier hierarchy
    positions = {
        # Tier 0 (top) - gateway
        "api-gateway": (3, 2),
        # Tier 1 (middle)
        "auth-service": (1, 1),
        "recommendation-service": (3, 1),
        "payment-service": (5, 1),
        # Tier 2 (bottom) - infrastructure
        "database": (1, 0),
        "cache": (3, 0),
        "message-queue": (5, 0),
    }

    fig = go.Figure()

    # Draw edges first (so they appear under nodes)
    for service, deps in DEPENDENCIES.items():
        if service in positions:
            x0, y0 = positions[service]
            for dep in deps:
                if dep in positions:
                    x1, y1 = positions[dep]

                    # Determine edge color
                    is_critical = (service, dep) in CRITICAL_EDGES
                    if is_critical:
                        edge_color = "rgba(232, 69, 69, 0.4)"
                        edge_width = 2
                    else:
                        edge_color = "rgba(255, 255, 255, 0.12)"
                        edge_width = 1

                    fig.add_trace(go.Scatter(
                        x=[x0, x1],
                        y=[y0, y1],
                        mode="lines",
                        line=dict(color=edge_color, width=edge_width),
                        hoverinfo="skip",
                        showlegend=False,
                    ))

    # Draw nodes
    node_x = []
    node_y = []
    node_text = []
    node_color = []
    node_size = []
    hover_texts = []

    for service, (x, y) in positions.items():
        node_x.append(x)
        node_y.append(y)
        node_text.append(service)

        if service == selected_service:
            node_color.append("#E84545")  # Accent red
            node_size.append(30)
        else:
            node_color.append("#27272A")  # Dark gray
            node_size.append(20)

        # Build hover text for this service
        svc = SERVICES.get(service, {})
        hover = (
            f"<b>{service}</b><br>"
            f"RPS: {svc.get('rps', '—')}<br>"
            f"Error rate: {svc.get('error_rate', 0):.3%}<br>"
            f"Latency p99: {svc.get('latency_p99', 0)}ms<br>"
            f"CPU: {svc.get('cpu', 0)}%<br>"
            f"Memory: {svc.get('memory', 0)}%"
        )
        hover_texts.append(hover)

    fig.add_trace(go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        marker=dict(
            size=node_size,
            color=node_color,
            line=dict(color="rgba(255,255,255,0.1)", width=1),
        ),
        text=node_text,
        textposition="middle center",
        textfont=dict(
            size=9,
            color="#E4E4E7",
            family="JetBrains Mono",
        ),
        customdata=hover_texts,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title="Service dependencies",
        showlegend=False,
        hovermode="closest",
        margin=dict(b=0, l=0, r=0, t=40),
        plot_bgcolor="#0A0A0C",
        paper_bgcolor="#0A0A0C",
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[-0.5, 6.5],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[-0.5, 2.5],
        ),
        height=400,
    )

    return fig
