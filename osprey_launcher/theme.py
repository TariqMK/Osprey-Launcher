"""Defines the light and dark colour palettes and builds the app's Qt style sheet from them."""

from __future__ import annotations

PALETTES = {
    "dark": {
        "bg": "#141415",
        "deep": "#0f0f10",
        "card": "#19191b",
        "raised": "#232325",
        "t1": "#ededed",
        "t2": "#a1a1a6",
        "t3": "#85858b",
        "hl": "rgba(237, 237, 237, 20)",
        "hover": "rgba(237, 237, 237, 12)",
        "acc": "#5cbfb3",
        "acc_hover": "#6fcabf",
        "acc_ink": "#0b2b28",
        "danger": "#e5484d",
        "overlay": "rgba(20, 20, 21, 230)",
    },
    "light": {
        "bg": "#fafafa",
        "deep": "#f1f1f2",
        "card": "#ffffff",
        "raised": "#f4f4f5",
        "t1": "#171717",
        "t2": "#525252",
        "t3": "#737373",
        "hl": "rgba(23, 23, 23, 20)",
        "hover": "rgba(23, 23, 23, 10)",
        "acc": "#1f7a70",
        "acc_hover": "#1a6a61",
        "acc_ink": "#ffffff",
        "danger": "#dc2626",
        "overlay": "rgba(250, 250, 250, 235)",
    },
}


def stylesheet(p: dict, mono: str) -> str:
    return f"""
QWidget#root {{ background: {p["bg"]}; }}
QWidget {{ color: {p["t1"]}; font-size: 13px; }}
QToolTip {{ background: {p["card"]}; color: {p["t1"]}; border: 1px solid {p["hl"]}; padding: 4px 8px; }}

QWidget#header {{ background: {p["deep"]}; border-bottom: 1px solid {p["hl"]}; }}
QLabel#wordmark {{ font-size: 15px; font-weight: 600; }}

QPushButton#tab {{
  background: transparent; color: {p["t2"]}; border: none; border-radius: 8px;
  padding: 6px 12px; font-size: 13px;
}}
QPushButton#tab:hover {{ background: {p["hover"]}; color: {p["t1"]}; }}
QPushButton#tab:checked {{ background: {p["raised"]}; color: {p["t1"]}; border: 1px solid {p["hl"]}; }}
QPushButton#tab:focus {{ outline: none; }}
QPushButton#tab[dropTarget="true"] {{
  background: {p["hover"]}; color: {p["t1"]}; border: 1px solid {p["acc"]};
}}
QWidget#dropIndicator {{ background: {p["acc"]}; border-radius: 1px; }}

QPushButton#iconButton {{
  background: transparent; border: none; border-radius: 8px; padding: 6px;
}}
QPushButton#iconButton:hover {{ background: {p["hover"]}; }}

QLineEdit#search {{
  background: {p["raised"]}; border: 1px solid {p["hl"]}; border-radius: 8px;
  padding: 5px 8px; color: {p["t1"]}; selection-background-color: {p["acc"]};
  selection-color: {p["acc_ink"]};
}}
QLineEdit#search:focus {{ border: 1px solid {p["acc"]}; }}

QPushButton#primary {{
  background: {p["acc"]}; color: {p["acc_ink"]}; border: none; border-radius: 8px;
  padding: 6px 14px; font-weight: 500;
}}
QPushButton#primary:hover {{ background: {p["acc_hover"]}; }}
QPushButton#primary::menu-indicator {{ image: none; width: 0; }}

QPushButton#secondary {{
  background: {p["raised"]}; color: {p["t1"]}; border: 1px solid {p["hl"]}; border-radius: 6px;
  padding: 2px 10px; font-size: 12px;
}}
QPushButton#secondary:hover {{ background: {p["hover"]}; }}

QLabel#sectionTitle {{ font-size: 15px; font-weight: 500; }}
QLabel#count {{ color: {p["t3"]}; font-family: "{mono}"; font-size: 12px; }}

QFrame#tile {{ background: {p["card"]}; border: 1px solid {p["hl"]}; border-radius: 12px; }}
QFrame#tile:hover {{ background: {p["raised"]}; }}
QFrame#tile QLabel {{ background: transparent; border: none; }}
QLabel#tileName {{ font-size: 13px; font-weight: 500; }}
QLabel#tileMeta {{ color: {p["t3"]}; font-size: 12px; }}
QLabel#tileMeta[missing="true"] {{ color: {p["danger"]}; }}
QLabel#tileName[missing="true"] {{ color: {p["danger"]}; }}
QFrame#tile QLabel#missingDot {{ background: {p["danger"]}; border-radius: 4px; }}
QFrame#tile QLabel#keycap {{
  color: {p["t3"]}; border: 1px solid {p["hl"]}; border-bottom: 2px solid {p["hl"]};
  border-radius: 4px; padding: 0px 4px; font-family: "{mono}"; font-size: 11px;
}}

QLabel#emptyTitle {{ font-size: 15px; font-weight: 500; }}
QLabel#emptyBody {{ color: {p["t2"]}; }}

QPushButton#dataButton {{
  background: transparent; border: none; border-radius: 6px; padding: 4px 6px;
  color: {p["t3"]}; font-family: "{mono}"; font-size: 12px;
}}
QPushButton#dataButton:hover {{ background: {p["hover"]}; color: {p["t2"]}; }}
QWidget#footer {{ border-top: 1px solid {p["hl"]}; }}
QLabel#hint {{ color: {p["t3"]}; font-size: 12px; }}
QLabel#hint[mono="true"] {{ font-family: "{mono}"; }}

QWidget#dropOverlay {{
  background: {p["overlay"]}; border: 2px dashed {p["acc"]}; border-radius: 12px;
}}
QWidget#dropOverlay QLabel {{ background: transparent; border: none; }}
QLabel#dropTitle {{ font-size: 14px; font-weight: 500; }}
QLabel#dropBody {{ color: {p["t3"]}; font-size: 12px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {p["hl"]}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {p["t3"]}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
  background: none; height: 0;
}}

QMenu {{
  background: {p["card"]}; border: 1px solid {p["hl"]}; border-radius: 10px; padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; color: {p["t1"]}; }}
QMenu::item:selected {{ background: {p["raised"]}; }}
QMenu::item:disabled {{ color: {p["t3"]}; }}
QMenu::separator {{ height: 1px; background: {p["hl"]}; margin: 4px 8px; }}
"""
