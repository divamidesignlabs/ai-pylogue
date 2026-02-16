from copy import deepcopy
import csv
import io
from typing import Any, Callable


class CanvasItemCRUD:
    SUMMARY_FIELDS = ("id", "type", "item_description")

    def __init__(
        self,
        initial_items: list[dict[str, Any]] | None = None,
        on_change: Callable[[], None] | None = None,
    ):
        self._items = deepcopy(initial_items or [])
        self._on_change = on_change

    def list_items(self) -> list[dict[str, Any]]:
        return deepcopy(self._items)

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._items = deepcopy(items or [])

    def list_component_types(self) -> str:
        types = sorted({str(item.get("type", "")).strip() for item in self._items if item.get("type")})
        return ", ".join(types)

    def list_item_summaries(self, limit: int = 12, offset: int = 0) -> str:
        total = len(self._items)
        start = max(0, int(offset))
        size = max(1, int(limit))
        end = min(total, start + size)
        page = self._items[start:end]
        rows = [
            [
                item.get("id", ""),
                item.get("type", ""),
                item.get("item_description", ""),
            ]
            for item in page
        ]
        _ = total, start, size, end  # pagination remains enforced by args; output stays pure CSV
        return self._to_csv(["item_id", "component_type", "item_description"], rows)

    def _get_item_raw(self, item_id: str) -> dict[str, Any] | None:
        for item in self._items:
            if item.get("id") == item_id:
                return deepcopy(item)
        return None

    def get_item(self, item_id: str, fields_csv: str) -> str | None:
        item = self._get_item_raw(item_id)
        if item is None:
            return None
        fields = [part.strip() for part in (fields_csv or "").split(",") if part.strip()]
        if not fields:
            raise ValueError("fields_csv is required and must be a comma-separated field list.")
        row = [item.get(field) for field in fields]
        return self._to_csv(fields, [row])

    def get_item_fields(self, item_id: str | None = None, component_type: str | None = None) -> str:
        if item_id:
            item = self._get_item_raw(item_id)
            if item is None:
                return ""
            return ",".join(item.keys())
        if component_type:
            fields: set[str] = set()
            for item in self._items:
                if str(item.get("type", "")) == component_type:
                    fields.update(item.keys())
            return ",".join(sorted(fields))
        fields: set[str] = set()
        for item in self._items:
            fields.update(item.keys())
        return ",".join(sorted(fields))

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
        for item in self._items:
            raw = str(item.get("id", ""))
            if raw.startswith("c") and raw[1:].isdigit():
                max_n = max(max_n, int(raw[1:]))
        return f"c{max_n + 1}"

    @staticmethod
    def _project(
        item: dict[str, Any], fields: list[str] | tuple[str, ...], compact: bool = False
    ) -> dict[str, Any] | list[Any]:
        if compact:
            return [deepcopy(item.get(field)) if field in item else None for field in fields]
        return {field: deepcopy(item.get(field)) for field in fields if field in item}

    @staticmethod
    def _to_csv(headers: list[str], rows: list[list[Any]]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        return buffer.getvalue().strip()
