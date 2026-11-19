"""Tests for the launcher data store: adding, detecting, saving and finding items."""

import json
from pathlib import Path

import pytest

from osprey_launcher.models import (
    detect_kind,
    display_name,
    normalise_url,
    resolve_target,
    to_stored,
)
from osprey_launcher.store import Store


@pytest.fixture
def base(tmp_path):
    (tmp_path / "Reports").mkdir()
    (tmp_path / "Reports" / "Budget 2026.xlsx").write_text("x")
    (tmp_path / "Notes.app").mkdir()
    return tmp_path


def make_store(base: Path) -> Store:
    return Store(base / "OspreyLauncher-data", base)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://example.com", "https://example.com"),
        ("example.com/path", "https://example.com/path"),
        ("  www.example.org  ", "https://www.example.org"),
        ("http://localhost:8080", "http://localhost:8080"),
        ("not a url", None),
        ("localhost", None),
        ("ftp://example.com", None),
        (r"C:\Users\sam\notes.txt", None),
        ("", None),
    ],
)
def test_normalise_url(text, expected):
    assert normalise_url(text) == expected


def test_detect_kind(base):
    assert detect_kind("https://example.com") == "link"
    assert detect_kind(str(base / "Reports")) == "folder"
    assert detect_kind(str(base / "Reports" / "Budget 2026.xlsx")) == "file"
    assert detect_kind(str(base / "Notes.app")) == "app"
    assert detect_kind("C:/Tools/Editor.lnk") == "app"


def test_display_name_drops_app_extension():
    assert display_name("/Applications/Notes.app", "app") == "Notes"
    assert display_name("/tmp/Budget 2026.xlsx", "file") == "Budget 2026.xlsx"
    assert display_name("https://www.example.com/x", "link") == "example.com"


def test_paths_inside_base_are_stored_relative(base, tmp_path_factory):
    inside = base / "Reports" / "Budget 2026.xlsx"
    assert to_stored(str(inside), base) == "Reports/Budget 2026.xlsx"
    outside = tmp_path_factory.mktemp("elsewhere") / "a.txt"
    assert Path(to_stored(str(outside), base)).is_absolute()


def test_relative_items_follow_a_moved_app_folder(base, tmp_path_factory):
    store = make_store(base)
    store.add_targets(store.tabs[0].id, [str(base / "Reports")])
    moved = tmp_path_factory.mktemp("moved")
    (moved / "Reports").mkdir()
    item = Store(base / "OspreyLauncher-data", moved).tabs[0].items[0]
    assert resolve_target(item, moved) == str(moved / "Reports")


def test_first_run_has_one_empty_tab(base):
    store = make_store(base)
    assert [t.name for t in store.tabs] == ["Home"]
    assert store.tabs[0].items == []


def test_add_items_skips_duplicates_and_saves(base):
    store = make_store(base)
    tab_id = store.tabs[0].id
    targets = [str(base / "Reports"), "https://example.com", str(base / "Reports")]
    added = store.add_targets(tab_id, targets)
    assert [i.kind for i in added] == ["folder", "link"]
    assert store.add_targets(tab_id, ["https://example.com"]) == []

    reloaded = make_store(base)
    assert [(i.name, i.kind) for i in reloaded.tabs[0].items] == [
        ("Reports", "folder"),
        ("example.com", "link"),
    ]


def test_tabs_rename_move_and_remove(base):
    store = make_store(base)
    home = store.tabs[0]
    work = store.add_tab("Work")
    item = store.add_targets(home.id, [str(base / "Reports")])[0]

    store.move_item(item.id, work.id)
    assert home.items == [] and work.items == [item]

    store.rename_tab(work.id, "  Studio ")
    assert work.name == "Studio"

    store.remove_tab(home.id)
    store.remove_tab(work.id)  # The last tab is kept.
    assert [t.name for t in make_store(base).tabs] == ["Studio"]


def _tab_with_links(store, names):
    tab = store.tabs[0]
    store.add_targets(tab.id, [f"https://{n}.example.com" for n in names])
    return tab, {i.name.split(".")[0]: i.id for i in tab.items}


def _order(tab):
    return [i.name.split(".")[0] for i in tab.items]


@pytest.mark.parametrize(
    "moving, index, expected",
    [
        ("a", 3, ["b", "c", "a", "d"]),  # Forward: drop between c and d.
        ("a", 4, ["b", "c", "d", "a"]),  # To the end.
        ("d", 0, ["d", "a", "b", "c"]),  # Back to the start.
        ("c", 1, ["a", "c", "b", "d"]),  # Back by one.
    ],
)
def test_reorder_within_tab(base, moving, index, expected):
    store = make_store(base)
    tab, ids = _tab_with_links(store, "abcd")
    assert store.move_item(ids[moving], tab.id, index)
    assert _order(tab) == expected
    assert _order(make_store(base).tabs[0]) == expected


@pytest.mark.parametrize("index", [0, 1, None])
def test_dropping_in_place_changes_nothing(base, index):
    store = make_store(base)
    tab, ids = _tab_with_links(store, "abc")
    assert not store.move_item(ids["a"], tab.id, index)
    assert _order(tab) == ["a", "b", "c"]


