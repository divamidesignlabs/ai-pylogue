from fasthtml.common import Div, H2


CANVAS_ITEMS = [
    {
        "id": "sample-1",
        "type": "insight",
        "title": "Welcome",
        "content": "100% of users find this canvas useful.",
        "col_span": 4,
        "row_span": 1,
        "variant": "success",
        "class": "shadow-lg",
    },
    {
        "id": "sample-2",
        "type": "insight",
        "title": "Welcome",
        "content": "20% of users find this canvas useful.",
        "col_span": 4,
        "row_span": 1,
        "variant": "caution",
        "class": "shadow-lg",
    },
    {
        "id": "sample-2",
        "type": "insight",
        "title": "Welcome",
        "content": "0% of users find this canvas useful.",
        "col_span": 6,
        "row_span": 1,
        "variant": "danger",
        "class": "shadow-lg",
    }
]

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


def render_insight(item):
    variant = INSIGHT_VARIANTS.get(item.get("variant"), "")
    return Div(
        H2(item.get("title", "Untitled"), cls="canvas-tile-title"),
        Div(item.get("content", ""), cls="canvas-tile-body"),
        cls=_component_cls(item, "canvas-tile", variant),
        style=_component_layout_style(item),
    )


def render_unknown(item):
    return Div(
        H2(item.get("title", "Unsupported item"), cls="canvas-tile-title"),
        Div(f"Unknown type: {item.get('type', 'none')}", cls="canvas-tile-body canvas-tile-body--unknown"),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--unknown"),
        style=_component_layout_style(item),
    )


RENDERERS = {
    "insight": render_insight,
}


def render_canvas(items):
    cards = []
    for item in items:
        item_type = item.get("type", "")
        renderer = RENDERERS.get(item_type, render_unknown)
        cards.append(renderer(item))
    return Div(*cards, cls="canvas-grid")
