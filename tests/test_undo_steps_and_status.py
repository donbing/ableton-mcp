"""One undo step per tool call, get_live_status and press_dialog_button.

Measured on Live 12.4 Lite (2026-10-24): Song.begin_undo_step / end_undo_step make each wrapped edit its
own undo step; without them Live merged every API edit into one. A multi-tick tool (locators, routing)
is not wrapped, because a step left open across ticks would swallow the user's own edits in between.
"""
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Song(object):
    def __init__(self, with_steps=True):
        self.log = []
        self.tracks = [types.SimpleNamespace(name="Bass", performance_impact=0.3),
                       types.SimpleNamespace(name="Pad", performance_impact=1.8)]
        self.return_tracks = [types.SimpleNamespace(name="A-Reverb", performance_impact=0.9)]
        self.is_playing, self.tempo, self.exclusive_arm, self.exclusive_solo = False, 120.0, False, False
        self.cue_points = []
        if with_steps:
            self.begin_undo_step = lambda: self.log.append("begin")
            self.end_undo_step = lambda: self.log.append("end")

    def set_tempo_mark(self, value):
        self.log.append("tempo=%s" % value)
        self.tempo = value


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def test_a_modifying_command_runs_inside_its_own_undo_step(script_module):
    song = Song()
    inst = make_inst(script_module, song)
    inst._set_tempo = lambda tempo: song.set_tempo_mark(tempo) or {"tempo": tempo}
    assert run(inst, "set_tempo", tempo=100.0)["status"] == "success"
    assert song.log == ["begin", "tempo=100.0", "end"]


def test_the_step_is_closed_even_when_the_command_fails(script_module):
    song = Song()
    inst = make_inst(script_module, song)

    def boom(tempo):
        song.log.append("boom")
        raise ValueError("nope")

    inst._set_tempo = boom
    assert run(inst, "set_tempo", tempo=100.0)["status"] == "error"
    assert song.log == ["begin", "boom", "end"]


def test_undo_and_redo_are_never_wrapped(script_module):
    song = Song()
    inst = make_inst(script_module, song)
    assert inst._begin_undo_step("undo") is False and inst._begin_undo_step("redo") is False
    assert inst._begin_undo_step("create_clip") is True
    assert song.log == ["begin"]


def test_a_live_without_undo_steps_still_works(script_module):
    song = Song(with_steps=False)
    inst = make_inst(script_module, song)
    inst._set_tempo = lambda tempo: {"tempo": tempo}
    assert inst._begin_undo_step("set_tempo") is False
    assert run(inst, "set_tempo", tempo=100.0)["status"] == "success"
    inst._end_undo_step(False)        # nothing to close, nothing raised


def test_a_failing_begin_or_end_does_not_break_the_command(script_module):
    song = Song()
    song.begin_undo_step = lambda: (_ for _ in ()).throw(RuntimeError("no"))
    inst = make_inst(script_module, song)
    inst._set_tempo = lambda tempo: {"tempo": tempo}
    assert run(inst, "set_tempo", tempo=100.0)["status"] == "success"
    song2 = Song()
    song2.end_undo_step = lambda: (_ for _ in ()).throw(RuntimeError("no"))
    inst2 = make_inst(script_module, song2)
    inst2._set_tempo = lambda tempo: {"tempo": tempo}
    assert run(inst2, "set_tempo", tempo=100.0)["status"] == "success"


# -------------------------------------------------------------- live status

class App(object):
    def __init__(self, dialogs=0):
        self.average_process_usage, self.peak_process_usage = 0.12, 0.4
        self.unavailable_features = ["max_for_live", "freeze"]
        self.open_dialog_count = dialogs
        self.current_dialog_message = "Couldn't create track. Live Lite allows 8 tracks." if dialogs else ""
        self.current_dialog_button_count = 1 if dialogs else 0
        self.pressed = []

    def get_version_string(self): return "12.4 (2026-10-01)"
    def get_build_id(self): return "build-1"
    def get_variant(self): return "lite"

    def press_current_dialog_button(self, index):
        self.pressed.append(index)
        self.open_dialog_count = 0


def with_app(script_module, app):
    inst = make_inst(script_module, Song())
    inst.application = lambda: app
    return inst


def test_live_status_has_version_cpu_and_the_heaviest_track_first(script_module):
    result = run(with_app(script_module, App()), "get_live_status")["result"]
    assert (result["version"], result["variant"], result["cpu_average"]) == ("12.4 (2026-10-01)", "lite", 0.12)
    assert result["features_this_edition_lacks"] == ["max_for_live", "freeze"]
    assert [t["name"] for t in result["track_performance_impact"]] == ["Pad", "A-Reverb", "Bass"]
    assert result["open_dialogs"] == 0 and "dialog_message" not in result


def test_one_field_this_live_lacks_does_not_stop_the_rest(script_module):
    app = App()
    app.get_variant = lambda: (_ for _ in ()).throw(AttributeError("no variant"))
    result = run(with_app(script_module, app), "get_live_status")["result"]
    assert result["variant"] is None and result["version"] == "12.4 (2026-10-01)"
    assert any("variant" in u for u in result["unavailable"])


def test_an_open_dialog_is_reported_with_its_text(script_module):
    result = run(with_app(script_module, App(dialogs=1)), "get_live_status")["result"]
    assert result["open_dialogs"] == 1 and "Couldn't create track" in result["dialog_message"]
    assert result["dialog_button_count"] == 1


# ------------------------------------------------------------------ dialogs

def test_the_dialog_is_pressed_only_when_its_text_matches(script_module):
    app = App(dialogs=1)
    inst = with_app(script_module, app)
    reply = run(inst, "press_dialog_button", button_index=0, expected_message="couldn't create TRACK")
    assert reply["status"] == "success" and app.pressed == [0]
    assert reply["result"]["open_dialogs_after"] == 0


@pytest.mark.parametrize("kwargs,needle", [
    (dict(button_index=0, expected_message="Save changes?"), "not something containing"),
    (dict(button_index=3, expected_message="create track"), "out of range"),
    (dict(button_index=0, expected_message=""), "expected_message is required"),
    (dict(button_index="0", expected_message="create track"), "must be an integer"),
])
def test_a_wrong_dialog_index_or_missing_text_presses_nothing(script_module, kwargs, needle):
    app = App(dialogs=1)
    reply = run(with_app(script_module, app), "press_dialog_button", **kwargs)
    assert reply["status"] == "error" and needle in reply["message"] and app.pressed == []


def test_pressing_with_no_dialog_open_is_an_error(script_module):
    reply = run(with_app(script_module, App()), "press_dialog_button", button_index=0, expected_message="x")
    assert reply["status"] == "error" and "No dialog is open" in reply["message"]


def test_tools(conn):
    conn.response = {"version": "12.4"}
    call(server.get_live_status, None)
    assert conn.sent[-1] == ("get_live_status", {})
    call(server.press_dialog_button, None, 0, "create track")
    assert conn.sent[-1] == ("press_dialog_button", {"button_index": 0, "expected_message": "create track"})
    assert "required" in call(server.press_dialog_button, None, 0, None)
