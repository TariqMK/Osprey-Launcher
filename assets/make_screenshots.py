"""Retakes the README screenshots and GIF from the real app, filled with made-up sample data.

Writes assets/screenshots/<view>-light.png and <view>-dark.png at 2x (2000 x 1080 px) for the
main, search, starred, data-menu, labels, rows and large views, and assets/gifs/drag-to-reorder.gif (dark,
1000 px wide). The GIF needs Pillow, which the "dev" extra installs.

Run from the project root with the project's environment, on Windows, macOS or Linux:
  .venv/bin/python assets/make_screenshots.py [--version 1.2.0]

The version in the header is the newest release tag (vX.Y.Z), so the screenshots never show the
development version. Pass --version to show a release that is about to be made. The version is
set only inside this script; the source keeps its development version.

Privacy: the app runs on a new temporary data folder with generated sample files, makes no
network requests, and only its content area is captured (no system title bar or desktop).
Qt's offscreen platform is used at a fixed 2x scale, so every system gives the same pixel size
and the same generic file icons. Native icons are avoided on purpose: they would differ per
system and reveal which apps are installed on the computer that takes the screenshots.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QIODevice, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QMenu

try:
    from PIL import Image
except ImportError:
    sys.exit(
        'Pillow is missing. Install the dev tools first: .venv/bin/pip install -e ".[dev]"'
    )

import osprey_launcher.app as app_module
from osprey_launcher.app import APP_NAME, MainWindow
from osprey_launcher.app import STARRED as STARRED_TAB
from osprey_launcher.icons import IconCache, app_icon
from osprey_launcher.store import Store

OUT = ROOT / "assets" / "screenshots"
GIF_OUT = ROOT / "assets" / "gifs"
GIF_FPS = 15
TILE_RADIUS = 12  # Matches the tile corner radius in theme.py.
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
    # Rows show each item's folder with the home folder as ~. Point home at the sample folder,
    # so the pictures show ~/Documents and never the real home or temporary folder.
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
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


def capture(window: MainWindow, app: QApplication, name: str, extra=None) -> None:
    """Save the window content in both themes. extra(image) can paint on top, for example a menu."""
    for theme in ("light", "dark"):
        window.store.set_theme(theme)
        window.apply_theme()
        window.refresh()
        app.processEvents()
        image = window.centralWidget().grab()
        if extra:
            extra(image)
        path = OUT / f"{name}-{theme}.png"
        image.save(str(path))
        print(f"Wrote {path.relative_to(ROOT)} ({image.width()} x {image.height()} px)")


def item_id(store: Store, name: str) -> str:
    return next(i.id for t in store.tabs for i in t.items if i.name == name)


def paint_data_menu(window: MainWindow, app: QApplication):
    """Return a painter for capture() that draws the data menu open above its button."""
    return paint_menu(window, app, window.data_menu, window.data_button, highlight=-1)


def paint_view_menu(window: MainWindow, app: QApplication):
    """Return a painter for capture() that draws the layout and size menu open above its button."""
    return paint_menu(
        window, app, window.view_menu, window.view_button, align_right=True
    )


def paint_menu(window, app, open_menu, button, highlight=None, align_right=False):
    """Return a painter for capture() that draws a footer menu open above its button."""

    def extra(image: QPixmap) -> None:
        menus: list[QMenu] = []
        original = window._menu_above
        window._menu_above = lambda menu, button: menus.append(
            menu
        )  # Keep it open, don't block.
        try:
            open_menu()
        finally:
            window._menu_above = original
        menu = menus[0]
        root = window.centralWidget()
        top_left = button.mapTo(root, QPoint(0, 0))
        menu.popup(button.mapToGlobal(QPoint(0, 0)))
        if highlight is not None:
            menu.setActiveAction(menu.actions()[highlight])
        app.processEvents()
        shot = menu.grab()
        size = shot.deviceIndependentSize()
        at = top_left - QPoint(0, int(size.height()) + 4)
        if align_right:
            at.setX(top_left.x() + button.width() - int(size.width()))
        painter = QPainter(image)
        painter.drawPixmap(at, shot)
        painter.end()
        menu.close()
        menu.deleteLater()

    return extra


def to_pil(pixmap: QPixmap) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    image = Image.open(BytesIO(bytes(buffer.data()))).convert("RGB")
    return image.resize((image.width // 2, image.height // 2), Image.LANCZOS)


def make_drag_gif(window: MainWindow, app: QApplication) -> None:
    """Record a tile being dragged to a new place in the Work tab, frame by frame.

    The frames show the same marks the app shows during a real drag: the faded source tile,
    the tile under the pointer and the accent line where it will land.
    """
    store = window.store
    store.set_theme("dark")
    window.apply_theme()
    window.select_tab(store.tabs[0].id)
    window.refresh()
    app.processEvents()
    root, grid = window.centralWidget(), window.grid
    source = grid.tiles[0]
    target_index = 4  # Before the fifth tile, measured before the move.
    grid.show_indicator(target_index)
    end = grid.indicator.geometry().center()
    grid.indicator.hide()
    start = source.geometry().center()
    lift = source.grab()
    hotspot = QPoint(lift.width() // 2, lift.height() // 2) / lift.devicePixelRatio()

    frames: list[tuple[Image.Image, int]] = []

    def frame(ms: int, pointer: QPoint | None = None) -> None:
        app.processEvents()
        image = root.grab()
        if pointer is not None:
            # A real drag pixmap is opaque; give the tile its card colour so nothing shows through.
            at = grid.mapTo(root, pointer) - hotspot
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(window.palette_values["card"]))
            painter.drawRoundedRect(QRect(at, source.size()), TILE_RADIUS, TILE_RADIUS)
            painter.drawPixmap(at, lift)
            painter.end()
        frames.append((to_pil(image), ms))

    tick = 1000 // GIF_FPS
    frame(900)
    fade = QGraphicsOpacityEffect(source)
    fade.setOpacity(0.3)
    source.setGraphicsEffect(fade)
    frame(200, start)
    steps = 18
    for n in range(1, steps + 1):
        t = n / steps
        t = t * t * (3 - 2 * t)  # Ease in and out.
        pointer = (QPointF(start) + (QPointF(end) - QPointF(start)) * t).toPoint()
        grid.show_indicator(grid.insertion_index(pointer))
        frame(tick, pointer)
    frame(400, end)
    source.setGraphicsEffect(None)
    grid.indicator.hide()
    store.move_item(source.item_id, store.tabs[0].id, target_index)
    window.refresh()
    frame(1800)

    images = [f for f, _ms in frames]
    palette = images[0].quantize(colors=128, method=Image.MEDIANCUT)
    paletted = [im.quantize(palette=palette, dither=Image.NONE) for im in images]
    GIF_OUT.mkdir(parents=True, exist_ok=True)
    path = GIF_OUT / "drag-to-reorder.gif"
    paletted[0].save(
        path,
        save_all=True,
        append_images=paletted[1:],
        duration=[ms for _f, ms in frames],
        loop=0,
        optimize=True,
    )
    size = path.stat().st_size / 1_000_000
    print(
        f"Wrote {path.relative_to(ROOT)} ({images[0].width} x {images[0].height} px, {size:.1f} MB)"
    )


def release_version() -> str:
    """The version to show: --version if given, else the newest vX.Y.Z tag, else the source's."""
    if "--version" in sys.argv:
        return sys.argv[sys.argv.index("--version") + 1].lstrip("v")
    try:
        tags = subprocess.run(
            ["git", "tag", "--list"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        tags = []
    plain = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if not plain:
        return app_module.__version__
    return max(plain, key=lambda t: tuple(int(n) for n in t[1:].split("."))).lstrip("v")


def main() -> int:
    app_module.__version__ = release_version()
    print(f"Header shows v{app_module.__version__}")
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

        window.select_tab(STARRED_TAB)
        capture(window, app, "starred")

        window.select_tab(store.tabs[0].id)
        capture(window, app, "data-menu", paint_data_menu(window, app))

        window.set_display(size=1)
        capture(window, app, "rows", paint_view_menu(window, app))
        window.set_display(size=5)
        capture(window, app, "large")
        window.set_display(size=3)

        make_drag_gif(window, app)

        store.rename_item(item_id(store, "Meeting notes.docx"), "Monday notes")
        window.set_display(types=False)
        capture(window, app, "labels")

        window.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
