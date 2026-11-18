"""Tile and grid layout tests: columns follow the window width, and tile content is centred."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from osprey_launcher.app import GAP, MARGIN, Tile, TileGrid, tile_size
from osprey_launcher.theme import PALETTES, stylesheet


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(stylesheet(PALETTES["dark"], "monospace"))
    return application


def make_grid(app, count: int = 10, names: bool = True, types: bool = True):
    """A tile grid inside a scroll area, set up the same way as the main window."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    grid = TileGrid()
    scroll.setWidget(grid)
    tiles = [
        Tile(
            str(i), f"Item {i}", "App", QPixmap(40, 40), i + 1, False, "", names, types
        )
        for i in range(count)
    ]
    grid.set_tiles(tiles, tile_size(names, types))
    scroll.show()
    return scroll, grid


def resize(app, scroll: QScrollArea, width: int) -> None:
    scroll.resize(width, 500)
    app.processEvents()


def expected_columns(grid: TileGrid, viewport_width: int) -> int:
    return max(1, (viewport_width - 2 * MARGIN + GAP) // (grid.tile_w + GAP))


def test_columns_shrink_when_window_narrows(app):
    scroll, grid = make_grid(app)
    resize(app, scroll, 1300)
    wide = grid.columns
    resize(app, scroll, 700)
    viewport = scroll.viewport().width()
    assert grid.columns < wide
    assert grid.width() == viewport
    assert grid.columns == expected_columns(grid, viewport)


def test_no_tile_extends_past_the_visible_area(app):
    scroll, grid = make_grid(app)
    for width in (1300, 1000, 600, 420, 1100):
        resize(app, scroll, width)
        right = max(t.geometry().right() for t in grid.tiles)
        assert right < scroll.viewport().width(), f"tile off screen at {width} px"


def test_columns_grow_when_window_widens(app):
    scroll, grid = make_grid(app)
    resize(app, scroll, 600)
    narrow = grid.columns
    resize(app, scroll, 1300)
    assert grid.columns > narrow


@pytest.mark.parametrize("names,types", [(True, False), (False, False)])
def test_compact_tiles_reflow_too(app, names, types):
    scroll, grid = make_grid(app, names=names, types=types)
    resize(app, scroll, 1300)
    resize(app, scroll, 500)
    assert grid.columns == expected_columns(grid, scroll.viewport().width())


def test_one_column_minimum(app):
    scroll, grid = make_grid(app, count=3)
    resize(app, scroll, 120)
    assert grid.columns == 1


def make_tile(app, name: str, star: bool = False) -> Tile:
    pixmap = QPixmap(12, 12) if star else None
    tile = Tile("1", name, "File", QPixmap(40, 40), 1, False, "", True, True, pixmap)
    tile.show()
    app.processEvents()
    return tile


def label(tile: Tile, name: str) -> QLabel:
    return tile.findChild(QLabel, name)


def test_icon_and_name_are_centred_and_key_stays_in_corner(app):
    tile = make_tile(app, "Budget 2026.xlsx", star=True)
    middle = tile.width() / 2
    icon = next(c for c in tile.findChildren(QLabel) if c.pixmap() and c.width() == 40)
    assert abs(icon.geometry().center().x() + 0.5 - middle) <= 1
    assert label(tile, "tileName").alignment() & Qt.AlignHCenter
    key = label(tile, "keycap")
    assert key.geometry().right() == tile.width() - 12 - 1
    star = label(tile, "starMark")
    assert star.geometry().right() < key.geometry().left()


def test_long_name_fits_inside_the_tile(app):
    for name in ("Quarterly planning workshop notes final v3.docx", "W" * 40):
        tile = make_tile(app, name)
        name_label = label(tile, "tileName")
        width = QFontMetrics(name_label.font()).horizontalAdvance(name_label.text())
        assert width <= name_label.width(), name
