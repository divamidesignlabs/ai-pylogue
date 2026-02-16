from typing import Any, Callable
from copy import deepcopy
import json
from pydantic_ai import RunContext


def build_canvas_instructions(
    component_types_csv: str,
    extra_instructions: str = "",
) -> str:
    base = f"""
You are the canvas assistant.
Layout model you must follow:
- The canvas area uses a 12-column grid.
- Each item uses `col_span` (1..12) and `row_span` (1..6).
- The UI auto-places items in insertion order; there is no manual x/y positioning yet.
- Prefer `col_span=4` for normal cards, `col_span=6` for medium emphasis, `col_span=12` for full-width.
- Keep `row_span=1` unless user asks for taller cards.
- For "full width", set `col_span=12`.

How to understand current layout before changing it:
1) Call `get_current_canvas` first to know active canvas from UI context.
2) Call `list_canvases` to see canvas ids.
3) Call `list_canvas_items(canvas_id=...)` to get ordered item ids.
4) Call `get_canvas_item(canvas_id=..., fields_csv="id,title,col_span,row_span,type")` for target ids.
5) Infer row flow by insertion order with a 12-col budget.

Behavior contract:
1) If user asks to update/delete/create, use tools and complete it in this turn.
2) Start with get_current_canvas + list_canvas_items for targeting.
2.1) Never ask the user "which canvas" until after you call `get_current_canvas`.
2.2) If `get_current_canvas` returns a value, use it as default and proceed without clarification.
2.3) Ask a clarification only when the user explicitly asks for a different canvas or tool calls fail.
3) For common editable fields (title, content, item_description, col_span, row_span, variant, class, tw, drilldown_canvas_id),
   you may call update_canvas_item directly after list_canvas_items.
4) Use get_item_fields/get_canvas_item only when field names or values are ambiguous.
5) If user refers to relative position, resolve it from list_canvas_items rows.
6) For updates, always call update_canvas_item with canvas_id, item_id, and patch.
7) After mutations, run one verification read (list_canvas_items) before replying.
8) End every turn with plain text only (no JSON, no markdown tables), max 2 short sentences.
9) For linking a card to another canvas, always use `link_canvas_item(source_canvas_id, item_id, target_canvas_id)`.
10) For moving a card across canvases, always use `move_canvas_item(source_canvas_id, target_canvas_id, item_id)`.
11) Never claim a move/update/create succeeded unless the tool returned success and a verification read confirms it.
12) If user asks to open/switch/go to another canvas, call `navigate_to_canvas` to trigger UI navigation.

Operational defaults:
- New insight defaults: type=insight, col_span=4, row_span=1, variant=success.
- If required fields are missing, infer safe defaults and proceed.
- If a tool fails, explain plainly and suggest the next single action.

Available component types:
{component_types_csv}
"""
    extra = (extra_instructions or "").strip()
    if not extra:
        return base.strip()
    return f"{base.strip()}\n\nAdditional agent instructions:\n{extra}"


