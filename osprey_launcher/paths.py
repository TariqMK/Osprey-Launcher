"""Finds the portable data folder that sits next to the app, so moving the app moves its data."""

from __future__ import annotations

import sys
from pathlib import Path

DATA_DIR_NAME = "OspreyLauncher-data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def app_location(
    frozen: bool | None = None,
    executable: str | None = None,
    platform: str | None = None,
) -> Path:
    """Return the folder the app lives in.

    From source this is the project root. In a packaged build it is the folder
    that holds the executable, or the folder that holds the .app on macOS.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return PROJECT_ROOT
    exe = Path(executable or sys.executable).resolve()
    if (platform or sys.platform) == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
    return exe.parent


def default_data_dir() -> Path:
    """Return the data folder next to the app."""
    return app_location() / DATA_DIR_NAME


def ensure_writable(folder: Path) -> bool:
    """Create the folder if needed and check the app can write to it."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
