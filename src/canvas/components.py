from fasthtml.common import Div, H2


CANVAS_ITEMS = [
    {
        "id": "sample-1",
        "type": "insight",
        "title": "Welcome",
        "content": "Canvas is ready. New items will appear here in order.",
        "w": "50%",
        "h": "auto",
        "variant": "success",
        "class": "shadow-lg",
    }
]

INSIGHT_VARIANTS = {
    "success": "canvas-tile--insight-success",
    "caution": "canvas-tile--insight-caution",
    "danger": "canvas-tile--insight-danger",
}


def _component_style(item):
    w = item.get("w", "100%")
    h = item.get("h", "auto")
    return f"width:{w};height:{h};"


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
        style=_component_style(item),
    )


def render_unknown(item):
    return Div(
        H2(item.get("title", "Unsupported item"), cls="canvas-tile-title"),
        Div(f"Unknown type: {item.get('type', 'none')}", cls="canvas-tile-body canvas-tile-body--unknown"),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--unknown"),
        style=_component_style(item),
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
    return Div(*cards, cls="canvas-stack")