def install_canvas_tools(
    agent,
    get_store: Callable[[str], Any],
    list_canvas_ids: Callable[[], list[str]],
    publish_canvas_message: Callable[[str], None] | None = None,
) -> None:
    def _resolve_canvas_id(ctx: RunContext[Any], canvas_id: str = "") -> str:
        selected = (canvas_id or "").strip()
        if selected:
            return selected
        deps = getattr(ctx, "deps", None)
        canvas = None
        if isinstance(deps, dict):
            canvas = deps.get("pylogue_canvas")
        else:
            canvas = getattr(deps, "pylogue_canvas", None)
        if isinstance(canvas, dict):
            current = str(canvas.get("current_canvas_id") or "").strip()
            if current:
                return current
        return "main"

    @agent.tool
    def get_current_canvas(ctx: RunContext[Any]):
        """Return the current canvas id for this chat session."""
        return _resolve_canvas_id(ctx, "")

    @agent.tool
    def list_canvases(ctx: RunContext[Any]):
        """List available canvas ids as comma-separated values."""
        _ = ctx
        return ",".join(list_canvas_ids())

    @agent.tool
    def list_canvas_items(ctx: RunContext[Any], canvas_id: str = "", limit: int = 12, offset: int = 0):
        """CSV read: item_id, component_type, item_description, title, content."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return store.list_item_summaries(limit=limit, offset=offset)

    @agent.tool
    def get_item_fields(
        ctx: RunContext[Any],
        canvas_id: str = "",
        item_id: str = "",
        component_type: str = "",
    ):
        """Return comma-separated available fields. Prefer item_id; fallback to component_type."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return store.get_item_fields(item_id=item_id or None, component_type=component_type or None)

    @agent.tool
    def get_canvas_item(
        ctx: RunContext[Any],
        canvas_id: str = "",
        item_id: str = "",
        fields_csv: str = "",
    ):
        """CSV read for one item. fields_csv is required, e.g. 'id,title,content'."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return store.get_item(item_id=item_id, fields_csv=fields_csv)

    @agent.tool
    def create_canvas_item(ctx: RunContext[Any], canvas_id: str = "", item: dict | None = None):
        """Create a new canvas item."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return store.create_item(item or {})

    @agent.tool
    def update_canvas_item(
        ctx: RunContext[Any],
        canvas_id: str = "",
        item_id: str = "",
        patch: dict | None = None,
    ):
        """Update fields on a canvas item by id."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return store.update_item(item_id, patch or {})

    @agent.tool
    def delete_canvas_item(ctx: RunContext[Any], canvas_id: str = "", item_id: str = ""):
        """Delete a canvas item by id."""
        store = get_store(_resolve_canvas_id(ctx, canvas_id))
        return {"deleted": store.delete_item(item_id)}

    @agent.tool
    def link_canvas_item(
        ctx: RunContext[Any],
        source_canvas_id: str = "main",
        item_id: str = "",
        target_canvas_id: str = "",
    ):
        """Deterministically link a source card to a target canvas via drilldown_canvas_id."""
        source_canvas_id = _resolve_canvas_id(ctx, source_canvas_id)
        target_canvas_id = (target_canvas_id or "").strip()
        item_id = (item_id or "").strip()
        if not item_id:
            return {"linked": False, "error": "item_id is required"}
        if not target_canvas_id:
            return {"linked": False, "error": "target_canvas_id is required"}

        source_store = get_store(source_canvas_id)
        if source_store.get_item(item_id=item_id, fields_csv="id") is None:
            return {
                "linked": False,
                "error": f"item '{item_id}' not found in canvas '{source_canvas_id}'",
            }

        # Ensure target canvas exists in store map even if currently empty.
        get_store(target_canvas_id)
        updated = source_store.update_item(item_id, {"drilldown_canvas_id": target_canvas_id})
        if updated is None:
            return {"linked": False, "error": "update failed unexpectedly"}
        return {
            "linked": True,
            "source_canvas_id": source_canvas_id,
            "item_id": item_id,
            "target_canvas_id": target_canvas_id,
        }

    @agent.tool
    def move_canvas_item(
        ctx: RunContext[Any],
        source_canvas_id: str = "",
        target_canvas_id: str = "",
        item_id: str = "",
    ):
        """Move one item from source canvas to target canvas in a single deterministic operation."""
        source_canvas_id = _resolve_canvas_id(ctx, source_canvas_id)
        target_canvas_id = (target_canvas_id or "").strip()
        item_id = (item_id or "").strip()
        if not item_id:
            return {"moved": False, "error": "item_id is required"}
        if not target_canvas_id:
            return {"moved": False, "error": "target_canvas_id is required"}
        if source_canvas_id == target_canvas_id:
            return {"moved": False, "error": "source and target canvas are the same"}

        source_store = get_store(source_canvas_id)
        target_store = get_store(target_canvas_id)
        source_items = source_store.list_items()
        payload = next((deepcopy(item) for item in source_items if str(item.get("id")) == item_id), None)
        if payload is None:
            return {
                "moved": False,
                "error": f"item '{item_id}' not found in canvas '{source_canvas_id}'",
            }

        # Avoid id collisions in target canvas.
        target_ids = {str(item.get("id")) for item in target_store.list_items()}
        if str(payload.get("id")) in target_ids:
            payload.pop("id", None)

        created = target_store.create_item(payload)
        deleted = source_store.delete_item(item_id)
        if not deleted:
            # Best-effort rollback if source delete unexpectedly fails.
            target_store.delete_item(str(created.get("id")))
            return {"moved": False, "error": "failed to delete source item"}

        return {
            "moved": True,
            "source_canvas_id": source_canvas_id,
            "target_canvas_id": target_canvas_id,
            "source_item_id": item_id,
            "target_item_id": created.get("id"),
        }

    @agent.tool
    def navigate_to_canvas(
        ctx: RunContext[Any],
        canvas_id: str = "",
        from_canvas_id: str = "",
    ):
        """Trigger navigation of the left canvas panel to another canvas."""
        target = (canvas_id or "").strip()
        if not target:
            return {"ok": False, "error": "canvas_id is required"}
        available = set(list_canvas_ids())
        if target not in available:
            return {"ok": False, "error": f"canvas '{target}' not found"}
        source = _resolve_canvas_id(ctx, from_canvas_id)
        page_href = f"/canvas/{target}?from={source}"
        panel_href = f"/canvas/{target}/panel?from={source}"
        if not callable(publish_canvas_message):
            return {"ok": False, "error": "canvas navigation transport unavailable"}
        payload = {"page_href": page_href, "panel_href": panel_href}
        publish_canvas_message("canvas_navigate:" + json.dumps(payload, ensure_ascii=True))
        return {"ok": True, "canvas_id": target}
