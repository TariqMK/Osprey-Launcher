"""Retakes the README screenshots from the real app, filled with made-up sample data.

Writes assets/screenshots/<view>-light.png and <view>-dark.png at 2x (2000 x 1080 px).

Run from the project root with the project's environment, on Windows, macOS or Linux:
  .venv/bin/python assets/make_screenshots.py

Privacy: the app runs on a new temporary data folder with generated sample files, makes no
network requests, and only its content area is captured (no system title bar or desktop).
Qt's offscreen platform is used at a fixed 2x scale, so every system gives the same pixel size
and the same generic file icons. Native icons are avoided on purpose: they would differ per
system and reveal which apps are installed on the computer that takes the screenshots.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from osprey_launcher.app import APP_NAME, MainWindow
from osprey_launcher.icons import IconCache, app_icon
from osprey_launcher.store import Store

OUT = ROOT / "assets" / "screenshots"
SIZE = (1000, 540)  # logical px; saved at 2x

# Made-up sample data. Every name and address here is fictional.
TABS = {
    "Work": [
        "Documents/Budget 2026.xlsx",
        "Documents/Meeting notes.docx",
        "Documents/Field guide.pdf",
        "Documents/Projects/",
        "Documents/Invoices/",
        "Documents/Reports/",
        "https://example.com",
        "Pictures/Logo draft.png",
    ],
    "Studio": [
        "Documents/Client brief.pdf",
        "Pictures/Moodboard.png",
        "Documents/Studio files/",
        "https://portfolio.example.com",
    ],
    "Home": [
        "Documents/Passport scan.pdf",
        "Documents/Recipes/",
        "Pictures/Holiday 2025/",
        "https://news.example.org",
    ],
}
STARRED = ("Budget 2026.xlsx", "Projects", "example.com")
MISSING = "Pictures/Logo draft.png"  # created, added, then deleted to show the Not found state


def make_sample_files(home: Path) -> None:
    for entries in TABS.values():
        for entry in entries:
            if entry.startswith("https://"):
                continue
            path = home / entry
            if entry.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")


def build_store(work: Path) -> Store:
    home = work / "Alex"
    make_sample_files(home)
    data = work / "OspreyLauncher-data"
    store = Store(data, work)
    first = store.tabs[0]
    store.rename_tab(first.id, "Work")
    for index, (name, entries) in enumerate(TABS.items()):
        tab = first if index == 0 else store.add_tab(name)
        targets = [
            e if e.startswith("https://") else str(home / e.rstrip("/"))
            for e in entries
        ]
        store.add_targets(tab.id, targets)
    for _tab, item in [(t, i) for t in store.tabs for i in t.items]:
        if item.name in STARRED:
            store.set_starred(item.id, True)
    (home / MISSING).unlink()
    return store


def capture(window: MainWindow, app: QApplication, name: str) -> None:
    for theme in ("light", "dark"):
        window.store.set_theme(theme)
        window.apply_theme()
        window.refresh()
        app.processEvents()
        image = window.centralWidget().grab()
        path = OUT / f"{name}-{theme}.png"
        image.save(str(path))
        print(f"Wrote {path.relative_to(ROOT)} ({image.width()} x {image.height()} px)")


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="osprey-shots-"))
    try:
        store = build_store(work)
        icons = IconCache(store.data_dir)
        window = MainWindow(store, icons)
        window.resize(*SIZE)
        window.show()
        app.processEvents()

        window.select_tab(store.tabs[0].id)
        capture(window, app, "main")

        window.search.setText("port")
        capture(window, app, "search")
        window.search.clear()

        window.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
