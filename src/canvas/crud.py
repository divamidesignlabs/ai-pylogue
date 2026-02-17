from copy import deepcopy
import re
from typing import Any, Callable


class CanvasItemCRUD:
    SUMMARY_FIELDS = ("id", "type", "item_description", "title", "content")
    KNOWN_FIELDS_BASE = (
        "id",
        "type",
        "item_description",
        "title",
        "content",
        "col_span",
        "row_span",
        "variant",
        "drilldown_canvas_id",
        "class",
        "tw",
        "className",
        "canvas_id",
        "component_type",
        "html",
    )

    def __init__(
        self,
        initial_items: list[dict[str, Any]] | None = None,
        on_change: Callable[[], None] | None = None,
        id_prefix: str = "c1",
    ):
        self._items = deepcopy(initial_items or [])
        self._on_change = on_change
        self._id_prefix = self._normalize_id_prefix(id_prefix)

    def list_items(self) -> list[dict[str, Any]]:
        return deepcopy(self._items)

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = deepcopy(items or [])

    def list_component_types(self) -> list[str]:
        return sorted({str(item.get("type", "")).strip() for item in self._items if item.get("type")})

    def list_item_summaries(
        self,
        limit: int = 12,
        offset: int = 0,
        fields: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        total = len(self._items)
        start = max(0, int(offset))
        size = max(1, int(limit))
        end = min(total, start + size)
        page = self._items[start:end]
        projected_fields = self._normalize_projection_fields(fields, default=self.SUMMARY_FIELDS)
        items = [self._project(item, projected_fields) for item in page]
        return {
            "items": items,
            "total": total,
            "offset": start,
            "limit": size,
            "has_more": end < total,
        }

    def _get_item_raw(self, item_id: str) -> dict[str, Any] | None:
        for item in self._items:
            if item.get("id") == item_id:
                return deepcopy(item)
        return None

    def get_item(self, item_id: str, fields: list[str] | tuple[str, ...] | None = None) -> dict[str, Any] | None:
        item = self._get_item_raw(item_id)
        if item is None:
            return None
        if fields:
            projected_fields = self._normalize_projection_fields(fields, default=self.SUMMARY_FIELDS)
            return self._project(item, projected_fields)
        return item

    def list_known_fields(self) -> list[str]:
        fields = set(self.KNOWN_FIELDS_BASE)
        for item in self._items:
            fields.update(str(key) for key in item.keys())
        return sorted(fields)

    def validate_projection_fields(self, fields: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
        requested = [str(field).strip() for field in (fields or []) if str(field).strip()]
        allowed = self.list_known_fields()
        allowed_set = set(allowed)
        unknown = [field for field in requested if field not in allowed_set]
        return {"requested": requested, "unknown": unknown, "allowed": allowed}

    def create_item(self, item: dict[str, Any]) -> dict[str, Any]:
        created = deepcopy(item)
        created["type"] = str(created.get("type") or "insight")
        created["col_span"] = int(created.get("col_span") or 4)
        created["row_span"] = int(created.get("row_span") or 1)
        created["variant"] = str(created.get("variant") or "success")
        if not created.get("item_description"):
            title = str(created.get("title") or "Untitled")
            created["item_description"] = f"{created['type']} card: {title}"
        created["id"] = str(created.get("id") or self._next_short_id())
        if self._get_item_raw(created["id"]):
            raise ValueError(f"Item with id '{created['id']}' already exists.")
        self._items.append(created)
        self._emit_change()
        return deepcopy(created)

    def update_item(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        for index, item in enumerate(self._items):
            if item.get("id") != item_id:
                continue
            updated = deepcopy(item)
            updated.update(deepcopy(patch))
            updated["id"] = item_id
            self._items[index] = updated
            self._emit_change()
            return deepcopy(updated)
        return None

    def delete_item(self, item_id: str) -> bool:
        for index, item in enumerate(self._items):
            if item.get("id") == item_id:
                self._items.pop(index)
                self._emit_change()
                return True
        return False

    def _emit_change(self) -> None:
        if callable(self._on_change):
            self._on_change()

    def _next_short_id(self) -> str:
        max_n = 0
        pattern = re.compile(rf"^{re.escape(self._id_prefix)}\.i(\d+)$")
        for item in self._items:
            raw = str(item.get("id", ""))
            match = pattern.match(raw)
            if match:
                max_n = max(max_n, int(match.group(1)))
        return f"{self._id_prefix}.i{max_n + 1}"

    @staticmethod
    def _normalize_id_prefix(prefix: str) -> str:
        raw = str(prefix or "").strip().lower()
        if re.fullmatch(r"c\d+", raw):
            return raw
        return "c1"

    @staticmethod
    def _project(
        item: dict[str, Any], fields: list[str] | tuple[str, ...], compact: bool = False
    ) -> dict[str, Any] | list[Any]:
        if compact:
            return [deepcopy(item.get(field)) if field in item else None for field in fields]
        return {field: deepcopy(item.get(field)) for field in fields if field in item}

    def _normalize_projection_fields(
        self,
        fields: list[str] | tuple[str, ...] | None,
        default: list[str] | tuple[str, ...],
    ) -> tuple[str, ...]:
        if not fields:
            return tuple(default)
        validation = self.validate_projection_fields(fields)
        if validation["unknown"]:
            raise ValueError(
                f"unknown_fields:{','.join(validation['unknown'])};"
                f"allowed:{','.join(validation['allowed'])}"
            )
        return tuple(validation["requested"])
