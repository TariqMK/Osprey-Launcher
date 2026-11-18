"""Writes and reads the readable YAML backup of all tabs and items (osprey-backup.yaml)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from .models import (
    Item,
    Tab,
    detect_kind,
    display_name,
    new_id,
    normalise_url,
    resolve_target,
    to_stored,
)

BACKUP_FILE = "osprey-backup.yaml"
BACKUP_VERSION = 1
KINDS = ("app", "file", "folder", "link")

HEADER = """\
# Osprey Launcher backup
# Saved: {saved}
#
# Osprey Launcher writes this file after every change. It holds every tab and item.
# To load it back, select "Stored next to the app" at the bottom of the window,
# then select "Restore from backup...".
#
# You can edit this file. The next change in the app overwrites it, so restore
# your edits first, or edit a copy and restore the copy.
#
# Item fields:
#   position         Order in the tab, starting at 1.
#   name             Original name, from the file name or the web address.
#   custom_name      Name set with Rename. null means the original name is shown.
#   type             app, file, folder or link.
#   path / link      Full location of a file, folder or app, or a web address.
#   starred          true if the item shows in the Starred tab.
#   starred_position Order in the Starred tab, starting at 1. Only for starred items.

"""


class _IndentedDumper(yaml.SafeDumper):
    """Indents lists under their key, so nested tabs and items are easy to follow."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


class BackupError(ValueError):
    """The backup file can't be read. The message says why, in plain words."""


def dump(tabs: list[Tab], starred: list[str], base_dir: Path) -> str:
    """Return the backup text for all tabs, with full paths so it reads clearly."""
    star_position = {item_id: n for n, item_id in enumerate(starred, 1)}
    data = {"version": BACKUP_VERSION, "tabs": []}
    for tab_position, tab in enumerate(tabs, 1):
        items = []
        for position, item in enumerate(tab.items, 1):
            entry = {
                "position": position,
                "name": item.name,
                "custom_name": item.custom_name,
                "type": item.kind,
            }
            key = "link" if item.kind == "link" else "path"
            entry[key] = resolve_target(item, base_dir)
            entry["starred"] = item.id in star_position
            if item.id in star_position:
                entry["starred_position"] = star_position[item.id]
            items.append(entry)
        data["tabs"].append({"tab": tab.name, "position": tab_position, "items": items})
    body = yaml.dump(
        data, Dumper=_IndentedDumper, sort_keys=False, allow_unicode=True, width=1000
    )
    saved = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return HEADER.format(saved=saved) + body


def write(path: Path, tabs: list[Tab], starred: list[str], base_dir: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(dump(tabs, starred, base_dir), encoding="utf-8")
    tmp.replace(path)


def _sorted(entries: list[dict]) -> list[dict]:
    """Sort by the position field. Entries without one keep their place in the file."""
    keyed = [(_position(e, n), n, e) for n, e in enumerate(entries, 1)]
    return [e for _p, _n, e in sorted(keyed, key=lambda k: (k[0], k[1]))]


def _position(entry: dict, fallback: int) -> float:
    value = entry.get("position")
    return (
        value
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else fallback
    )


def parse(text: str, base_dir: Path) -> tuple[list[Tab], list[str], int]:
    """Read backup text. Returns the tabs, the starred item IDs in order, and how many items were skipped."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark else ""
        raise BackupError(f"The file is not valid YAML{where}.") from error
    if not isinstance(data, dict) or not isinstance(data.get("tabs"), list):
        raise BackupError(
            "The file has no list of tabs. It may not be an Osprey Launcher backup."
        )

    tabs: list[Tab] = []
    stars: list[tuple[float, int, str]] = []
    skipped = 0
    for raw_tab in _sorted([t for t in data["tabs"] if isinstance(t, dict)]):
        tab = Tab(new_id(), str(raw_tab.get("tab") or "Tab").strip() or "Tab")
        raw_items = [i for i in raw_tab.get("items") or [] if isinstance(i, dict)]
        skipped += len(raw_tab.get("items") or []) - len(raw_items)
        for raw in _sorted(raw_items):
            item = _item(raw, base_dir)
            if item is None:
                skipped += 1
                continue
            tab.items.append(item)
            if raw.get("starred") is True:
                order = _position({"position": raw.get("starred_position")}, 10**6)
                stars.append((order, len(stars), item.id))
        tabs.append(tab)
    if not tabs:
        raise BackupError("The file has no tabs.")
    starred = [item_id for _order, _n, item_id in sorted(stars)]
    return tabs, starred, skipped


def _item(raw: dict, base_dir: Path) -> Item | None:
    link = raw.get("link")
    path = raw.get("path")
    if isinstance(link, str) and normalise_url(link):
        target, full, kind = normalise_url(link), normalise_url(link), "link"
    elif isinstance(path, str) and path.strip():
        full = path.strip()
        kind = raw.get("type") if raw.get("type") in KINDS[:3] else detect_kind(full)
        target = to_stored(full, base_dir)
    else:
        return None
    name = raw.get("name")
    name = str(name).strip() if name not in (None, "") else display_name(full, kind)
    custom = raw.get("custom_name")
    custom = str(custom).strip() if custom not in (None, "") else None
    return Item(new_id(), kind, name, target, custom if custom != name else None)
