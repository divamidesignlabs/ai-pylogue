from fasthtml.common import Div, H2


CANVAS_ITEMS = [
    {
        "id": "sample-1",
        "type": "insight",
        "title": "Welcome",
        "content": "Canvas is ready. New items will appear here in order.",
        "w": "50%",
        "h": "auto",
    }
]


def _tile_style(item):
    w = item.get("w", "100%")
    h = item.get("h", "auto")
    return f"width:{w};height:{h};"


def render_insight(item):
    return Div(
        H2(item.get("title", "Untitled"), cls="canvas-tile-title"),
        Div(item.get("content", ""), cls="canvas-tile-body"),
        cls="canvas-tile",
        style=_tile_style(item),
    )


def render_unknown(item):
    return Div(
        H2(item.get("title", "Unsupported item"), cls="canvas-tile-title"),
        Div(f"Unknown type: {item.get('type', 'none')}", cls="canvas-tile-body canvas-tile-body--unknown"),
        cls="canvas-tile canvas-tile--unknown",
        style=_tile_style(item),
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
