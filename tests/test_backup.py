"""Tests for the readable YAML backup: what it holds, reading it back and recovering from it."""

from pathlib import Path

import pytest
import yaml

from osprey_launcher.backup import BackupError, parse
from osprey_launcher.store import Store


@pytest.fixture
def store(tmp_path):
    (tmp_path / "Reports").mkdir()
    (tmp_path / "notes.txt").write_text("x")
    s = Store(tmp_path / "OspreyLauncher-data", tmp_path)
    work = s.tabs[0]
    s.rename_tab(work.id, "Work")
    reports, notes, link = s.add_targets(
        work.id,
        [
            str(tmp_path / "Reports"),
            str(tmp_path / "notes.txt"),
            "https://example.com/a",
        ],
    )
    s.rename_item(notes.id, "Meeting notes")
    studio = s.add_tab("Studio")
    s.add_targets(studio.id, ["https://github.com/"])
    s.set_starred(link.id, True)
    s.set_starred(reports.id, True)
    return s


def read_backup(store):
    return yaml.safe_load(store.backup_path.read_text(encoding="utf-8"))


def test_backup_is_written_next_to_data_with_readable_fields(store, tmp_path):
    text = store.backup_path.read_text(encoding="utf-8")
    assert store.backup_path.parent == tmp_path / "OspreyLauncher-data"
    assert text.startswith("# Osprey Launcher backup")
    data = read_backup(store)
    assert [t["tab"] for t in data["tabs"]] == ["Work", "Studio"]
    assert [t["position"] for t in data["tabs"]] == [1, 2]
    reports, notes, link = data["tabs"][0]["items"]
    assert reports == {
        "position": 1,
        "name": "Reports",
        "custom_name": None,
        "type": "folder",
        "path": str((tmp_path / "Reports").resolve()),
        "starred": True,
        "starred_position": 2,
    }
    assert notes["custom_name"] == "Meeting notes" and notes["starred"] is False
    assert "starred_position" not in notes
    assert link["type"] == "link" and link["link"] == "https://example.com/a"
    assert link["starred_position"] == 1


def test_backup_updates_after_every_change(store):
    store.remove_item(store.tabs[1].items[0].id)
    assert read_backup(store)["tabs"][1]["items"] == []


def test_round_trip_restores_everything(store):
    tabs, starred, skipped = parse(store.backup_path.read_text(), store.base_dir)
    assert skipped == 0
    shape = lambda ts: [
        [(i.kind, i.name, i.custom_name, i.target) for i in t.items] for t in ts
    ]
    assert [t.name for t in tabs] == ["Work", "Studio"]
    assert shape(tabs) == shape(store.tabs)
    names = {i.id: i.name for t in tabs for i in t.items}
    assert [names[i] for i in starred] == ["example.com", "Reports"]


def test_hand_edited_backup_uses_positions_and_skips_bad_items(tmp_path):
    text = """
tabs:
  - tab: Second
    position: 2
    items: []
  - tab: First
    position: 1
    items:
      - {position: 2, link: example.org}
      - {position: 1, path: /Applications/Notes.app, custom_name: My notes, starred: true}
      - {name: no target}
      - just text
"""
    tabs, starred, skipped = parse(text, tmp_path)
    assert [t.name for t in tabs] == ["First", "Second"]
    first = tabs[0].items
    assert [(i.label, i.kind) for i in first] == [
        ("My notes", "app"),
        ("example.org", "link"),
    ]
    assert first[1].target == "https://example.org"
    assert starred == [first[0].id]
    assert skipped == 2


@pytest.mark.parametrize(
    "text, message",
    [
        ("tabs: [unclosed", "not valid YAML near line"),
        ("just: a mapping", "no list of tabs"),
        ("tabs: []", "no tabs"),
    ],
)
def test_bad_backup_explains_the_problem(tmp_path, text, message):
    with pytest.raises(BackupError, match=message):
        parse(text, tmp_path)


def test_restore_replaces_tabs_and_saves(store):
    tabs, starred, _ = parse(store.backup_path.read_text(), store.base_dir)
    tabs[0].items.pop()  # Drop the starred link before restoring.
    store.restore(tabs, starred)
    reloaded = Store(store.data_dir, store.base_dir)
    assert [len(t.items) for t in reloaded.tabs] == [2, 1]
    assert len(reloaded.starred) == 1


def test_broken_data_file_is_kept_and_backup_is_loaded(store):
    store.path.write_text("{ broken", encoding="utf-8")
    reloaded = Store(store.data_dir, store.base_dir)
    assert reloaded.restored_from_backup
    assert [t.name for t in reloaded.tabs] == ["Work", "Studio"]
    assert len(reloaded.starred) == 2
    broken = list(Path(store.data_dir).glob("launcher.json.broken-*"))
    assert len(broken) == 1 and broken[0].read_text() == "{ broken"
    assert Store(store.data_dir, store.base_dir).restored_from_backup is False


def test_missing_data_file_without_backup_starts_fresh(tmp_path):
    s = Store(tmp_path / "data", tmp_path)
    assert not s.restored_from_backup and [t.name for t in s.tabs] == ["Home"]


def test_existing_data_without_backup_gets_one_at_start(store):
    store.backup_path.unlink()
    Store(store.data_dir, store.base_dir)
    assert [t["tab"] for t in read_backup(store)["tabs"]] == ["Work", "Studio"]
