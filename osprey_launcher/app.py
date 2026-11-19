"""Main window of Osprey Launcher: tabs of tiles you can open, add by drag and drop or a picker, and search."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDrag,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import __version__, launcher
from .backup import BackupError
from .backup import parse as parse_backup
from .icons import ICON_SIZE, IconCache, app_icon, line_icon
from .models import Item, normalise_url, resolve_target, url_domain
from .paths import app_location, default_data_dir, ensure_writable
from .store import DEFAULT_TILE_SIZE, TILE_SIZES, Store
from .theme import PALETTES, stylesheet

APP_NAME = "Osprey Launcher"
GAP, MARGIN = 12, 16
KIND_LABELS = {"app": "App", "file": "File", "folder": "Folder", "link": "Link"}
THEME_ORDER = ["system", "light", "dark"]
THEME_ICONS = {"system": "monitor", "light": "sun", "dark": "moon"}
ITEM_MIME = "application/x-osprey-item"
STARRED = "starred"  # ID of the Starred tab. It is built from the starred list, not stored as a tab.
AUTOSCROLL_EDGE, AUTOSCROLL_STEP = 32, 16


# Sizes 1 and 2 show each item as a row: key, icon, then name and location side by side.
# Sizes 3 to 5 show tiles with the icon on top. Size 3 is the original tile.
ROW_LAYOUT = {1: (20, 248), 2: (32, 288)}  # Icon size and row width, in px.
TILE_ICONS = {3: ICON_SIZE, 4: 56, 5: 72}
SIZE_NAMES = {
    1: "Small rows",
    2: "Rows",
    3: "Tiles",
    4: "Large tiles",
    5: "Extra large tiles",
}


def is_rows(size: int) -> bool:
    return size in ROW_LAYOUT


def icon_size(size: int) -> int:
    return ROW_LAYOUT[size][0] if is_rows(size) else TILE_ICONS[size]


def tile_size(show_name: bool, show_type: bool, size: int = DEFAULT_TILE_SIZE) -> QSize:
    """Tiles grow with the size setting and shrink when the name or type line is hidden.

    Rows always show the name, so only the detail line changes their height.
    """
    if is_rows(size):
        icon, width = ROW_LAYOUT[size]
        return QSize(width, icon + (24 if show_type else 16))
    extra = TILE_ICONS[size] - ICON_SIZE
    width = 176 + extra * 3 // 2
    if show_name and show_type:
        return QSize(width, 116 + extra)
    if show_name or show_type:
        return QSize(width, 96 + extra)
    return QSize(96 + extra, 96 + extra)


def short_location(path: str) -> str:
    """The folder an item is in, with the home folder written as ~."""
    parent = Path(path).parent
    try:
        return str(Path("~") / parent.relative_to(Path.home()))
    except ValueError:
        return str(parent)


if sys.platform == "darwin":
    REVEAL_LABEL = "Show in Finder"
elif sys.platform == "win32":
    REVEAL_LABEL = "Show in File Explorer"
else:
    REVEAL_LABEL = "Show in folder"


class Tile(QFrame):
    """One launchable item: icon, name, detail line and its 1-9 key, as a tile or a row."""

    activated = Signal(str)
    menu_requested = Signal(str, QPoint)
    locate_requested = Signal(str)
    drag_finished = Signal()

    def __init__(
        self,
        item_id,
        name,
        meta,
        pixmap,
        key,
        missing,
        tooltip,
        show_name=True,
        show_type=True,
        star=None,
        size=DEFAULT_TILE_SIZE,
    ):
        super().__init__()
        self.item_id = item_id
        self.missing = missing
        self._press: QPoint | None = None
        style_size = size
        size = tile_size(show_name, show_type, style_size)
        self.setObjectName("tile")
        self.setFixedSize(size)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)
        if missing:
            tooltip += "\nNot found. Click to locate."
        self.setToolTip(tooltip)

        icon = QLabel()
        icon.setFixedSize(icon_size(style_size), icon_size(style_size))
        icon.setPixmap(pixmap)
        if missing:
            icon.setEnabled(False)

        if is_rows(style_size):
            self._build_row(icon, name, meta, key, missing, show_type, star, size)
            return

        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        if not (show_name or show_type):
            # Icon only: the icon sits in the middle, the key in the top corner.
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(icon, 0, Qt.AlignCenter)
            if key:
                cap = QLabel(str(key), self, objectName="keycap")
                cap.ensurePolished()
                cap.adjustSize()
                cap.move(size.width() - 8 - cap.width(), 8)
            if star is not None:
                mark = QLabel(self, objectName="starMark")
                mark.setPixmap(star)
                mark.setToolTip("Starred")
                mark.move(8, 8)
            if missing:
                dot = QLabel(self, objectName="missingDot")
                dot.setFixedSize(8, 8)
                dot.move(size.width() - 16, size.height() - 16)
            return

        # Icon, name and type are centred. The key and star sit in the top-right corner,
        # placed directly so they do not push the icon off centre.
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(icon, 0, Qt.AlignHCenter | Qt.AlignTop)
        right = size.width() - 12
        cap_height = 0
        if key:
            cap = QLabel(str(key), self, objectName="keycap")
            cap.ensurePolished()
            cap.adjustSize()
            right -= cap.width()
            cap.move(right, 12)
            cap_height = cap.height()
        if star is not None:
            mark = QLabel(self, objectName="starMark")
            mark.setPixmap(star)
            mark.setToolTip("Starred")
            mark.adjustSize()
            if key:
                right -= 6
            mark.move(
                right - mark.width(), 12 + max(0, cap_height - mark.height()) // 2
            )
        layout.addStretch()

        if show_name:
            name_label = QLabel()
            name_label.setObjectName("tileName")
            name_label.setProperty("missing", missing and not show_type)
            name_label.setAlignment(Qt.AlignHCenter)
            name_label.ensurePolished()  # Measure with the style sheet's font, not the default.
            name_label.setText(
                QFontMetrics(name_label.font()).elidedText(
                    name, Qt.ElideMiddle, size.width() - 24
                )
            )
            layout.addWidget(name_label)
        if show_name and show_type:
            layout.addSpacing(2)
        if not show_type:
            return

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        meta_label = QLabel()
        meta_label.setObjectName("tileMeta")
        meta_label.setProperty("missing", missing)
        meta_label.setText("Not found" if missing else meta)
        meta_row.addStretch()
        meta_row.addWidget(meta_label)
        if missing:
            locate = QPushButton("Locate")
            locate.setObjectName("secondary")
            locate.setCursor(Qt.PointingHandCursor)
            locate.clicked.connect(lambda: self.locate_requested.emit(self.item_id))
            meta_row.addWidget(locate)
        meta_row.addStretch()
        layout.addLayout(meta_row)

    def _build_row(self, icon, name, meta, key, missing, show_type, star, size):
        """Row layout: the key comes first, then the icon, the name and the location."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8 if missing else 12, 0)
        layout.setSpacing(10)

        cap = QLabel(str(key) if key else "", objectName="keycap")
        cap.setAlignment(Qt.AlignCenter)
        cap.setFixedSize(22, 20)
        if not key:
            cap.setStyleSheet(
                "border: none;"
            )  # Keeps the column, so names still line up.
        layout.addWidget(cap)
        layout.addWidget(icon)

        locate = None
        if missing:
            locate = QPushButton("Locate", objectName="secondary")
            locate.setCursor(Qt.PointingHandCursor)
            locate.clicked.connect(lambda: self.locate_requested.emit(self.item_id))
            locate.ensurePolished()
        mark = None
        if star is not None:
            mark = QLabel(objectName="starMark")
            mark.setPixmap(star)
            mark.setToolTip("Starred")

        # Measure inside the tile's border, which the style sheet draws and Qt subtracts.
        self.ensurePolished()
        margins = layout.contentsMargins()
        text_width = self.contentsRect().width() - margins.left() - margins.right()
        text_width -= cap.width() + icon.width() + 2 * layout.spacing()
        if mark is not None:
            text_width -= star.deviceIndependentSize().width() + layout.spacing()
        if locate is not None:
            text_width -= locate.sizeHint().width() + layout.spacing()

        text = QVBoxLayout()
        text.setSpacing(2)
        text.setContentsMargins(0, 0, 0, 0)
        text.addStretch()  # The stretches above and below centre the lines in the row.
        name_label = QLabel(objectName="tileName")
        name_label.setProperty("missing", missing and not show_type)
        name_label.ensurePolished()
        name_label.setText(
            QFontMetrics(name_label.font()).elidedText(
                name, Qt.ElideMiddle, int(text_width)
            )
        )
        text.addWidget(name_label)
        if show_type:
            meta_label = QLabel(objectName="tileMeta")
            meta_label.setProperty("missing", missing)
            meta_label.setProperty("mono", not missing)
            meta_label.ensurePolished()
            meta_label.setText(
                "Not found"
                if missing
                else QFontMetrics(meta_label.font()).elidedText(
                    meta, Qt.ElideMiddle, int(text_width)
                )
            )
            text.addWidget(meta_label)
        text.addStretch()
        layout.addLayout(text, 1)
        if mark is not None:
            layout.addWidget(mark)
        if locate is not None:
            layout.addWidget(locate)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is None or not event.buttons() & Qt.LeftButton:
            return
        moved = (event.position().toPoint() - self._press).manhattanLength()
        if moved >= QApplication.startDragDistance():
            self._start_drag(self._press)

    def mouseReleaseEvent(self, event):
        clicked = self._press is not None
        self._press = None
        inside = self.rect().contains(event.position().toPoint())
        if clicked and event.button() == Qt.LeftButton and inside:
            if self.missing:
                self.locate_requested.emit(self.item_id)
            else:
                self.activated.emit(self.item_id)
        super().mouseReleaseEvent(event)

    def _start_drag(self, hotspot: QPoint) -> None:
        """Drag this tile to a new place in the grid or onto a tab."""
        self._press = None
        mime = QMimeData()
        mime.setData(ITEM_MIME, self.item_id.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(hotspot)
        # Leave a faded copy where the tile came from while it is dragged.
        fade = QGraphicsOpacityEffect(self)
        fade.setOpacity(0.3)
        self.setGraphicsEffect(fade)
        drag.exec(Qt.MoveAction)
        self.setGraphicsEffect(None)
        self.drag_finished.emit()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self.item_id, event.globalPos())


