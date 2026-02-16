from fasthtml.common import A, Div, H2

INSIGHT_VARIANTS = {
    "success": "canvas-tile--insight-success",
    "caution": "canvas-tile--insight-caution",
    "danger": "canvas-tile--insight-danger",
}


def _span(value, lo, hi, default):
    try:
        return max(lo, min(int(value), hi))
    except Exception:
        return default


def _component_layout_style(item):
    col = _span(item.get("col_span", 12), 1, 12, 12)
    row = _span(item.get("row_span", 1), 1, 6, 1)
    return f"grid-column: span {col}; grid-row: span {row};"


def _component_cls(item, base_cls, *extra_cls):
    extra = []
    for key in ("tw", "className", "class"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            extra.append(value.strip())
    parts = [base_cls, *[c for c in extra_cls if c], *extra]
    return " ".join(parts)


def render_insight(item, current_canvas_id: str = "main"):
    variant = INSIGHT_VARIANTS.get(item.get("variant"), "")
    size_cls = "canvas-insight--hero" if _span(item.get("col_span", 12), 1, 12, 12) >= 12 else "canvas-insight--compact"
    layout_style = _component_layout_style(item)
    target_canvas = item.get("drilldown_canvas_id")
    if isinstance(target_canvas, str) and target_canvas.strip():
        body_cls = _component_cls(item, "canvas-tile canvas-insight", variant, size_cls, "canvas-tile--linkable")
        target = target_canvas.strip()
        return A(
            Div(
                Div(">", cls="canvas-tile-chevron"),
                H2(item.get("title", "Untitled"), cls="canvas-insight-title"),
                Div(item.get("content", ""), cls="canvas-insight-value"),
                cls=body_cls,
            ),
            href=f"/canvas/{target}?from={current_canvas_id}",
            cls="canvas-tile-link",
            style=layout_style,
        )
    body_cls = _component_cls(item, "canvas-tile canvas-insight", variant, size_cls)
    return Div(
        H2(item.get("title", "Untitled"), cls="canvas-insight-title"),
        Div(item.get("content", ""), cls="canvas-insight-value"),
        cls=body_cls,
        style=layout_style,
    )


def render_unknown(item, current_canvas_id: str = "main"):
    return Div(
        H2(item.get("title", "Unsupported item"), cls="canvas-tile-title"),
        Div(f"Unknown type: {item.get('type', 'none')}", cls="canvas-tile-body canvas-tile-body--unknown"),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--unknown"),
        style=_component_layout_style(item),
    )


RENDERERS = {
    "insight": render_insight,
}


def render_canvas(items, current_canvas_id: str = "main"):
    cards = []
    for item in items:
        item_type = item.get("type", "")
        renderer = RENDERERS.get(item_type, render_unknown)
        cards.append(renderer(item, current_canvas_id=current_canvas_id))
    return Div(*cards, cls="canvas-grid")
