"""Opens items with the system's default handler and shows files in the system file manager."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_target(target: str, is_link: bool) -> bool:
    """Open a URL in the browser, or a file, folder or app with its default handler."""
    if is_link:
        return QDesktopServices.openUrl(QUrl(target))
    path = Path(target)
    if sys.platform.startswith("linux") and path.suffix == ".desktop":
        try:
            subprocess.Popen(["gio", "launch", str(path)])
            return True
        except OSError:
            pass
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal(target: str) -> None:
    """Show the item in Finder, File Explorer or the Linux file manager."""
    path = Path(target)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
