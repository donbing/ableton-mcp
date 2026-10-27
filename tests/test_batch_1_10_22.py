"""1.10.22: get_browser_tree covers every root, counts the loadable items below each folder,
and get_browser_items_at_path pages, compacts and filters by kind.

Remote Script side runs against a fake browser of SimpleNamespace nodes (no Live). Server
side runs the real tool functions with the fake connection from test_scenes.
"""
import types
import typing

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


def node(name, children=(), loadable=False, device=False, uri=None):
    return types.SimpleNamespace(name=name, children=list(children), is_loadable=loadable,
                                 is_device=device, is_folder=bool(children),
                                 uri=uri or "query:" + name.replace(" ", "_"))


def browser():
    return types.SimpleNamespace(
        instruments=node("Instruments", [
            node("Wavetable", [node("Analog Pad", loadable=True), node("Bass 808", loadable=True),
                               node("Deep Pad", [node("Wide Pad", loadable=True)])],
                 loadable=True, device=True),
            node("Operator", loadable=True, device=True)]),
        sounds=node("Sounds", [node("Pads", [node("Analog Pad Warm", loadable=True)])]),
        drums=node("Drums", [node("Kits", [node("808 Kit", loadable=True),
                                           node("Kick 01.wav", loadable=True),
                                           node("Snare.aif", loadable=True)])]),
        audio_effects=node("Audio Effects", [node("Glue Compressor", loadable=True, device=True)]),
        midi_effects=node("MIDI Effects", [node("Arpeggiator", loadable=True, device=True)]),
        plugins=node("Plugins", [node("VST", [node("Synth X", loadable=True, device=True)])]),
        user_library=node("User Library", [node("Big", [node("Preset %03d" % i, loadable=True)
                                                        for i in range(120)])]),
        packs=node("Packs", [node("Pack A", [node("Loop.wav", loadable=True),
                                             node("Bass", [node("Sub.wav", loadable=True)])])]),
        # samples and clips are flat on the Push (4,005 and 350 items in 12.4.6)
        samples=node("Samples", [node("Kick %02d.wav" % i, loadable=True) for i in range(60)]),
        clips=node("Clips", [node("Groove 1.alc", loadable=True)]),
        current_project=node("Current Project"))


@pytest.fixture
def inst(script_module):
    obj = make_inst(script_module, types.SimpleNamespace())
    obj.application = lambda: types.SimpleNamespace(browser=browser())
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def by_name(nodes):
    return {n["name"]: n for n in nodes}


# ------------------------------------------------------------- get_browser_tree

def test_schema_enum_matches_the_remote_script_roots(script_module):
    assert typing.get_args(server.BrowserCategory) == ("all",) + script_module.AbletonMCP.BROWSER_ROOTS


def test_samples_page_like_any_folder(inst):
    page = ok(run(inst, "get_browser_items_at_path", path="samples", kind="sample"))
    assert page["total"] == 60 and len(page["items"]) == 50 and page["next_offset"] == 50
    tree = ok(run(inst, "get_browser_tree", category_type="samples"))
    root = tree["categories"][0]
    assert root["name"] == "Samples" and root["item_count"] == 60 and root["truncated"] is True


def test_an_empty_current_project_is_listed_not_an_error(inst):
    root = ok(run(inst, "get_browser_tree", category_type="current_project"))["categories"][0]
    assert root["name"] == "Current Project" and root["is_folder"] is False and root["children"] == []


def test_all_roots_are_covered(inst, script_module):
    tree = ok(run(inst, "get_browser_tree"))
    assert [c["root"] for c in tree["categories"]] == list(script_module.AbletonMCP.BROWSER_ROOTS)
    assert tree["categories"][0]["name"] == "Instruments"
    assert tree["available_categories"] == list(script_module.AbletonMCP.BROWSER_ROOTS)


def test_one_root_by_name(inst):
    tree = ok(run(inst, "get_browser_tree", category_type="sounds"))
    assert [c["root"] for c in tree["categories"]] == ["sounds"]


def test_depth_one_lists_the_first_level_and_marks_folders_below_it(inst):
    root = ok(run(inst, "get_browser_tree", category_type="instruments", depth=1))["categories"][0]
    wavetable, operator = root["children"]
    assert wavetable["name"] == "Wavetable" and wavetable["has_more"] is True
    assert wavetable["children"] == []
    assert "has_more" not in operator and operator["children"] == []


