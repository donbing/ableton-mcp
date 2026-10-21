"""Tests for note editing and clip loop on Session clips.

Tools: get_clip_info, set_clip_loop, remove_notes_from_clip,
apply_note_modifications, quantize_clip.

The Remote Script side runs against a mocked Live Object Model (``_Framework``
stubbed, no socket, no Ableton). The fake clip mimics the parts of Live that
make these edits risky: get_notes_extended returns COPIES of the notes (edits
reach the clip only through apply_note_modifications), and the loop setters
reject an intermediate state where loop_start >= loop_end. Anything that
removes or rewrites notes must preview unless explicitly told to act.

Nothing here talks to Live. Names marked UNVERIFIED in the Remote Script have
only been exercised against this fake.
"""

import asyncio
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")


# ----------------------------------------------------------------- fixtures

def _load_script_module():
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)
    spec = importlib.util.spec_from_file_location(
        "ableton_mcp_script_notes_edit", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeNote(object):
    """Stand-in for a Live MidiNote returned by get_notes_extended."""

    def __init__(self, note_id, pitch, start_time, duration=0.25, velocity=100.0,
                 mute=False):
        self.note_id = note_id
        self.pitch = pitch
        self.start_time = start_time
        self.duration = duration
        self.velocity = velocity
        self.mute = mute

    def copy(self):
        return FakeNote(self.note_id, self.pitch, self.start_time, self.duration,
                        self.velocity, self.mute)


class FakeClip(object):
    def __init__(self, notes=None, length=4.0, midi=True, name="Clip",
                 loop_start=0.0, loop_end=None, looping=True):
        self.name = name
        self.length = length
        self.is_midi_clip = midi
        self.is_audio_clip = not midi
        self.is_playing = False
        self.muted = False
        self.color_index = 7
        self.looping = looping
        self.start_marker = 0.0
        self.end_marker = length
        self._loop_start = loop_start
        self._loop_end = length if loop_end is None else loop_end
        self.notes = list(notes or [])
        self.loop_writes = []        # ("loop_start"|"loop_end", value)
        self.apply_calls = []        # lists of note ids passed
        self.remove_calls = []
        self.quantize_calls = []
        self.loop_end_ignored = False   # a Live that silently refuses loop_end

    # --- loop markers: Live rejects an intermediate state with start >= end
    @property
    def loop_start(self):
        return self._loop_start

    @loop_start.setter
    def loop_start(self, value):
        self.loop_writes.append(("loop_start", value))
        if value >= self._loop_end:
            raise RuntimeError("loop_start must be before loop_end")
        self._loop_start = value

    @property
    def loop_end(self):
        return self._loop_end

    @loop_end.setter
    def loop_end(self, value):
        self.loop_writes.append(("loop_end", value))
        if value <= self._loop_start:
            raise RuntimeError("loop_end must be after loop_start")
        if not self.loop_end_ignored:
            self._loop_end = value

    # --- notes
    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return tuple(n.copy() for n in self.notes
                     if from_pitch <= n.pitch < from_pitch + pitch_span
                     and from_time <= n.start_time < from_time + time_span)

    def apply_note_modifications(self, notes):
        ids = [n.note_id for n in notes]
        self.apply_calls.append(ids)
        by_id = dict((n.note_id, n) for n in self.notes)
        for n in notes:
            if n.note_id not in by_id:
                raise RuntimeError("unknown note id %r" % n.note_id)
        for n in notes:
            by_id[n.note_id].__dict__.update(n.copy().__dict__)

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.remove_calls.append((from_pitch, pitch_span, from_time, time_span))
        doomed = set(id(n) for n in self.notes
                     if from_pitch <= n.pitch < from_pitch + pitch_span
                     and from_time <= n.start_time < from_time + time_span)
        self.notes = [n for n in self.notes if id(n) not in doomed]

    def quantize(self, grid, amount):
        self.quantize_calls.append((grid, amount))
        size = {1: 1.0, 2: 0.5, 3: 1.0 / 3, 5: 0.25, 6: 1.0 / 6, 8: 0.125}[grid]
        for n in self.notes:
            target = round(n.start_time / size) * size
            n.start_time = n.start_time + amount * (target - n.start_time)


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip
        self.has_clip = clip is not None


class FakeTrack(object):
    def __init__(self, slots):
        self.clip_slots = slots


class FakeSong(object):
    def __init__(self, clip):
        self.tracks = [FakeTrack([FakeSlot(clip), FakeSlot(None)])]


def make_notes():
    return [
        FakeNote(1, 36, 0.0, 0.25, 100.0),
        FakeNote(2, 38, 1.1, 0.5, 90.0, mute=True),
        FakeNote(3, 42, 2.0, 0.25, 80.0),
        FakeNote(4, 60, 3.05, 1.0, 70.0),
    ]


def make_inst(script_module, song):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    return obj


@pytest.fixture
def clip():
    return FakeClip(make_notes())


@pytest.fixture
def inst(script_module, clip):
    return make_inst(script_module, FakeSong(clip))


def run(inst, command, **params):
    params.setdefault("track_index", 0)
    params.setdefault("clip_index", 0)
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------ get_clip_info

def test_clip_info_reports_the_facts(inst):
    info = ok(run(inst, "get_clip_info"))
    assert info["name"] == "Clip"
    assert info["length"] == 4.0
    assert info["looping"] is True
    assert (info["loop_start"], info["loop_end"]) == (0.0, 4.0)
    assert (info["start_marker"], info["end_marker"]) == (0.0, 4.0)
    assert info["is_playing"] is False
    assert info["is_midi_clip"] is True
    assert info["note_count"] == 4
    assert info["muted"] is False
    assert info["color_index"] == 7


def test_clip_info_is_a_read_not_scheduled_on_the_main_thread(inst):
    run(inst, "get_clip_info")
    assert inst.scheduled == []


def test_clip_info_for_an_audio_clip_has_no_note_count(script_module):
    audio = FakeClip(midi=False)
    info = ok(run(make_inst(script_module, FakeSong(audio)), "get_clip_info"))
    assert info["is_audio_clip"] is True
    assert info["note_count"] is None


def test_clip_info_leaves_missing_properties_null(script_module):
    class Bare(object):
        is_midi_clip = False
        name = "x"
        length = 2.0

    info = ok(run(make_inst(script_module, FakeSong(Bare())), "get_clip_info"))
    assert info["muted"] is None
    assert info["color_index"] is None
    assert info["loop_start"] is None


@pytest.mark.parametrize("params,needle", [
    ({"track_index": 5}, "Track index out of range"),
    ({"clip_index": 9}, "Clip index out of range"),
    ({"clip_index": 1}, "No clip in slot"),
    ({"track_index": True}, "must be an integer"),
    ({"clip_index": 0.5}, "must be an integer"),
])
def test_clip_info_errors(inst, params, needle):
    assert needle in err(run(inst, "get_clip_info", **params))


# ------------------------------------------------------ server tool wrappers

class FakeConnection(object):
    def __init__(self):
        self.responses = []
        self.raise_exc = None
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, dict(params or {})))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.responses.pop(0) if self.responses else {}


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    fake = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    return fake


def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def _tool(name):
    return next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == name)


def test_get_clip_info_tool_sends_the_command_and_returns_json(conn):
    conn.responses = [{"name": "Clip", "note_count": 4}]
    out = call(server.get_clip_info, None, 2, 3)
    assert conn.sent == [("get_clip_info", {"track_index": 2, "clip_index": 3})]
    assert json.loads(out)["note_count"] == 4


def test_get_clip_info_tool_is_read_only_and_keeps_user_prompt():
    tool = _tool("get_clip_info")
    assert tool.annotations.readOnlyHint is True
    assert "user_prompt" in tool.inputSchema["properties"]


def test_get_clip_info_tool_reports_errors(conn):
    conn.raise_exc = Exception("No clip in slot")
    assert call(server.get_clip_info, None, 0, 0).startswith("Error getting clip info:")


def test_get_clip_info_tool_returns_the_capability_message_for_an_old_script(
        conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.get_clip_info, None, 0, 0) == "missing get_clip_info"
    assert conn.sent == []
