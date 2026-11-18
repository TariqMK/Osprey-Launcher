"""Tests that the data folder sits next to the app on every platform."""

from pathlib import Path

from osprey_launcher.paths import PROJECT_ROOT, app_location, ensure_writable


def test_source_run_uses_project_root():
    assert app_location(frozen=False) == PROJECT_ROOT


def test_windows_and_linux_use_executable_folder(tmp_path):
    exe = tmp_path / "Osprey Launcher.exe"
    assert app_location(frozen=True, executable=str(exe), platform="win32") == tmp_path
    assert app_location(frozen=True, executable=str(exe), platform="linux") == tmp_path


def test_macos_uses_folder_beside_app_bundle(tmp_path):
    exe = tmp_path / "Osprey Launcher.app" / "Contents" / "MacOS" / "Osprey Launcher"
    assert app_location(frozen=True, executable=str(exe), platform="darwin") == tmp_path


def test_ensure_writable(tmp_path):
    assert ensure_writable(tmp_path / "data")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert not ensure_writable(Path(blocker) / "data")