@pytest.mark.parametrize("depth,expect_deep_children", [(2, []), (3, ["Wide Pad"])])
def test_deeper_levels_expand_one_more_folder(inst, depth, expect_deep_children):
    root = ok(run(inst, "get_browser_tree", category_type="instruments", depth=depth))["categories"][0]
    wavetable = by_name(root["children"])["Wavetable"]
    deep_pad = by_name(wavetable["children"])["Deep Pad"]
    assert [c["name"] for c in deep_pad["children"]] == expect_deep_children
    assert deep_pad.get("has_more", False) is (depth == 2)


def test_item_counts_count_loadable_items_anywhere_below(inst):
    root = ok(run(inst, "get_browser_tree", category_type="instruments"))["categories"][0]
    # Analog Pad, Bass 808, Wide Pad, Operator and Wavetable itself is below the root
    assert root["item_count"] == 5
    wavetable = by_name(root["children"])["Wavetable"]
    assert wavetable["item_count"] == 3
    assert "item_count" not in by_name(root["children"])["Operator"]


def test_without_counts_there_are_no_counts_and_no_approximate_flag(inst):
    tree = ok(run(inst, "get_browser_tree", category_type="instruments", with_counts=False))
    assert "approximate" not in tree
    assert "item_count" not in tree["categories"][0]


def test_a_folder_with_many_children_lists_fifty_and_says_how_many(inst):
    many = [node("Preset %d" % i, loadable=True) for i in range(120)]
    inst.application = lambda: types.SimpleNamespace(
        browser=types.SimpleNamespace(instruments=node("Instruments", many)))
    root = ok(run(inst, "get_browser_tree", category_type="instruments"))["categories"][0]
    assert len(root["children"]) == 50
    assert root["truncated"] is True and root["total_children"] == 120
    assert root["item_count"] == 120


def test_the_count_budget_marks_counts_approximate(inst, script_module, monkeypatch):
    # The deadline is set from the first clock read; every later read is past it
    clock = iter([0.0])
    monkeypatch.setattr(script_module.time, "time", lambda: next(clock, 100.0))
    tree = inst.get_browser_tree("instruments", 1, True)
    root = tree["categories"][0]
    assert tree["approximate"] is True
    assert root["item_count"] < 5


@pytest.mark.parametrize("kwargs,needle", [
    (dict(category_type="nope"), "category_type must be 'all' or one of"),
    (dict(depth=0), "depth must be a whole number from 1 to 3"),
    (dict(depth=4), "depth must be a whole number from 1 to 3"),
    (dict(depth="deep"), "depth must be"),
])
def test_tree_bad_arguments(inst, kwargs, needle):
    reply = run(inst, "get_browser_tree", **kwargs)
    assert reply["status"] == "error" and needle in reply["message"]


def test_tree_old_call_shape_still_works(inst):
    tree = ok(run(inst, "get_browser_tree", category_type="instruments"))
    assert tree["depth"] == 1 and tree["with_counts"] is True
    assert tree["categories"][0]["children"][0]["name"] == "Wavetable"


# -------------------------------------------------------- get_browser_items_at_path

def test_the_page_reports_total_offset_limit_and_next_offset(inst):
    first = ok(run(inst, "get_browser_items_at_path", path="user_library/Big"))
    assert first["total"] == 120 and first["offset"] == 0 and first["limit"] == 50
    assert len(first["items"]) == 50 and first["next_offset"] == 50
    last = ok(run(inst, "get_browser_items_at_path", path="user_library/Big", offset=100, limit=50))
    assert len(last["items"]) == 20 and "next_offset" not in last
    assert last["items"][0]["name"] == "Preset 100"
    everything = ok(run(inst, "get_browser_items_at_path", path="user_library/Big", limit=200))
    assert len(everything["items"]) == 120 and "next_offset" not in everything


def test_compact_items_have_name_and_type(inst):
    items = ok(run(inst, "get_browser_items_at_path", path="instruments"))["items"]
    # a device that holds presets is a device, with the count of what is inside it
    assert items[0] == {"name": "Wavetable", "type": "device", "item_count": 3}
    assert items[1] == {"name": "Operator", "type": "device"}


def test_compact_types_for_presets_and_samples(inst):
    kits = ok(run(inst, "get_browser_items_at_path", path="drums/Kits"))["items"]
    assert kits == [{"name": "808 Kit", "type": "preset"},
                    {"name": "Kick 01.wav", "type": "sample"},
                    {"name": "Snare.aif", "type": "sample"}]
    pack = ok(run(inst, "get_browser_items_at_path", path="packs/Pack A"))["items"]
    assert pack[0] == {"name": "Loop.wav", "type": "sample"}
    assert pack[1] == {"name": "Bass", "type": "folder", "item_count": 1}


