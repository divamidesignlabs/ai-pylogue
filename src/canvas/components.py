from fasthtml.common import Div, H2


CANVAS_ITEMS = [
    {
        "id": "sample-1",
        "type": "insight",
        "title": "Welcome",
        "content": "Canvas is ready. New items will appear here in order.",
    }
]


def render_canvas(items):
    cards = []
    for item in items:
        cards.append(
            Div(
                H2(item.get("title", "Untitled"), cls="text-base font-semibold text-slate-800"),
                Div(item.get("content", ""), cls="text-sm text-slate-600 mt-1"),
                cls="rounded-lg border border-slate-200 bg-white p-3",
            )
        )
    return Div(*cards, cls="space-y-3")
