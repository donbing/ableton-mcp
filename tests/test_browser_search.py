"""search_browser_items: breadth first, every query word, a time budget (idea from upstream #97)."""
import json
import types

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
            node("Wavetable", [node("Analog Pad", loadable=True), node("Bass 808", loadable=True)], loadable=True, device=True),
            node("Operator", loadable=True, device=True)]),
        audio_effects=node("Audio Effects", [
            node("Compressor", [node("Bass Compressor", loadable=True)], loadable=True, device=True),
            node("Glue Compressor", loadable=True, device=True)]),
        sounds=node("Sounds", [node("Pads", [node("Analog Pad Warm", loadable=True)])]))


@pytest.fixture
def inst(script_module):
    obj = make_inst(script_module, types.SimpleNamespace())
    obj.application = lambda: types.SimpleNamespace(browser=browser())
    return obj


def run(inst, **params):
    return inst._process_command({"type": "search_browser_items", "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def test_every_word_of_the_query_must_match_and_shallow_items_come_first(inst):
    result = ok(run(inst, query="analog pad"))
    assert [r["name"] for r in result["results"]] == ["Analog Pad", "Analog Pad Warm"]
    assert result["truncated"] is False and result["count"] == 2
    first = ok(run(inst, query="compressor"))["results"]
    assert [r["name"] for r in first][:2] == ["Compressor", "Glue Compressor"]      # before "Bass Compressor"


def test_a_category_limits_the_search(inst):
    result = ok(run(inst, query="compressor", category="instruments"))
    assert result["results"] == []
    assert ok(run(inst, query="operator", category="instruments"))["results"][0]["uri"] == "query:Operator"


def test_the_root_folders_themselves_are_not_results(inst):
    assert ok(run(inst, query="instruments"))["results"] == []


def test_loadable_only_leaves_out_folders(inst):
    names = [r["name"] for r in ok(run(inst, query="pad", loadable_only=True))["results"]]
    assert "Pads" not in names and "Analog Pad" in names
    assert "Pads" in [r["name"] for r in ok(run(inst, query="pad"))["results"]]


def test_the_result_limit_marks_the_search_as_truncated(inst):
    result = ok(run(inst, query="a", max_results=2))
    assert result["count"] == 2 and result["truncated"] is True


def test_the_time_budget_stops_the_walk(inst, script_module, monkeypatch):
    ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(script_module.time, "time", lambda: next(ticks, 99.0))
    result = ok(run(inst, query="zzz", max_seconds=1.0))
    assert result["truncated"] is True and result["visited"] < 5


@pytest.mark.parametrize("kwargs,needle", [
    (dict(query=""), "query is required"),
    (dict(query="x", category="nope"), "category must be"),
    (dict(query="x", max_results=0), "max_results must be"),
    (dict(query="x", max_seconds=100), "max_seconds"),
])
def test_bad_arguments(inst, kwargs, needle):
    reply = run(inst, **kwargs)
    assert reply["status"] == "error" and needle in reply["message"]


def test_tool_forwards(conn):
    conn.response = {"results": []}
    call(server.search_browser_items, None, "analog pad", "instruments", 5, True, 3.0)
    assert conn.sent[-1] == ("search_browser_items", {"query": "analog pad", "category": "instruments",
                                                      "max_results": 5, "loadable_only": True, "max_seconds": 3.0})


def test_results_leave_out_what_they_repeat(conn):
    conn.response = {"query": "bpm", "count": 3, "truncated": False, "results": [
        {"name": "80s Beat 90 bpm.wav", "path": "samples/80s Beat 90 bpm.wav", "uri": "query:Samples#FileId_3988",
         "is_loadable": True, "is_device": False, "is_folder": False},
        {"name": "Drums", "path": "samples/Drums", "uri": "query:Samples#Drums", "is_loadable": False,
         "is_device": False, "is_folder": True},
        {"name": "Odd", "path": "samples/Other", "uri": "u", "is_loadable": True, "is_device": True,
         "is_folder": False}]}
    out = json.loads(call(server.search_browser_items, None, "bpm"))
    assert out["results"] == [{"path": "samples/80s Beat 90 bpm.wav", "uri": "query:Samples#FileId_3988"},
                              {"path": "samples/Drums", "uri": "query:Samples#Drums", "folder": True,
                               "loadable": False},
                              {"path": "samples/Other", "uri": "u", "name": "Odd", "device": True}]
    assert out["count"] == 3 and out["truncated"] is False
