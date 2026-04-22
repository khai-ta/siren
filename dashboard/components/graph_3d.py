import plotly.graph_objects as go
from simulator.topology import DEPENDENCIES, SERVICES


def render_dependency_graph(
    affected_services: list[str] = None,
    origin_service: str = None,
) -> go.Figure:
    """Render the 7-service topology as a 3D graph.
    
    Origin service = red, affected = orange, healthy = gray.
    Edges = gray lines, active cascade edges = red.
    """
    affected_services = affected_services or []
    
    # Fixed positions for the 7 services (manually laid out for clarity)
    positions = {
        "api-gateway":            (0, 2, 2),
        "auth-service":           (-2, 1, 1),
        "payment-service":        (0, 1, 1),
        "recommendation-service": (2, 1, 1),
        "database":               (0, 0, 0),
        "cache":                  (-2, 0, 0),
        "message-queue":          (2, 0, 0),
    }
    
    # Build edge traces
    edge_x, edge_y, edge_z = [], [], []
    cascade_x, cascade_y, cascade_z = [], [], []
    
    for svc, deps in DEPENDENCIES.items():
        for dep in deps:
            x0, y0, z0 = positions[svc]
            x1, y1, z1 = positions[dep]
            
            is_cascade = svc in affected_services and dep in affected_services
            target_x, target_y, target_z = (
                (cascade_x, cascade_y, cascade_z) if is_cascade else (edge_x, edge_y, edge_z)
            )
            target_x += [x0, x1, None]
            target_y += [y0, y1, None]
            target_z += [z0, z1, None]
    
    edge_trace = go.Scatter3d(
        x=edge_x, y=edge_y, z=edge_z,
        mode="lines",
        line=dict(color="lightgray", width=2),
        hoverinfo="none",
        showlegend=False,
    )
    
    cascade_trace = go.Scatter3d(
        x=cascade_x, y=cascade_y, z=cascade_z,
        mode="lines",
        line=dict(color="red", width=4),
        hoverinfo="none",
        name="Cascade path",
    )
    
    # Build node trace
    node_x, node_y, node_z, node_colors, node_texts, node_sizes, node_hover = [], [], [], [], [], [], []
    for svc, pos in positions.items():
        node_x.append(pos[0])
        node_y.append(pos[1])
        node_z.append(pos[2])

        if svc == origin_service:
            color, size = "#E24B4A", 30  # red, large
        elif svc in affected_services:
            color, size = "#EF9F27", 22  # orange
        else:
            color, size = "#4CAF50", 16  # green

        node_colors.append(color)
        node_sizes.append(size)
        node_texts.append(svc)

        # Build hover text with SLA stats
        svc_stats = SERVICES.get(svc, {})
        hover_text = f"<b>{svc}</b><br>"
        hover_text += f"RPS: {svc_stats.get('rps', '—')}<br>"
        hover_text += f"Error rate: {svc_stats.get('error_rate', 0):.3%}<br>"
        hover_text += f"Latency p99: {svc_stats.get('latency_p99', '—')}ms<br>"
        hover_text += f"CPU: {svc_stats.get('cpu', '—')}%<br>"
        hover_text += f"Memory: {svc_stats.get('memory', '—')}%"
        node_hover.append(hover_text)

    node_trace = go.Scatter3d(
        x=node_x, y=node_y, z=node_z,
        mode="markers+text",
        marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="white")),
        text=node_texts,
        textposition="top center",
        textfont=dict(size=12),
        customdata=node_hover,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=False,
    )
    
    fig = go.Figure(data=[edge_trace, cascade_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#0A0A0C",
        plot_bgcolor="#0A0A0C",
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=500,
    )
    return fig