class TileGrid(QWidget):
    """Lays tiles out in as many columns as fit the window width."""

    def __init__(self):
        super().__init__()
        self.tiles: list[Tile] = []
        self.columns = 0
        self.tile_w, self.tile_h = tile_size(True, True).toTuple()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(MARGIN, 8, MARGIN, 20)
        self.grid.setSpacing(GAP)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        # The layout's minimum width is its current column count. Ignore it, so the scroll
        # area can make the grid narrower when the window shrinks and the columns reflow.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.indicator = QWidget(self, objectName="dropIndicator")
        self.indicator.setAttribute(Qt.WA_StyledBackground)
        self.indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.indicator.hide()

    def insertion_index(self, pos: QPoint) -> int:
        """Return where a tile dropped at this point goes: 0 is before the first tile."""
        count = len(self.tiles)
        columns = self.columns or 1
        top = self.grid.contentsMargins().top()
        row = max(0, (pos.y() - top) // (self.tile_h + GAP))
        column = (pos.x() - MARGIN + (self.tile_w + GAP) // 2) // (self.tile_w + GAP)
        column = min(max(column, 0), columns)
        return min(row * columns + column, count)

    def show_indicator(self, index: int) -> None:
        """Draw a thin accent line in the gap where the tile will land."""
        columns = self.columns or 1
        row, column = divmod(index, columns)
        if column == 0 and index == len(self.tiles) and index > 0:
            row, column = row - 1, columns  # After the last tile of a full row.
        top = self.grid.contentsMargins().top()
        x = MARGIN + column * (self.tile_w + GAP) - GAP // 2 - 1
        y = top + row * (self.tile_h + GAP)
        self.indicator.setGeometry(x, y, 2, self.tile_h)
        self.indicator.raise_()
        self.indicator.show()

    def set_tiles(self, tiles: list[Tile], size: QSize) -> None:
        for tile in self.tiles:
            tile.setParent(None)
            tile.deleteLater()
        self.tiles = tiles
        self.tile_w, self.tile_h = size.toTuple()
        self.columns = 0
        self._relayout()

    def _relayout(self) -> None:
        columns = max(1, (self.width() - 2 * MARGIN + GAP) // (self.tile_w + GAP))
        if columns == self.columns:
            return
        self.columns = columns
        for tile in self.tiles:
            self.grid.removeWidget(tile)
        for index, tile in enumerate(self.tiles):
            self.grid.addWidget(tile, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()


class MainWindow(QMainWindow):
    def __init__(self, store: Store, icons: IconCache):
        super().__init__()
        self.store = store
        self.icons = icons
        self.current_tab_id = store.tabs[0].id
        self.visible_ids: list[str] = []
        self.mono = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()

        self.setWindowTitle(APP_NAME)
        self.resize(880, 600)
        self.setMinimumSize(520, 400)
        self.setAcceptDrops(True)

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        column = QVBoxLayout(root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        self.body = QWidget()
        column.addWidget(self.body, 1)
        self._build_body()
        column.addWidget(self._build_footer())

        icons.site_icon_ready.connect(lambda _domain: self.refresh())
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            lambda _s: self.apply_theme()
        )

        QShortcut(QKeySequence("Ctrl+K"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._clear_search)
        for keys, step in (("Ctrl+=", 1), ("Ctrl++", 1), ("Ctrl+-", -1)):
            QShortcut(QKeySequence(keys), self, lambda step=step: self.step_size(step))
        for n in range(1, 10):
            QShortcut(QKeySequence(str(n)), self, lambda n=n: self.open_nth(n))

        self.apply_theme()

    # Layout

    def _build_header(self) -> QWidget:
        header = QWidget(objectName="header")
        header.setAttribute(Qt.WA_StyledBackground)
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(8)

        wordmark = QLabel("Osprey", objectName="wordmark")
        row.addWidget(wordmark)
        version = QLabel(f"v{__version__}", objectName="version")
        version.setToolTip(f"{APP_NAME} version {__version__}")
        row.addWidget(version, 0, Qt.AlignBaseline)
        row.addSpacing(8)

        self.tab_row = QHBoxLayout()
        self.tab_row.setSpacing(4)
        row.addLayout(self.tab_row)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)

        self.add_tab_button = QPushButton(objectName="iconButton")
        self.add_tab_button.setToolTip("New tab")
        self.add_tab_button.setCursor(Qt.PointingHandCursor)
        self.add_tab_button.clicked.connect(self.new_tab)
        row.addWidget(self.add_tab_button)
        row.addStretch()

        self.search = QLineEdit(objectName="search")
        self.search.setPlaceholderText("Search")
        self.search.setFixedWidth(180)
        self.search.setClearButtonEnabled(True)
        self.search.setAcceptDrops(False)
        self.search_action = QAction(self.search)
        self.search.addAction(self.search_action, QLineEdit.LeadingPosition)
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.search.returnPressed.connect(lambda: self.open_nth(1))
        row.addWidget(self.search)

        self.add_button = QPushButton(" Add", objectName="primary")
        self.add_button.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.add_button)
        menu.addAction("Files or apps…", self.pick_files)
        menu.addAction("Folder…", self.pick_folder)
        menu.addAction("Link…", self.enter_link)
        self.add_button.setMenu(menu)
        row.addWidget(self.add_button)
        return header

    def _build_body(self) -> None:
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(MARGIN, 20, MARGIN, 8)
        title_row.setSpacing(8)
        self.section_title = QLabel(objectName="sectionTitle")
        self.count_label = QLabel(objectName="count")
        title_row.addWidget(self.section_title, 0, Qt.AlignBaseline)
        title_row.addWidget(self.count_label, 0, Qt.AlignBaseline)
        title_row.addStretch()
        layout.addLayout(title_row)

        self.stack = QStackedWidget()
        self.grid = TileGrid()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.grid)
        self.stack.addWidget(self.scroll)

        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(8)
        self.empty_title = QLabel(objectName="emptyTitle", alignment=Qt.AlignCenter)
        self.empty_body = QLabel(objectName="emptyBody", alignment=Qt.AlignCenter)
        self.empty_body.setWordWrap(True)
        self.empty_body.setMaximumWidth(360)
        empty_layout.addWidget(self.empty_title, 0, Qt.AlignCenter)
        empty_layout.addWidget(self.empty_body, 0, Qt.AlignCenter)
        empty_layout.addSpacing(32)
        self.stack.addWidget(empty)
        layout.addWidget(self.stack, 1)

        self.overlay = QWidget(self.body, objectName="dropOverlay")
        self.overlay.setAttribute(Qt.WA_StyledBackground)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)
        overlay_layout.setSpacing(8)
        self.drop_icon = QLabel(alignment=Qt.AlignCenter)
        self.drop_title = QLabel(objectName="dropTitle", alignment=Qt.AlignCenter)
        drop_body = QLabel(
            "Files, folders, shortcuts and links",
            objectName="dropBody",
            alignment=Qt.AlignCenter,
        )
        for widget in (self.drop_icon, self.drop_title, drop_body):
            overlay_layout.addWidget(widget, 0, Qt.AlignCenter)
        self.overlay.hide()

    def _build_footer(self) -> QWidget:
        footer = QWidget(objectName="footer")
        footer.setAttribute(Qt.WA_StyledBackground)
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 6, 10, 6)
        row.setSpacing(12)
        search_key = QKeySequence("Ctrl+K").toString(QKeySequence.NativeText)
        row.addWidget(
            QLabel(f"Press 1–9 to open, {search_key} to search", objectName="hint")
        )
        row.addStretch()
        self.data_button = QPushButton(
            "Stored next to the app", objectName="dataButton"
        )
        self.data_button.setCursor(Qt.PointingHandCursor)
        self.data_button.setToolTip(str(self.store.data_dir))
        self.data_button.clicked.connect(self.data_menu)
        row.addWidget(self.data_button)
        self.view_button = QPushButton(objectName="iconButton")
        self.view_button.setCursor(Qt.PointingHandCursor)
        self.view_button.setToolTip("Layout and size")
        self.view_button.clicked.connect(self.view_menu)
        row.addWidget(self.view_button)
        self.theme_button = QPushButton(objectName="iconButton")
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.clicked.connect(self.cycle_theme)
        row.addWidget(self.theme_button)
        return footer

    # Theme

    def effective_scheme(self) -> str:
        if self.store.theme != "system":
            return self.store.theme
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return "dark" if dark else "light"

    def apply_theme(self) -> None:
        self.palette_values = p = PALETTES[self.effective_scheme()]
        app = QApplication.instance()
        palette = QPalette()
        for role, key in (
            (QPalette.Window, "bg"),
            (QPalette.Base, "card"),
            (QPalette.AlternateBase, "raised"),
            (QPalette.Button, "raised"),
            (QPalette.WindowText, "t1"),
            (QPalette.Text, "t1"),
            (QPalette.ButtonText, "t1"),
            (QPalette.ToolTipBase, "card"),
            (QPalette.ToolTipText, "t1"),
            (QPalette.PlaceholderText, "t3"),
            (QPalette.Highlight, "acc"),
            (QPalette.HighlightedText, "acc_ink"),
        ):
            palette.setColor(role, QColor(p[key]))
        app.setPalette(palette)
        app.setStyleSheet(stylesheet(p, self.mono))

        self.add_tab_button.setIcon(line_icon("plus", p["t2"]))
        self.add_button.setIcon(line_icon("plus", p["acc_ink"]))
        self.search_action.setIcon(line_icon("search", p["t3"]))
        self.drop_icon.setPixmap(line_icon("download", p["acc"], 24).pixmap(24, 24))
        self._update_view_icon()
        self.theme_button.setIcon(line_icon(THEME_ICONS[self.store.theme], p["t3"]))
        self.theme_button.setIconSize(QSize(16, 16))
        self.theme_button.setToolTip(f"Theme: {self.store.theme.capitalize()}")
        self.rebuild_tabs()

    def _update_view_icon(self) -> None:
        name = "list" if is_rows(self.store.tile_size) else "layout-grid"
        self.view_button.setIcon(line_icon(name, self.palette_values["t3"]))
        self.view_button.setIconSize(QSize(16, 16))

    def view_menu(self) -> None:
        """Choose rows or tiles and their size with one slider, and hide the label lines."""
        menu = QMenu(self)

        panel = QWidget(objectName="sizePanel")
        column = QVBoxLayout(panel)
        column.setContentsMargins(12, 8, 12, 8)
        column.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(QLabel("Size", objectName="menuLabel"))
        top.addStretch()
        value = QLabel(SIZE_NAMES[self.store.tile_size], objectName="menuValue")
        top.addWidget(value)
        column.addLayout(top)
        slider = QSlider(Qt.Horizontal, objectName="sizeSlider")
        slider.setRange(TILE_SIZES[0], TILE_SIZES[-1])
        slider.setPageStep(1)
        slider.setFixedWidth(208)
        slider.setValue(self.store.tile_size)
        slider.setCursor(Qt.PointingHandCursor)
        slider.setAccessibleName("Size")
        column.addWidget(slider)
        ends = QHBoxLayout()
        ends.addWidget(QLabel("Rows", objectName="menuHint"))
        ends.addStretch()
        ends.addWidget(QLabel("Large tiles", objectName="menuHint"))
        column.addLayout(ends)
        slider_action = QWidgetAction(menu)
        slider_action.setDefaultWidget(panel)
        menu.addAction(slider_action)
        menu.addSeparator()

        names = menu.addAction("Show names")
        names.setCheckable(True)
        names.setChecked(self.store.show_names)
        names.toggled.connect(lambda on: self.set_display(names=on))
        details = menu.addAction("Show details")
        details.setCheckable(True)
        details.setChecked(self.store.show_types)
        details.toggled.connect(lambda on: self.set_display(types=on))

        def size_changed(size: int) -> None:
            value.setText(SIZE_NAMES[size])
            names.setEnabled(not is_rows(size))  # Rows always show the name.
            self.set_display(size=size)

        names.setEnabled(not is_rows(self.store.tile_size))
        slider.valueChanged.connect(size_changed)
        self._menu_above(menu, self.view_button)

    def step_size(self, step: int) -> None:
        self.set_display(size=self.store.tile_size + step)

    def _menu_above(self, menu: QMenu, button: QPushButton) -> None:
        top_left = button.rect().topLeft()
        menu.exec(
            button.mapToGlobal(top_left - QPoint(0, menu.sizeHint().height() + 4))
        )

    def data_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(
            "Open data folder",
            lambda: launcher.open_target(str(self.store.data_dir), is_link=False),
        )
        menu.addAction("Restore from backup…", self.restore_backup)
        self._menu_above(menu, self.data_button)

    def restore_backup(self) -> None:
        """Replace all tabs and items with the contents of a YAML backup file, after a confirmation."""
        path, _f = QFileDialog.getOpenFileName(
            self,
            "Restore from backup",
            str(self.store.backup_path),
            "Osprey Launcher backup (*.yaml *.yml)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            tabs, starred, skipped = parse_backup(text, self.store.base_dir)
        except (OSError, UnicodeDecodeError, BackupError) as error:
            message = (
                str(error)
                if isinstance(error, BackupError)
                else "The file can't be read."
            )
            QMessageBox.warning(
                self, "Restore from backup", f"{message}\n\nNothing was changed."
            )
            return

        count = sum(len(t.items) for t in tabs)
        box = QMessageBox(self)
        box.setWindowTitle("Restore from backup")
        box.setText("Replace all tabs and items with this backup?")
        box.setInformativeText(
            f"The backup has {len(tabs)} tab{'s' if len(tabs) != 1 else ''} and "
            f"{count} item{'s' if count != 1 else ''}. Your current tabs and items are replaced. "
            "Your files, folders and apps are not changed."
        )
        restore = box.addButton("Restore", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is not restore:
            return

        self.store.restore(tabs, starred)
        self.current_tab_id = tabs[0].id
        if self.search.text():
            self.search.clear()
        for tab in tabs:
            for item in tab.items:
                if item.kind == "link" and not self.icons.has_site_icon(
                    url_domain(item.target)
                ):
                    self.icons.fetch_site_icon(url_domain(item.target))
        self.rebuild_tabs()
        if skipped:
            QMessageBox.information(
                self,
                "Restore from backup",
                f"{skipped} item{'s' if skipped != 1 else ''} in the backup had no path or link "
                "and were not restored.",
            )

    def set_display(self, **kwargs) -> None:
        self.store.set_display(**kwargs)
        self._update_view_icon()
        self.refresh()

    def cycle_theme(self) -> None:
        index = THEME_ORDER.index(self.store.theme)
        self.store.set_theme(THEME_ORDER[(index + 1) % len(THEME_ORDER)])
        self.apply_theme()

    # Tabs

    def rebuild_tabs(self) -> None:
        for button in self.tab_group.buttons():
            self.tab_group.removeButton(button)
            button.setParent(None)
            button.deleteLater()
        if self.current_tab_id not in self._tab_ids():
            self.current_tab_id = self.store.tabs[0].id
        if self.store.starred:
            # The Starred tab exists only while at least one item is starred.
            button = QPushButton("Starred", objectName="tab")
            button.setIcon(
                line_icon(
                    "star",
                    self.palette_values["acc"],
                    14,
                    fill=self.palette_values["acc"],
                )
            )
            button.setCheckable(True)
            button.setChecked(self.current_tab_id == STARRED)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _c=False: self.select_tab(STARRED))
            button.setProperty("tab_id", STARRED)
            self.tab_group.addButton(button)
            self.tab_row.addWidget(button)
        for tab in self.store.tabs:
            button = QPushButton(tab.name, objectName="tab")
            button.setCheckable(True)
            button.setChecked(tab.id == self.current_tab_id)
            button.setCursor(Qt.PointingHandCursor)
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.clicked.connect(lambda _c=False, tid=tab.id: self.select_tab(tid))
            button.customContextMenuRequested.connect(
                lambda pos, tid=tab.id, b=button: self.tab_menu(tid, b.mapToGlobal(pos))
            )
            button.setProperty("tab_id", tab.id)
            self.tab_group.addButton(button)
            self.tab_row.addWidget(button)
        self.refresh()

    def _tab_ids(self) -> set[str]:
        ids = {t.id for t in self.store.tabs}
        if self.store.starred:
            ids.add(STARRED)
        return ids

    def _tab_name(self, tab_id: str) -> str:
        return "Starred" if tab_id == STARRED else self.store.tab(tab_id).name

    def select_tab(self, tab_id: str) -> None:
        self.current_tab_id = tab_id
        for button in self.tab_group.buttons():
            button.setChecked(button.property("tab_id") == tab_id)
        if self.search.text():
            self.search.clear()
        self.refresh()

    def new_tab(self) -> None:
        name, ok = QInputDialog.getText(self, "New tab", "Name")
        if ok and name.strip():
            self.current_tab_id = self.store.add_tab(name).id
            self.rebuild_tabs()

    def tab_menu(self, tab_id: str, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_tab(tab_id))
        if len(self.store.tabs) > 1:
            menu.addAction("Delete tab…", lambda: self.delete_tab(tab_id))
        menu.exec(pos)

    def rename_tab(self, tab_id: str) -> None:
        tab = self.store.tab(tab_id)
        name, ok = QInputDialog.getText(self, "Rename tab", "Name", text=tab.name)
        if ok:
            self.store.rename_tab(tab_id, name)
            self.rebuild_tabs()

    def delete_tab(self, tab_id: str) -> None:
        tab = self.store.tab(tab_id)
        count = len(tab.items)
        box = QMessageBox(self)
        box.setWindowTitle("Delete tab")
        box.setText(f"Delete the “{tab.name}” tab?")
        box.setInformativeText(
            f"Its {count} item{'s' if count != 1 else ''} will be removed from the launcher. "
            "Your files, folders and apps are not changed."
        )
        delete = box.addButton("Delete", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is delete:
            self.store.remove_tab(tab_id)
            self.rebuild_tabs()

    # Tiles

    def _pixmap(self, item: Item):
        scale = self.devicePixelRatioF()
        size = icon_size(self.store.tile_size)
        p = self.palette_values
        if item.kind == "link":
            return self.icons.pixmap_for_link(
                url_domain(item.target), p["raised"], p["t2"], scale, size
            )
        return self.icons.pixmap_for_path(
            resolve_target(item, self.store.base_dir), scale, size
        )

    def refresh(self) -> None:
        if not hasattr(self, "grid"):
            return
        query = self.search.text().strip()
        starred_view = not query and self.current_tab_id == STARRED
        if query:
            entries = self.store.search(query)
            self.section_title.setText("Results")
        elif starred_view:
            entries = self.store.starred_items()
            self.section_title.setText("Starred")
        else:
            tab = self.store.tab(self.current_tab_id)
            entries = [(tab, item) for item in tab.items]
            self.section_title.setText(tab.name)
        count = len(entries)
        self.count_label.setText(f"{count} item{'s' if count != 1 else ''}")
        self.visible_ids = [item.id for _tab, item in entries]

        acc = self.palette_values["acc"]
        star = line_icon("star", acc, 12, fill=acc).pixmap(12, 12)
        size = self.store.tile_size
        tiles = []
        for index, (tab, item) in enumerate(entries):
            missing = not self.store.target_exists(item)
            full = resolve_target(item, self.store.base_dir)
            if is_rows(size):
                # Rows have room for where the item is, not only what it is.
                meta = full if item.kind == "link" else short_location(full)
            else:
                meta = KIND_LABELS[item.kind]
                if item.kind == "link" and item.label != url_domain(item.target):
                    meta = url_domain(item.target)
            if query or starred_view:
                meta = f"{tab.name} · {meta}"
            tile = Tile(
                item.id,
                item.label,
                meta,
                self._pixmap(item),
                index + 1 if index < 9 else None,
                missing,
                f"{item.label}\n{full}",
                self.store.show_names,
                self.store.show_types,
                star if self.store.is_starred(item.id) else None,
                size,
            )
            tile.activated.connect(self.open_item)
            tile.menu_requested.connect(self.item_menu)
            tile.locate_requested.connect(self.locate_item)
            tile.drag_finished.connect(self._end_drag)
            tiles.append(tile)
        self.grid.set_tiles(
            tiles, tile_size(self.store.show_names, self.store.show_types, size)
        )

        if tiles:
            self.stack.setCurrentIndex(0)
        elif query:
            self.empty_title.setText("No matches")
            self.empty_body.setText(f"Nothing in any tab matches “{query}”.")
            self.stack.setCurrentIndex(1)
        else:
            self.empty_title.setText(f"Add items to {self.section_title.text()}")
            self.empty_body.setText(
                "Drag files, folders, apps, shortcuts or links into this window, or select Add."
            )
            self.stack.setCurrentIndex(1)

    def open_item(self, item_id: str) -> None:
        _tab, item = self.store.find(item_id)
        if not self.store.target_exists(item):
            self.refresh()
            return
        launcher.open_target(
            resolve_target(item, self.store.base_dir), item.kind == "link"
        )

    def open_nth(self, n: int) -> None:
        if len(self.visible_ids) >= n:
            self.open_item(self.visible_ids[n - 1])

    def item_menu(self, item_id: str, pos: QPoint) -> None:
        current_tab, item = self.store.find(item_id)
        full = resolve_target(item, self.store.base_dir)
        exists = self.store.target_exists(item)
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.open_item(item_id)).setEnabled(exists)
        starred = self.store.is_starred(item_id)
        menu.addAction(
            "Remove from Starred" if starred else "Add to Starred",
            lambda: self.set_starred(item_id, not starred),
        )
        if item.kind == "link":
            menu.addAction(
                "Copy link", lambda: QGuiApplication.clipboard().setText(full)
            )
            domain = url_domain(item.target)
            if not self.icons.has_site_icon(domain):
                menu.addAction(
                    "Download site icon", lambda: self.icons.fetch_site_icon(domain)
                )
        else:
            menu.addAction(REVEAL_LABEL, lambda: launcher.reveal(full)).setEnabled(
                exists
            )
            menu.addAction(
                "Copy path", lambda: QGuiApplication.clipboard().setText(full)
            )
            menu.addAction("Locate…", lambda: self.locate_item(item_id))
        menu.addSeparator()
        menu.addAction("Rename…", lambda: self.rename_item(item_id))
        if item.custom_name:
            menu.addAction(
                f"Reset name to “{item.name}”", lambda: self._reset_name(item_id)
            )
        if len(self.store.tabs) > 1:
            move = menu.addMenu("Move to")
            for tab in self.store.tabs:
                if tab.id != current_tab.id:
                    move.addAction(
                        tab.name, lambda tid=tab.id: self._move(item_id, tid)
                    )
        menu.addSeparator()
        menu.addAction("Remove from launcher", lambda: self._remove(item_id))
        menu.exec(pos)

    def set_starred(self, item_id: str, on: bool) -> None:
        self.store.set_starred(item_id, on)
        self.rebuild_tabs()  # The Starred tab shows or hides with the first or last star.

    def _move(self, item_id: str, tab_id: str) -> None:
        self.store.move_item(item_id, tab_id)
        self.refresh()

    def _remove(self, item_id: str) -> None:
        self.store.remove_item(item_id)
        self.rebuild_tabs()

    def rename_item(self, item_id: str) -> None:
        item = self.store.find(item_id)[1]
        name, ok = QInputDialog.getText(
            self, "Rename", f"Name (original: {item.name})", text=item.label
        )
        if ok:
            self.store.rename_item(item_id, name)
            self.refresh()

    def _reset_name(self, item_id: str) -> None:
        self.store.rename_item(item_id, "")
        self.refresh()

    def locate_item(self, item_id: str) -> None:
        item = self.store.find(item_id)[1]
        start = str(Path(resolve_target(item, self.store.base_dir)).parent)
        if item.kind == "folder":
            path = QFileDialog.getExistingDirectory(self, f"Locate {item.label}", start)
        else:
            path = QFileDialog.getOpenFileName(self, f"Locate {item.label}", start)[0]
        if path:
            self.store.relocate_item(item_id, path)
            self.refresh()

    # Adding

    def add_targets(self, targets: list[str], tab_id: str | None = None) -> None:
        if not targets:
            return
        if self.search.text():
            self.search.clear()
        tab_id = tab_id or self.current_tab_id
        to_starred = tab_id == STARRED
        if to_starred:
            # Starred is a view, so new items live in the first tab and get a star.
            tab_id = self.store.tabs[0].id
        added = self.store.add_targets(tab_id, targets)
        for item in added:
            if to_starred:
                self.store.set_starred(item.id, True)
            if item.kind == "link":
                self.icons.fetch_site_icon(url_domain(item.target))
        self.rebuild_tabs()

    def pick_files(self) -> None:
        paths, _f = QFileDialog.getOpenFileNames(self, "Add files or apps")
        self.add_targets(paths)

    def pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add folder")
        self.add_targets([path] if path else [])

    def enter_link(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Add link", "Web address", text="https://"
        )
        if not ok:
            return
        url = normalise_url(text)
        if url:
            self.add_targets([url])
        else:
            QMessageBox.information(
                self,
                "Add link",
                "Enter a web address, for example https://example.com.",
            )

    # Drag and drop

    def _drop_targets(self, mime) -> list[str]:
        targets = []
        for url in mime.urls():
            if url.isLocalFile():
                targets.append(url.toLocalFile().rstrip("/") or "/")
            elif url.scheme() in ("http", "https"):
                targets.append(url.toString())
        if not targets and mime.hasText():
            url = normalise_url(mime.text())
            if url:
                targets.append(url)
        return targets

    @staticmethod
    def _dragged_item(mime) -> str | None:
        """Return the item ID when a tile from this window is being dragged."""
        if mime.hasFormat(ITEM_MIME):
            return bytes(mime.data(ITEM_MIME).data()).decode()
        return None

    def _tab_at(self, pos: QPoint) -> str | None:
        for button in self.tab_group.buttons():
            if button.rect().contains(button.mapFrom(self, pos)):
                return button.property("tab_id")
        return None

    def _grid_index_at(self, pos: QPoint) -> int | None:
        """Return the insertion point under the cursor, or None if tiles can't be placed there."""
        if self.search.text().strip() or self.stack.currentIndex() != 0:
            return None
        viewport = self.scroll.viewport()
        if not viewport.rect().contains(viewport.mapFrom(self, pos)):
            return None
        return self.grid.insertion_index(self.grid.mapFrom(self, pos))

    def _highlight_tab(self, tab_id: str | None) -> None:
        for button in self.tab_group.buttons():
            on = tab_id is not None and button.property("tab_id") == tab_id
            if bool(button.property("dropTarget")) != on:
                button.setProperty("dropTarget", on)
                button.style().unpolish(button)
                button.style().polish(button)

    def _autoscroll(self, pos: QPoint) -> None:
        viewport = self.scroll.viewport()
        y = viewport.mapFrom(self, pos).y()
        bar = self.scroll.verticalScrollBar()
        if 0 <= y < AUTOSCROLL_EDGE:
            bar.setValue(bar.value() - AUTOSCROLL_STEP)
        elif viewport.height() - AUTOSCROLL_EDGE < y <= viewport.height():
            bar.setValue(bar.value() + AUTOSCROLL_STEP)

    def _clear_drop_marks(self) -> None:
        self.overlay.hide()
        self.grid.indicator.hide()
        self._highlight_tab(None)

    def _end_drag(self) -> None:
        """Called by the dragged tile once its drag is over, dropped or cancelled."""
        self._clear_drop_marks()
        self.rebuild_tabs()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if self._dragged_item(mime):
            self.dragMoveEvent(event)
        elif self._drop_targets(mime):
            self.overlay.setGeometry(self.body.rect().adjusted(MARGIN, 8, -MARGIN, -12))
            self.overlay.raise_()
            self.overlay.show()
            self.dragMoveEvent(event)
        else:
            event.ignore()
            return
        # Accept the enter even if the first spot is not a drop target, so move events keep coming.
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        pos = event.position().toPoint()
        tab_id = self._tab_at(pos)
        item_id = self._dragged_item(event.mimeData())
        self._autoscroll(pos)

        if item_id is None:
            # Files or links from outside: add to the tab under the cursor, or the open tab.
            self._highlight_tab(tab_id)
            name = self._tab_name(tab_id or self.current_tab_id)
            self.drop_title.setText(f"Drop to add to {name}")
            event.acceptProposedAction()
            return

        if tab_id == STARRED:
            tab_ok = not self.store.is_starred(item_id)
        else:
            tab_ok = tab_id is not None and tab_id != self.store.find(item_id)[0].id
        index = None if tab_id else self._grid_index_at(pos)
        if tab_ok:
            self._highlight_tab(tab_id)
            self.grid.indicator.hide()
            event.acceptProposedAction()
        elif index is not None:
            self._highlight_tab(None)
            self.grid.show_indicator(index)
            event.acceptProposedAction()
        else:
            self._clear_drop_marks()
            event.ignore()

    def dragLeaveEvent(self, event):
        self._clear_drop_marks()

    def dropEvent(self, event):
        pos = event.position().toPoint()
        tab_id = self._tab_at(pos)
        item_id = self._dragged_item(event.mimeData())
        self._clear_drop_marks()

        if item_id is None:
            targets = self._drop_targets(event.mimeData())
            if targets:
                event.acceptProposedAction()
                self.add_targets(targets, tab_id)
            return

        # The tile refreshes the grid itself when its drag ends (see _end_drag),
        # because the grid can't delete a tile while that tile is still running its drag.
        if tab_id == STARRED:
            self.store.set_starred(item_id, True)
        elif tab_id:
            self.store.move_item(item_id, tab_id)
        else:
            index = self._grid_index_at(pos)
            if index is None:
                pass
            elif self.current_tab_id == STARRED:
                self.store.move_starred(item_id, index)
            else:
                self.store.move_item(item_id, self.current_tab_id, index)
        event.acceptProposedAction()

    # Search

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _clear_search(self) -> None:
        if self.search.text():
            self.search.clear()
        self.search.clearFocus()


def choose_data_dir(default: Path) -> Path | None:
    """Use the folder next to the app. If it can't be written, ask the user where to save instead."""
    if ensure_writable(default):
        return default
    QMessageBox.warning(
        None,
        APP_NAME,
        f"Osprey Launcher can't save its data next to the app:\n{default}\n\n"
        "Choose another folder for your launcher data. To keep the app portable, "
        "move the app to a folder you can write to.",
    )
    chosen = QFileDialog.getExistingDirectory(None, "Choose a folder for launcher data")
    if chosen and ensure_writable(Path(chosen)):
        return Path(chosen)
    return None


def self_check() -> int:
    """Check a packaged build has everything it needs. Opens no window and writes no data.

    The release workflow runs the built app with --self-check and stops if this fails.
    """
    from PySide6.QtGui import QImageReader
    from PySide6.QtNetwork import QNetworkAccessManager

    from .backup import dump
    from .models import Item, Tab

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication([sys.argv[0]])
    formats = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
    sample = [
        Tab("t", "Tab", [Item("i", "link", "example.com", "https://example.com")])
    ]
    checks = {
        "app icon (SVG renderer)": not app_icon().isNull(),
        "line icons": not line_icon("star", "#000000").isNull(),
        "site icon formats (png, ico)": {"png", "ico"} <= formats,
        "YAML backup": parse_backup(dump(sample, ["i"], Path.cwd()), Path.cwd())[1]
        != [],
        "network": QNetworkAccessManager(app) is not None,
        "style sheet": bool(stylesheet(PALETTES["dark"], "monospace")),
    }
    ok = all(checks.values())
    if sys.stdout:  # Windowed Windows builds have no console.
        print(f"{APP_NAME} v{__version__}")
        for name, passed in checks.items():
            print(f"{'ok  ' if passed else 'FAIL'} {name}")
    return 0 if ok else 1


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    data_dir = choose_data_dir(default_data_dir())
    if data_dir is None:
        return 1
    store = Store(data_dir, app_location())
    icons = IconCache(data_dir)
    window = MainWindow(store, icons)
    window.show()
    if store.restored_from_backup:
        QMessageBox.information(
            window,
            APP_NAME,
            "The launcher data file could not be read. Your tabs and items were "
            f"restored from {store.backup_path.name}.",
        )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
