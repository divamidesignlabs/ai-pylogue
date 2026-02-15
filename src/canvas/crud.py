from copy import deepcopy
from typing import Any
from uuid import uuid4


class CanvasItemCRUD:
    SUMMARY_FIELDS = (
        "id",
        "type",
        "title",
        "variant",
        "col_span",
        "row_span",
        "class",
        "tw",
    )
    DETAIL_LEVEL_FIELDS = {
        "scan": ("id", "type", "title", "variant"),
        "focus": ("id", "type", "title", "variant", "col_span", "row_span", "class", "tw"),
    }
    GET_ITEM_DEFAULT_FIELDS = ("id", "item_description")

    def __init__(self, initial_items: list[dict[str, Any]] | None = None):
        self._items = deepcopy(initial_items or [])

    def list_item_summaries(self, limit: int = 12, offset: int = 0) -> dict[str, Any]:
        return self._list_item_summaries(limit=limit, offset=offset, fields=self.GET_ITEM_DEFAULT_FIELDS)

    def _list_item_summaries(
        self,
        limit: int = 12,
        offset: int = 0,
        fields: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        fields = tuple(fields) if fields else self.SUMMARY_FIELDS
        total = len(self._items)
        start = max(0, int(offset))
        size = max(1, int(limit))
        end = min(total, start + size)
        page = self._items[start:end]
        rows = [self._project(item, fields, compact=True) for item in page]
        next_offset = end if end < total else None
        return {
            "fields": list(fields),
            "rows": rows,
            "offset": start,
            "limit": size,
            "next_offset": next_offset,
            "total": total,
        }

    def _get_item_raw(self, item_id: str) -> dict[str, Any] | None:
        for item in self._items:
            if item.get("id") == item_id:
                return deepcopy(item)
        return None

    def get_item(
        self, item_id: str, fields: list[str] | tuple[str, ...] | None = None
    ) -> dict[str, Any] | None:
        item = self._get_item_raw(item_id)
        if item is None:
            return None
        picked = tuple(fields) if fields else self.GET_ITEM_DEFAULT_FIELDS
        return self._project(item, picked)

    def get_item_detail(
        self,
        item_id: str,
        fields: list[str] | tuple[str, ...] | None = None,
        level: str = "focus",
    ) -> dict[str, Any] | None:
        return self.get_item_detail_compact(item_id=item_id, fields=fields, level=level)

    def get_item_detail_compact(
        self,
        item_id: str,
        fields: list[str] | tuple[str, ...] | None = None,
        level: str = "focus",
    ) -> dict[str, Any] | None:
        item = self._get_item_raw(item_id)
        if item is None:
            return None
        if fields:
            picked = tuple(fields)
        elif level == "full":
            picked = tuple(item.keys())
        else:
            picked = self.DETAIL_LEVEL_FIELDS.get(level, self.DETAIL_LEVEL_FIELDS["focus"])
        return {
            "fields": list(picked),
            "row": self._project(item, picked, compact=True),
            "level": level,
        }

    def create_item(self, item: dict[str, Any]) -> dict[str, Any]:
        created = deepcopy(item)
        created["id"] = str(created.get("id") or uuid4())
        if self._get_item_raw(created["id"]):
            raise ValueError(f"Item with id '{created['id']}' already exists.")
        self._items.append(created)
        return deepcopy(created)

    def update_item(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        for index, item in enumerate(self._items):
            if item.get("id") != item_id:
                continue
            updated = deepcopy(item)
            updated.update(deepcopy(patch))
            updated["id"] = item_id
            self._items[index] = updated
            return deepcopy(updated)
        return None

    def delete_item(self, item_id: str) -> bool:
        for index, item in enumerate(self._items):
            if item.get("id") == item_id:
                self._items.pop(index)
                return True
        return False

    @staticmethod
    def _project(
        item: dict[str, Any], fields: list[str] | tuple[str, ...], compact: bool = False
    ) -> dict[str, Any] | list[Any]:
        if compact:
            return [deepcopy(item.get(field)) if field in item else None for field in fields]
        return {field: deepcopy(item.get(field)) for field in fields if field in item}