def test_full_items_keep_uri_and_flags(inst):
    items = ok(run(inst, "get_browser_items_at_path", path="instruments", compact=False))["items"]
    assert items[0] == {"name": "Wavetable", "is_folder": True, "is_device": True,
                        "is_loadable": True, "uri": "query:Wavetable"}
    assert "type" not in items[0] and "item_count" not in items[0]


@pytest.mark.parametrize("kind,path,names", [
    ("device", "instruments", ["Wavetable", "Operator"]),
    ("folder", "packs/Pack A", ["Bass"]),
    ("sample", "drums/Kits", ["Kick 01.wav", "Snare.aif"]),
    ("preset", "drums/Kits", ["808 Kit"]),
])
def test_kind_filters_before_paging(inst, kind, path, names):
    result = ok(run(inst, "get_browser_items_at_path", path=path, kind=kind))
    assert [item["name"] for item in result["items"]] == names
    assert result["total"] == len(names)


def test_kind_is_counted_before_offset_and_limit(inst):
    result = ok(run(inst, "get_browser_items_at_path", path="drums/Kits", kind="sample", offset=1, limit=1))
    assert [item["name"] for item in result["items"]] == ["Snare.aif"]
    assert result["total"] == 2 and "next_offset" not in result


def test_unknown_category_still_lists_the_categories(inst):
    result = ok(run(inst, "get_browser_items_at_path", path="nope/x"))
    assert "Unknown or unavailable category" in result["error"]
    assert "instruments" in result["available_categories"]


@pytest.mark.parametrize("kwargs,needle", [
    (dict(path="instruments", limit=0), "limit must be a whole number from 1 to 200"),
    (dict(path="instruments", limit=201), "limit must be"),
    (dict(path="instruments", offset=-1), "offset must be"),
    (dict(path="instruments", kind="song"), "kind must be one of"),
])
def test_items_bad_arguments(inst, kwargs, needle):
    reply = run(inst, "get_browser_items_at_path", **kwargs)
    assert reply["status"] == "error" and needle in reply["message"]


def test_items_old_call_shape_still_works(inst):
    result = ok(run(inst, "get_browser_items_at_path", path="drums/Kits"))
    assert result["name"] == "Kits" and result["total"] == 3 and result["offset"] == 0


# ------------------------------------------------------------------ MCP tools

def test_tree_tool_forwards_depth_and_counts(conn):
    conn.response = {"categories": [], "available_categories": ["instruments"]}
    call(server.get_browser_tree, None, "instruments", "", 2, False)
    assert conn.sent[-1] == ("get_browser_tree", {"category_type": "instruments", "depth": 2,
                                                  "with_counts": False})


def test_tree_tool_formats_counts_paths_and_truncation(conn):
    conn.response = {"total_folders": 2, "categories": [{
        "name": "Instruments", "root": "instruments", "is_folder": True, "item_count": 5,
        "children": [
            {"name": "Wavetable", "is_folder": True, "item_count": 3, "has_more": True,
             "total_children": 3, "children": []},
            {"name": "Packs", "is_folder": True, "item_count": 120, "truncated": True,
             "total_children": 120, "children": [{"name": "Pack A", "is_folder": False, "children": []},
                                                 {"name": "Pack B", "is_folder": False, "children": []}]}]}]}
    out = call(server.get_browser_tree, None, "instruments")
    assert "Instruments (5 items) (path: instruments)" in out
    assert "  • Wavetable (3 items) (path: instruments/Wavetable) [...]" in out
    assert "  • Packs (120 items) (path: instruments/Packs) [first 2 of 120 children]" in out


def test_items_tool_forwards_paging_and_kind(conn):
    conn.response = {"items": []}
    call(server.get_browser_items_at_path, None, "drums/Kits", "", 50, 200, True, "sample")
    assert conn.sent[-1] == ("get_browser_items_at_path", {"path": "drums/Kits", "offset": 50,
                                                          "limit": 200, "compact": True, "kind": "sample"})


def test_load_drum_kit_still_gets_uris_and_every_kit(conn):
    conn.response = {"loaded": True, "items": [{"name": "808 Kit", "is_loadable": True, "uri": "u"}]}
    call(server.load_drum_kit, None, 0, "Drums/Drum Rack", "drums/Kits")
    assert conn.sent[1] == ("get_browser_items_at_path", {"path": "drums/Kits", "limit": 200,
                                                          "compact": False})
