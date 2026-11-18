"""Defines launcher items and tabs, and the helpers that detect, name and locate their targets."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

# File types that start a program or point at one. They get the "App" label.
APP_SUFFIXES = {".app", ".exe", ".lnk", ".url", ".desktop", ".appimage", ".bat", ".cmd"}


@dataclass
class Item:
    id: str
    kind: str  # "app", "file", "folder" or "link"
    name: str
    target: str  # A URL for links. A path for everything else, relative when inside the base folder.
    custom_name: str | None = (
        None  # Set by Rename. The name above stays as the original.
    )

    @property
    def label(self) -> str:
        """The name shown on the tile: the custom name if there is one."""
        return self.custom_name or self.name


@dataclass
class Tab:
    id: str
    name: str
    items: list[Item] = field(default_factory=list)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def normalise_url(text: str) -> str | None:
    """Return a full http(s) URL for the text, or None if it is not a web address."""
    text = text.strip()
    if not text or "\\" in text or any(ch.isspace() for ch in text):
        return None
    if "://" not in text:
        if "." not in text.split("/")[0]:
            return None
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return text


def url_domain(url: str) -> str:
    host = urlparse(url).hostname or url
    return host.removeprefix("www.")


def detect_kind(target: str) -> str:
    """Work out what sort of item a dropped or picked target is."""
    if target.lower().startswith(("http://", "https://")):
        return "link"
    path = Path(target)
    if path.suffix.lower() in APP_SUFFIXES:
        return "app"
    if path.is_dir():
        return "folder"
    return "file"


def display_name(target: str, kind: str) -> str:
    if kind == "link":
        return url_domain(target)
    path = Path(target)
    if kind == "app":
        return path.stem or path.name
    return path.name or str(path)


def to_stored(path: str, base: Path) -> str:
    """Store a path relative to the base folder when it is inside it, so it survives a move."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_target(item: Item, base: Path) -> str:
    """Return the full path or URL to open for an item."""
    if item.kind == "link":
        return item.target
    path = Path(item.target)
    return str(path if path.is_absolute() else (base / path))