def test_move_to_other_tab_at_position(base):
    store = make_store(base)
    tab, ids = _tab_with_links(store, "abc")
    other = store.add_tab("Work")
    store.add_targets(other.id, ["https://x.example.com", "https://y.example.com"])
    assert store.move_item(ids["b"], other.id, 1)
    assert _order(tab) == ["a", "c"]
    assert _order(other) == ["x", "b", "y"]
    assert store.move_item(ids["a"], other.id, 99)
    assert _order(other) == ["x", "b", "y", "a"]


def test_missing_target_is_reported_and_can_be_relocated(base):
    store = make_store(base)
    file = base / "Reports" / "Budget 2026.xlsx"
    item = store.add_targets(store.tabs[0].id, [str(file)])[0]
    file.rename(base / "Budget.xlsx")
    assert not store.target_exists(item)
    store.relocate_item(item.id, str(base / "Budget.xlsx"))
    assert store.target_exists(item)


def test_search_matches_name_across_tabs(base):
    store = make_store(base)
    store.add_targets(store.tabs[0].id, [str(base / "Reports")])
    other = store.add_tab("Work")
    store.add_targets(other.id, ["https://reports.example.com"])
    names = [item.name for _tab, item in store.search("REPORT")]
    assert names == ["Reports", "reports.example.com"]
    assert store.search("   ") == []


def test_search_ignores_folder_path(base):
    store = make_store(base)
    store.add_targets(store.tabs[0].id, [str(base / "Reports" / "Budget 2026.xlsx")])
    assert store.search("reports") == []
    assert [i.name for _t, i in store.search("budget")] == ["Budget 2026.xlsx"]


def test_corrupt_data_file_starts_fresh(base):
    data = base / "OspreyLauncher-data"
    data.mkdir()
    (data / "launcher.json").write_text("{ not json")
    store = make_store(base)
    assert len(store.tabs) == 1


def test_display_settings_default_on_and_are_saved(base):
    store = make_store(base)
    assert store.show_names and store.show_types
    store.set_display(types=False)
    reloaded = make_store(base)
    assert reloaded.show_names and not reloaded.show_types
    reloaded.set_display(names=False)
    assert not make_store(base).show_names


def test_theme_setting_is_saved(base):
    store = make_store(base)
    store.set_theme("dark")
    store.set_theme("purple")
    assert make_store(base).theme == "dark"


def test_starring_keeps_order_and_is_saved(base):
    store = make_store(base)
    tab, ids = _tab_with_links(store, "abcd")
    assert store.starred_items() == []
    store.set_starred(ids["c"], True)
    store.set_starred(ids["a"], True)
    store.set_starred(ids["d"], True, index=0)
    assert not store.set_starred(ids["a"], True)  # Already starred.
    assert [i.name[0] for _t, i in store.starred_items()] == ["d", "c", "a"]
    assert store.move_starred(ids["a"], 0)
    assert make_store(base).starred == [ids["a"], ids["d"], ids["c"]]
    store.set_starred(ids["d"], False)
    assert not store.is_starred(ids["d"])
    assert _order(tab) == ["a", "b", "c", "d"]  # Starring never changes the home tab.


def test_starred_items_survive_moves_and_go_with_removal(base):
    store = make_store(base)
    _tab, ids = _tab_with_links(store, "abc")
    other = store.add_tab("Work")
    for key in "abc":
        store.set_starred(ids[key], True)
    store.move_item(ids["a"], other.id)
    assert store.is_starred(ids["a"])
    store.remove_item(ids["b"])
    store.remove_tab(other.id)
    assert store.starred == [ids["c"]]
    assert make_store(base).starred == [ids["c"]]


def test_unknown_starred_ids_are_dropped_on_load(base):
    store = make_store(base)
    _tab, ids = _tab_with_links(store, "a")
    store.starred = [ids["a"], "gone", ids["a"]]
    store.save()
    assert make_store(base).starred == [ids["a"]]


def test_custom_name_keeps_original_and_can_be_reset(base):
    store = make_store(base)
    item = store.add_targets(store.tabs[0].id, [str(base / "Reports")])[0]
    store.rename_item(item.id, "  Quarterly reports ")
    assert (item.name, item.custom_name, item.label) == (
        "Reports",
        "Quarterly reports",
        "Quarterly reports",
    )
    assert [i.label for _t, i in store.search("quarterly")] == ["Quarterly reports"]
    assert [i.label for _t, i in store.search("reports")] == ["Quarterly reports"]
    assert make_store(base).tabs[0].items[0].custom_name == "Quarterly reports"
    store.rename_item(item.id, "")
    assert item.custom_name is None and item.label == "Reports"
    store.rename_item(item.id, "Reports")  # Same as the original: no custom name.
    assert item.custom_name is None


def test_tile_size_defaults_to_tiles_and_is_saved(base):
    store = make_store(base)
    assert store.tile_size == 3
    store.set_display(size=1)
    assert make_store(base).tile_size == 1


def test_tile_size_stays_in_range(base):
    store = make_store(base)
    store.set_display(size=9)
    assert store.tile_size == 5
    store.set_display(size=0)
    assert store.tile_size == 1


def test_bad_tile_size_in_file_falls_back(base):
    store = make_store(base)
    store.save()
    for bad in (7, "big", True, None):
        raw = json.loads(store.path.read_text(encoding="utf-8"))
        raw["display"]["size"] = bad
        store.path.write_text(json.dumps(raw), encoding="utf-8")
        assert make_store(base).tile_size == 3, bad
