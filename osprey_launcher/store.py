"""Keeps the launcher's tabs, items and settings. Saves them as JSON, plus a readable YAML backup."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import backup
from .models import (
    Item,
    Tab,
    detect_kind,
    display_name,
    new_id,
    resolve_target,
    to_stored,
)

DATA_FILE = "launcher.json"
SCHEMA_VERSION = 1
THEMES = ("system", "light", "dark")


class Store:
    """All launcher data. Every change is saved straight away."""

    def __init__(self, data_dir: Path, base_dir: Path):
        self.data_dir = data_dir
        self.base_dir = base_dir
        self.tabs: list[Tab] = []
        self.theme = "system"
        self.show_names = True
        self.show_types = True
        self.starred: list[str] = []  # Item IDs, in the order shown in the Starred tab.
        self.restored_from_backup = (
            False  # True when the data file was unreadable at start.
        )
        self.load()

    @property
    def path(self) -> Path:
        return self.data_dir / DATA_FILE

    @property
    def backup_path(self) -> Path:
        return self.data_dir / backup.BACKUP_FILE

    # Loading and saving

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
            if self._load_backup_instead():
                return
        self.theme = raw.get("theme") if raw.get("theme") in THEMES else "system"
        display = raw.get("display") if isinstance(raw.get("display"), dict) else {}
        self.show_names = display.get("names", True) is not False
        self.show_types = display.get("types", True) is not False
        self.tabs = []
        for t in raw.get("tabs", []):
            items = [
                Item(i["id"], i["kind"], i["name"], i["target"], i.get("custom_name"))
                for i in t.get("items", [])
                if {"id", "kind", "name", "target"} <= i.keys()
            ]
            self.tabs.append(
                Tab(t.get("id") or new_id(), t.get("name") or "Tab", items)
            )
        if not self.tabs:
            self.tabs = [Tab(new_id(), "Home")]
        known = {i.id for t in self.tabs for i in t.items}
        starred = raw.get("starred") if isinstance(raw.get("starred"), list) else []
        self.starred = list(dict.fromkeys(i for i in starred if i in known))
        if self.path.exists() and not self.backup_path.exists():
            backup.write(self.backup_path, self.tabs, self.starred, self.base_dir)

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "schema": SCHEMA_VERSION,
            "theme": self.theme,
            "display": {"names": self.show_names, "types": self.show_types},
            "starred": self.starred,
            "tabs": [asdict(t) for t in self.tabs],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        backup.write(self.backup_path, self.tabs, self.starred, self.base_dir)

    def _load_backup_instead(self) -> bool:
        """When the data file is missing or broken, load the YAML backup if there is one.

        A broken data file is kept as launcher.json.broken-<time>, so nothing is lost.
        """
        if not self.backup_path.exists():
            return False
        try:
            tabs, starred, _skipped = backup.parse(
                self.backup_path.read_text(encoding="utf-8"), self.base_dir
            )
        except (OSError, backup.BackupError):
            return False
        if self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.path.replace(self.path.with_name(f"{DATA_FILE}.broken-{stamp}"))
        self.tabs, self.starred = tabs, starred
        self.restored_from_backup = True
        self.save()
        return True

    def restore(self, tabs: list[Tab], starred: list[str]) -> None:
        """Replace all tabs and items, for example with the contents of a backup file."""
        if not tabs:
            return
        self.tabs = tabs
        known = {i.id for t in tabs for i in t.items}
        self.starred = [i for i in starred if i in known]
        self.save()

    # Tabs

    def tab(self, tab_id: str) -> Tab:
        return next(t for t in self.tabs if t.id == tab_id)

    def add_tab(self, name: str) -> Tab:
        tab = Tab(new_id(), name.strip() or "Tab")
        self.tabs.append(tab)
        self.save()
        return tab

    def rename_tab(self, tab_id: str, name: str) -> None:
        if name.strip():
            self.tab(tab_id).name = name.strip()
            self.save()

    def remove_tab(self, tab_id: str) -> None:
        if len(self.tabs) > 1:
            gone = {i.id for i in self.tab(tab_id).items}
            self.tabs = [t for t in self.tabs if t.id != tab_id]
            self.starred = [i for i in self.starred if i not in gone]
            self.save()

    # Items

    def add_targets(self, tab_id: str, targets: list[str]) -> list[Item]:
        """Add files, folders, apps or URLs to a tab. Targets already in the tab are skipped."""
        tab = self.tab(tab_id)
        existing = {resolve_target(i, self.base_dir) for i in tab.items}
        added = []
        for raw in targets:
            kind = detect_kind(raw)
            if kind == "link":
                target = full = raw
            else:
                target = to_stored(raw, self.base_dir)
                full = str(Path(raw).resolve())
            if full in existing:
                continue
            existing.add(full)
            item = Item(new_id(), kind, display_name(full, kind), target)
            tab.items.append(item)
            added.append(item)
        if added:
            self.save()
        return added

    def find(self, item_id: str) -> tuple[Tab, Item]:
        for tab in self.tabs:
            for item in tab.items:
                if item.id == item_id:
                    return tab, item
        raise KeyError(item_id)

    def rename_item(self, item_id: str, name: str) -> None:
        """Set a custom name. An empty name, or the original name, clears it."""
        item = self.find(item_id)[1]
        name = name.strip()
        item.custom_name = name if name and name != item.name else None
        self.save()

    def relocate_item(self, item_id: str, new_path: str) -> None:
        item = self.find(item_id)[1]
        item.target = to_stored(new_path, self.base_dir)
        self.save()

    def move_item(self, item_id: str, tab_id: str, index: int | None = None) -> bool:
        """Move an item to a tab, at a position or at the end.

        The index is an insertion point in the tab as it looks before the move,
        so dropping between tiles 2 and 3 passes 2. Returns False if nothing changed.
        """
        source, item = self.find(item_id)
        target = self.tab(tab_id)
        if source is target:
            changed = _reorder(target.items, item, index)
        else:
            source.items.remove(item)
            _insert(target.items, item, index)
            changed = True
        if changed:
            self.save()
        return changed

    def remove_item(self, item_id: str) -> None:
        tab, item = self.find(item_id)
        tab.items.remove(item)
        if item_id in self.starred:
            self.starred.remove(item_id)
        self.save()

    # Starred

    def is_starred(self, item_id: str) -> bool:
        return item_id in self.starred

    def set_starred(self, item_id: str, on: bool, index: int | None = None) -> bool:
        """Star or unstar an item. A new star goes at the index, or at the end."""
        self.find(item_id)
        if on == (item_id in self.starred):
            return False
        if on:
            _insert(self.starred, item_id, index)
        else:
            self.starred.remove(item_id)
        self.save()
        return True

    def move_starred(self, item_id: str, index: int) -> bool:
        """Reorder the Starred tab. The index works as in move_item."""
        changed = _reorder(self.starred, item_id, index)
        if changed:
            self.save()
        return changed

    def starred_items(self) -> list[tuple[Tab, Item]]:
        return [self.find(item_id) for item_id in self.starred]

    def target_exists(self, item: Item) -> bool:
        return item.kind == "link" or Path(resolve_target(item, self.base_dir)).exists()

    def search(self, text: str) -> list[tuple[Tab, Item]]:
        """Match the shown name, the original name, and the file name or web address.

        Folder paths are not searched.
        """
        needle = text.strip().lower()
        if not needle:
            return []

        def haystack(item: Item) -> str:
            extra = item.target if item.kind == "link" else Path(item.target).name
            return f"{item.label}\n{item.name}\n{extra}".lower()

        return [
            (tab, item)
            for tab in self.tabs
            for item in tab.items
            if needle in haystack(item)
        ]

    def set_theme(self, theme: str) -> None:
        if theme in THEMES:
            self.theme = theme
            self.save()

    def set_display(self, names: bool | None = None, types: bool | None = None) -> None:
        """Choose whether tiles show the item name and the type line under the icon."""
        if names is not None:
            self.show_names = names
        if types is not None:
            self.show_types = types
        self.save()


def _insert(items: list, value, index: int | None) -> None:
    if index is None or index > len(items):
        index = len(items)
    items.insert(max(index, 0), value)


def _reorder(items: list, value, index: int | None) -> bool:
    """Move a value within a list. The index is an insertion point before the move."""
    old = items.index(value)
    if index is None or index in (old, old + 1):
        return False
    items.pop(old)
    _insert(items, value, index - 1 if index > old else index)
    return True
