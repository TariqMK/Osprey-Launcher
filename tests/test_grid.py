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


# Size slider: sizes 1-2 are rows, 3-5 are tiles with bigger icons.


def make_row(app, name: str, size: int = 1, missing: bool = False, star: bool = False):
    from osprey_launcher.app import icon_size

    pixmap = QPixmap(icon_size(size), icon_size(size))
    tile = Tile(
        "1",
        name,
        "~/Documents/Finance",
        pixmap,
        1,
        missing,
        "",
        True,
        True,
        QPixmap(12, 12) if star else None,
        size,
    )
    tile.show()
    app.processEvents()
    return tile


def test_tile_sizes_grow_with_the_slider():
    tiles = [tile_size(True, True, size) for size in (3, 4, 5)]
    assert tiles[0] == tile_size(True, True)  # Size 3 is the original tile.
    assert tiles[0].width() < tiles[1].width() < tiles[2].width()
    assert tiles[0].height() < tiles[1].height() < tiles[2].height()
    rows = [tile_size(True, True, size) for size in (1, 2)]
    assert all(r.height() < tiles[0].height() for r in rows)
    assert all(r.width() > r.height() * 4 for r in rows)  # Rows are wide and short.


def test_rows_lose_height_when_details_are_hidden():
    for size in (1, 2):
        assert (
            tile_size(True, False, size).height() < tile_size(True, True, size).height()
        )
        assert tile_size(False, True, size) == tile_size(True, True, size)


@pytest.mark.parametrize("size", [1, 2, 4, 5])
def test_every_size_reflows(app, size):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    grid = TileGrid()
    scroll.setWidget(grid)
    tiles = [
        Tile(
            str(i),
            f"Item {i}",
            "~/x",
            QPixmap(),
            i + 1,
            False,
            "",
            True,
            True,
            None,
            size,
        )
        for i in range(10)
    ]
    grid.set_tiles(tiles, tile_size(True, True, size))
    scroll.show()
    for width in (1300, 700, 420):
        resize(app, scroll, width)
        assert grid.columns == expected_columns(grid, scroll.viewport().width())
        right = max(t.geometry().right() for t in grid.tiles)
        assert right < scroll.viewport().width()


def test_row_puts_key_then_icon_then_name(app):
    tile = make_row(app, "Budget 2026.xlsx", star=True)
    key = label(tile, "keycap")
    name = label(tile, "tileName")
    icon = next(c for c in tile.findChildren(QLabel) if c.pixmap() and c.width() == 20)
    star = label(tile, "starMark")
    assert key.geometry().right() < icon.geometry().left()
    assert icon.geometry().right() < name.geometry().left()
    assert name.geometry().right() < star.geometry().left()
    assert star.geometry().right() < tile.width()


@pytest.mark.parametrize("size", [1, 2])
def test_long_names_fit_inside_a_row(app, size):
    for missing in (False, True):
        tile = make_row(
            app, "Quarterly planning workshop notes final v3.docx", size, missing
        )
        for name in ("tileName", "tileMeta"):
            text = label(tile, name)
            width = QFontMetrics(text.font()).horizontalAdvance(text.text())
            assert width <= text.width(), (size, missing, name)
            assert text.geometry().right() < tile.width()
