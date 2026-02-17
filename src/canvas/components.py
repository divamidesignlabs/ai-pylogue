from fasthtml.common import A, Button, Div, H2, Iframe
import html as html_lib
import re

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


def _remove_card_control():
    return Button(
        type="button",
        cls="canvas-tile-remove",
        uk_icon="close",
        aria_label="Remove card",
        title="Remove card",
        onclick=(
            "event.stopPropagation();"
            "const tile=this.closest('.canvas-tile-link')||this.closest('.canvas-tile');"
            "if(tile){tile.remove();}"
            "return;"
        ),
    )


def _item_id_badge(item):
    item_id = str(item.get("id", "")).strip()
    if not item_id:
        return None
    return Div(item_id, cls="canvas-item-id")


_IFRAME_SRCDOC_RE = re.compile(r"""<iframe[^>]*\ssrcdoc=(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)


def _normalized_srcdoc(value):
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    match = _IFRAME_SRCDOC_RE.search(raw)
    normalized = html_lib.unescape(match.group(2)) if match else raw
    # Some generated Plotly embeds force the parent iframe height (e.g. 420px),
    # which shrinks full-height canvas cards after initial render.
    normalized = re.sub(r"window\.frameElement\.style\.height\s*=\s*[^;]+;", "", normalized)
    normalized = re.sub(r"window\.frameElement\.height\s*=\s*[^;]+;", "", normalized)
    return normalized


def render_insight(item, current_canvas_id: str = "main"):
    variant = INSIGHT_VARIANTS.get(item.get("variant"), "")
    size_cls = "canvas-insight--hero" if _span(item.get("col_span", 12), 1, 12, 12) >= 12 else "canvas-insight--compact"
    layout_style = _component_layout_style(item)
    target_canvas = item.get("drilldown_canvas_id")
    if isinstance(target_canvas, str) and target_canvas.strip():
        body_cls = _component_cls(item, "canvas-tile canvas-insight", variant, size_cls, "canvas-tile--linkable")
        target = target_canvas.strip()
        page_href = f"/canvas/{target}?from={current_canvas_id}"
        panel_href = f"/canvas/{target}/panel?from={current_canvas_id}"
        return A(
            Div(
                _remove_card_control(),
                Div(">", cls="canvas-tile-chevron"),
                H2(item.get("title", "Untitled"), cls="canvas-insight-title"),
                Div(item.get("content", ""), cls="canvas-insight-value"),
                _item_id_badge(item),
                cls=body_cls,
            ),
            href=page_href,
            hx_get=panel_href,
            hx_target="#canvas-panel",
            hx_swap="outerHTML",
            hx_push_url=page_href,
            cls="canvas-tile-link",
            style=layout_style,
        )
    body_cls = _component_cls(item, "canvas-tile canvas-insight", variant, size_cls)
    return Div(
        _remove_card_control(),
        H2(item.get("title", "Untitled"), cls="canvas-insight-title"),
        Div(item.get("content", ""), cls="canvas-insight-value"),
        _item_id_badge(item),
        cls=body_cls,
        style=layout_style,
    )


def render_unknown(item, current_canvas_id: str = "main"):
    return Div(
        _remove_card_control(),
        H2(item.get("title", "Unsupported item"), cls="canvas-tile-title"),
        Div(f"Unknown type: {item.get('type', 'none')}", cls="canvas-tile-body canvas-tile-body--unknown"),
        _item_id_badge(item),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--unknown"),
        style=_component_layout_style(item),
    )


def render_html(item, current_canvas_id: str = "main"):
    layout_style = _component_layout_style(item)
    html_content = _normalized_srcdoc(item.get("html", ""))
    if isinstance(html_content, str) and html_content.strip():
        body = Iframe(
            srcdoc=html_content,
            cls="canvas-html-frame",
            loading="lazy",
            referrerpolicy="no-referrer",
            sandbox="allow-scripts allow-same-origin",
        )
    else:
        body = Div(item.get("content", ""), cls="canvas-html-fallback")
    target_canvas = item.get("drilldown_canvas_id")
    if isinstance(target_canvas, str) and target_canvas.strip():
        target = target_canvas.strip()
        page_href = f"/canvas/{target}?from={current_canvas_id}"
        panel_href = f"/canvas/{target}/panel?from={current_canvas_id}"
        body_cls = _component_cls(item, "canvas-tile", "canvas-tile--html", "canvas-tile--linkable")
        return A(
            Div(
                _remove_card_control(),
                Div(">", cls="canvas-tile-chevron"),
                H2(item.get("title", "Chart"), cls="canvas-tile-title"),
                body,
                _item_id_badge(item),
                cls=body_cls,
            ),
            href=page_href,
            hx_get=panel_href,
            hx_target="#canvas-panel",
            hx_swap="outerHTML",
            hx_push_url=page_href,
            cls="canvas-tile-link",
            style=layout_style,
        )
    return Div(
        _remove_card_control(),
        H2(item.get("title", "Chart"), cls="canvas-tile-title"),
        body,
        _item_id_badge(item),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--html"),
        style=layout_style,
    )


def render_plotly(item, current_canvas_id: str = "main"):
    _ = current_canvas_id
    html_content = _normalized_srcdoc(item.get("html", ""))
    if isinstance(html_content, str) and html_content.strip():
        body = Iframe(
            srcdoc=html_content,
            cls="canvas-html-frame",
            loading="lazy",
            referrerpolicy="no-referrer",
            sandbox="allow-scripts allow-same-origin",
        )
    else:
        body = Div(item.get("content", ""), cls="canvas-html-fallback")
    return Div(
        _remove_card_control(),
        body,
        _item_id_badge(item),
        cls=_component_cls(item, "canvas-tile", "canvas-tile--html", "canvas-tile--plotly"),
        style=_component_layout_style(item),
    )


RENDERERS = {
    "insight": render_insight,
    "html": render_html,
    "plotly": render_plotly,
}


def render_canvas(items, current_canvas_id: str = "main"):
    cards = []
    for item in items:
        item_type = item.get("type", "")
        renderer = RENDERERS.get(item_type, render_unknown)
        cards.append(renderer(item, current_canvas_id=current_canvas_id))
    return Div(*cards, cls="canvas-grid")
