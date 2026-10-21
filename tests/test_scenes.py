"""Tests for the Session scene tools (get/create/delete/duplicate/fire/rename,
stop all clips).

Remote Script side runs against a mocked Live Object Model (``_Framework``
stubbed, no socket, no Ableton). The fake Song keeps scenes and the clip grid in
step, shifts indices on create/delete like Live, and has switches for the
behaviours that cannot be confirmed without a real set: a Live Lite style limit
that either raises or silently does nothing. Server side runs the real tool
functions with a fake connection.
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
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")
SOURCE_SCRIPT = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"

SCENE_COMMANDS = ("get_scenes", "create_scene", "delete_scene", "duplicate_scene",
                  "fire_scene", "set_scene_name", "stop_all_clips")


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
        "ableton_mcp_script_scenes", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeClip(object):
    def __init__(self, name):
        self.name = name


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeScene(object):
    def __init__(self, name="", tempo=-1.0):
        self.name = name
        self.tempo = tempo
        self.is_triggered = False
        self.fired = 0

    def fire(self):
        self.fired += 1
        self.is_triggered = True


class FakeTrack(object):
    def __init__(self, name):
        self.name = name
        self.clip_slots = []


class FakeSong(object):
    """scenes + tracks[].clip_slots kept in step, like Live's session grid.

    limit: maximum scene count (a Live Lite style cap).
    limit_raises: True = Live raises when over the cap, False = silently does
    nothing. Both must end in a readable error and an unchanged set.
    """

    def __init__(self, scene_names=("Intro", "Verse", "Chorus"), tracks=2,
                 limit=None, limit_raises=True):
        self.scenes = [FakeScene(n) for n in scene_names]
        self.tracks = [FakeTrack("Track %d" % (i + 1)) for i in range(tracks)]
        for t in self.tracks:
            t.clip_slots = [FakeSlot() for _ in self.scenes]
        self.limit = limit
        self.limit_raises = limit_raises
        self.calls = []
        self.silently_ignore_delete = False

    def put_clip(self, track, scene, name):
        self.tracks[track].clip_slots[scene].clip = FakeClip(name)

    def _full(self):
        if self.limit is not None and len(self.scenes) >= self.limit:
            if self.limit_raises:
                raise RuntimeError("Live Lite: scene limit reached")
            return True
        return False

    def create_scene(self, index):
        self.calls.append(("create_scene", index))
        if self._full():
            return
        at = len(self.scenes) if index == -1 else index
        self.scenes.insert(at, FakeScene())
        for t in self.tracks:
            t.clip_slots.insert(at, FakeSlot())

    def duplicate_scene(self, index):
        self.calls.append(("duplicate_scene", index))
        if self._full():
            return
        src = self.scenes[index]
        self.scenes.insert(index + 1, FakeScene(src.name, src.tempo))
        for t in self.tracks:
            slot = t.clip_slots[index]
            copy = FakeSlot(FakeClip(slot.clip.name) if slot.has_clip else None)
            t.clip_slots.insert(index + 1, copy)

    def delete_scene(self, index):
        self.calls.append(("delete_scene", index))
        if self.silently_ignore_delete:
            return
        del self.scenes[index]
        for t in self.tracks:
            del t.clip_slots[index]

    def stop_all_clips(self):
        self.calls.append(("stop_all_clips",))


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
def song():
    s = FakeSong()
    s.put_clip(0, 1, "Verse Keys")
    s.put_clip(1, 1, "Verse Drums")
    s.put_clip(0, 2, "Chorus Keys")
    s.scenes[1].tempo = 128.0
    return s


@pytest.fixture
def inst(script_module, song):
    return make_inst(script_module, song)


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def names(song):
    return [s.name for s in song.scenes]


def listed(reply):
    return [(s["index"], s["name"]) for s in reply["result"]["scenes"]]


# ---------------------------------------------------------------- get_scenes

def test_get_scenes_reports_name_tempo_triggered_and_clip_count(inst):
    reply = run(inst, "get_scenes")
    assert reply["status"] == "success"
    assert reply["result"]["scene_count"] == 3
    assert reply["result"]["scenes"] == [
        {"index": 0, "name": "Intro", "tempo": -1.0, "is_triggered": False, "clip_count": 0},
        {"index": 1, "name": "Verse", "tempo": 128.0, "is_triggered": False, "clip_count": 2},
        {"index": 2, "name": "Chorus", "tempo": -1.0, "is_triggered": False, "clip_count": 1},
    ]


@pytest.mark.parametrize("raw", [0, 0.0, -1, None])
def test_a_scene_tempo_of_zero_or_less_is_reported_as_minus_one(inst, song, raw):
    song.scenes[0].tempo = raw
    assert run(inst, "get_scenes")["result"]["scenes"][0]["tempo"] == -1.0


def test_get_scenes_does_not_touch_live(inst, song):
    run(inst, "get_scenes")
    assert song.calls == []
    assert inst.scheduled == []  # a read: not scheduled on the main thread


# ------------------------------------------------------------- create_scene

def test_create_scene_appends_by_default_and_names_it(inst, song):
    reply = run(inst, "create_scene", name="Outro")
    assert reply["status"] == "success"
    assert reply["result"]["created_index"] == 3
    assert names(song) == ["Intro", "Verse", "Chorus", "Outro"]
    assert reply["result"]["scene_count"] == 4
    assert listed(reply)[-1] == (3, "Outro")


def test_create_scene_in_the_middle_shifts_later_scenes(inst, song):
    reply = run(inst, "create_scene", index=1, name="Pre")
    assert reply["result"]["created_index"] == 1
    assert listed(reply) == [(0, "Intro"), (1, "Pre"), (2, "Verse"), (3, "Chorus")]
    # clip counts follow their scenes
    assert [s["clip_count"] for s in reply["result"]["scenes"]] == [0, 0, 2, 1]


def test_create_scene_index_len_appends(inst, song):
    assert run(inst, "create_scene", index=3)["result"]["created_index"] == 3


def test_create_scene_without_a_name_keeps_the_default(inst, song):
    run(inst, "create_scene", index=0)
    assert song.scenes[0].name == ""


@pytest.mark.parametrize("bad", [-2, 4, 99])
def test_create_scene_out_of_range(inst, song, bad):
    reply = run(inst, "create_scene", index=bad)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]
    assert song.calls == []


@pytest.mark.parametrize("bad", ["1", 1.0, True])
def test_create_scene_index_must_be_an_integer(inst, song, bad):
    reply = run(inst, "create_scene", index=bad)
    assert reply["status"] == "error" and "integer" in reply["message"]
    assert song.calls == []


def test_create_scene_name_must_be_a_string(inst, song):
    reply = run(inst, "create_scene", name=5)
    assert reply["status"] == "error" and "string" in reply["message"]
    assert song.calls == []


@pytest.mark.parametrize("limit_raises", [True, False])
def test_live_lite_refusing_an_extra_scene_is_a_readable_error(
        script_module, limit_raises):
    song = FakeSong(limit=3, limit_raises=limit_raises)
    reply = run(make_inst(script_module, song), "create_scene")
    assert reply["status"] == "error"
    assert "Live did not create a scene" in reply["message"]
    assert "Live Lite" in reply["message"]
    assert "Traceback" not in reply["message"]
    assert len(song.scenes) == 3


# --------------------------------------------------------- duplicate_scene

def test_duplicate_scene_inserts_the_copy_after_the_original(inst, song):
    reply = run(inst, "duplicate_scene", scene_index=1)
    assert reply["status"] == "success"
    assert reply["result"]["source_index"] == 1
    assert reply["result"]["new_index"] == 2
    assert listed(reply) == [(0, "Intro"), (1, "Verse"), (2, "Verse"), (3, "Chorus")]
    assert reply["result"]["scenes"][2]["clip_count"] == 2


@pytest.mark.parametrize("limit_raises", [True, False])
def test_duplicate_scene_refused_by_live_lite(script_module, limit_raises):
    song = FakeSong(limit=3, limit_raises=limit_raises)
    reply = run(make_inst(script_module, song), "duplicate_scene", scene_index=0)
    assert reply["status"] == "error"
    assert "Live did not duplicate the scene" in reply["message"]
    assert len(song.scenes) == 3


@pytest.mark.parametrize("command", ["duplicate_scene", "fire_scene"])
@pytest.mark.parametrize("bad", [-1, 3, 50])
def test_scene_index_out_of_range(inst, song, command, bad):
    reply = run(inst, command, scene_index=bad)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]
    assert song.calls == []
    assert all(s.fired == 0 for s in song.scenes)


@pytest.mark.parametrize("command", ["duplicate_scene", "fire_scene", "set_scene_name"])
@pytest.mark.parametrize("bad", ["0", 1.0, None, True])
def test_scene_index_must_be_an_integer(inst, song, command, bad):
    params = {"scene_index": bad}
    if command == "set_scene_name":
        params["name"] = "x"
    reply = run(inst, command, **params)
    assert reply["status"] == "error" and "integer" in reply["message"]
    assert song.calls == []


def test_a_missing_scene_index_never_defaults_to_scene_zero(inst, song):
    for command in ("fire_scene", "duplicate_scene"):
        assert run(inst, command)["status"] == "error"
    assert song.scenes[0].fired == 0
    assert song.calls == []


# --------------------------------------------------------------- fire_scene

def test_fire_scene_fires_only_that_scene(inst, song):
    reply = run(inst, "fire_scene", scene_index=1)
    assert reply["status"] == "success"
    assert reply["result"]["fired"] is True
    assert reply["result"]["name"] == "Verse"
    assert reply["result"]["clip_count"] == 2
    assert [s.fired for s in song.scenes] == [0, 1, 0]
    assert reply["result"]["scenes"][1]["is_triggered"] is True


# ----------------------------------------------------------- set_scene_name

def test_set_scene_name_renames_and_reports_the_previous_name(inst, song):
    reply = run(inst, "set_scene_name", scene_index=2, name="Drop")
    assert reply["status"] == "success"
    assert reply["result"]["previous_name"] == "Chorus"
    assert reply["result"]["name"] == "Drop"
    assert names(song) == ["Intro", "Verse", "Drop"]


def test_set_scene_name_can_clear_a_name(inst, song):
    run(inst, "set_scene_name", scene_index=0, name="")
    assert song.scenes[0].name == ""


@pytest.mark.parametrize("bad", [None, 3, ["x"]])
def test_set_scene_name_requires_a_string(inst, song, bad):
    reply = run(inst, "set_scene_name", scene_index=0, name=bad)
    assert reply["status"] == "error" and "string" in reply["message"]
    assert names(song) == ["Intro", "Verse", "Chorus"]


def test_set_scene_name_out_of_range(inst):
    reply = run(inst, "set_scene_name", scene_index=9, name="x")
    assert reply["status"] == "error" and "out of range" in reply["message"]


# ----------------------------------------------------------- stop_all_clips

def test_stop_all_clips_calls_live_once(inst, song):
    reply = run(inst, "stop_all_clips")
    assert reply["status"] == "success"
    assert reply["result"] == {"stop_requested": True}
    assert song.calls == [("stop_all_clips",)]


# ------------------------------------------------------------ delete_scene

def test_preview_reports_the_facts_and_deletes_nothing(inst, song):
    reply = run(inst, "delete_scene", scene_index=1, expected_name="Verse", dry_run=True)
    assert reply["status"] == "success"
    info = reply["result"]
    assert info["name"] == "Verse" and info["tempo"] == 128.0
    assert info["clip_count"] == 2
    assert info["clips"] == [{"track": "Track 1", "clip": "Verse Keys"},
                             {"track": "Track 2", "clip": "Verse Drums"}]
    assert info["deleted"] is False and info["dry_run"] is True
    assert [(r["index"], r["name"]) for r in info["remaining"]] == [(0, "Intro"), (1, "Chorus")]
    assert song.calls == []
    assert len(song.scenes) == 3


def test_dry_run_is_the_default_when_the_flag_is_missing(inst, song):
    reply = run(inst, "delete_scene", scene_index=0, expected_name="Intro")
    assert reply["result"]["dry_run"] is True
    assert song.calls == []


def test_delete_with_matching_name_removes_the_scene_and_returns_the_new_list(inst, song):
    reply = run(inst, "delete_scene", scene_index=1, expected_name="Verse", dry_run=False)
    assert reply["status"] == "success"
    assert reply["result"]["deleted"] is True
    assert names(song) == ["Intro", "Chorus"]
    assert [(r["index"], r["name"]) for r in reply["result"]["remaining"]] == [
        (0, "Intro"), (1, "Chorus")]
    assert song.calls == [("delete_scene", 1)]


def test_delete_requires_expected_name(inst, song):
    reply = run(inst, "delete_scene", scene_index=0, dry_run=False)
    assert reply["status"] == "error"
    assert "expected_name is required" in reply["message"]
    assert song.calls == []


def test_an_empty_expected_name_matches_an_unnamed_scene(script_module):
    song = FakeSong(scene_names=("A", "", "C"))
    inst = make_inst(script_module, song)
    reply = run(inst, "delete_scene", scene_index=1, expected_name="", dry_run=False)
    assert reply["status"] == "success"
    assert names(song) == ["A", "C"]


def test_an_empty_expected_name_does_not_match_a_named_scene(inst, song):
    reply = run(inst, "delete_scene", scene_index=0, expected_name="", dry_run=False)
    assert reply["status"] == "error" and "indices may have shifted" in reply["message"]
    assert song.calls == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_name_mismatch_deletes_nothing_even_in_preview(inst, song, dry_run):
    reply = run(inst, "delete_scene", scene_index=0, expected_name="Verse", dry_run=dry_run)
    assert reply["status"] == "error"
    assert "indices may have shifted" in reply["message"]
    assert "Nothing was deleted" in reply["message"]
    assert song.calls == []


def test_a_stale_index_after_a_delete_is_caught(inst, song):
    """The realistic failure: delete 0, then reuse the old index of 'Verse'."""
    run(inst, "delete_scene", scene_index=0, expected_name="Intro", dry_run=False)
    reply = run(inst, "delete_scene", scene_index=1, expected_name="Verse", dry_run=False)
    assert reply["status"] == "error"
    assert names(song) == ["Verse", "Chorus"]


def test_last_remaining_scene_is_refused(script_module):
    song = FakeSong(scene_names=("Only",))
    reply = run(make_inst(script_module, song), "delete_scene", scene_index=0,
                expected_name="Only", dry_run=False)
    assert reply["status"] == "error" and "last remaining scene" in reply["message"]
    assert song.calls == []


@pytest.mark.parametrize("bad", [-1, 3, 50])
def test_delete_out_of_range(inst, song, bad):
    reply = run(inst, "delete_scene", scene_index=bad, expected_name="x", dry_run=False)
    assert reply["status"] == "error" and "out of range" in reply["message"]
    assert song.calls == []


@pytest.mark.parametrize("bad", ["0", 1.0, None, True])
def test_delete_index_must_be_an_integer(inst, song, bad):
    reply = run(inst, "delete_scene", scene_index=bad, expected_name="x", dry_run=False)
    assert reply["status"] == "error" and "integer" in reply["message"]
    assert song.calls == []


def test_a_delete_that_live_does_not_perform_is_reported_as_an_error(inst, song):
    song.silently_ignore_delete = True
    reply = run(inst, "delete_scene", scene_index=0, expected_name="Intro", dry_run=False)
    assert reply["status"] == "error" and "did not delete" in reply["message"]


# --------------------------------------------- scheduling / handshake / docs

@pytest.mark.parametrize("command,params", [
    ("create_scene", {}),
    ("duplicate_scene", {"scene_index": 0}),
    ("fire_scene", {"scene_index": 0}),
    ("set_scene_name", {"scene_index": 0, "name": "x"}),
    ("stop_all_clips", {}),
    ("delete_scene", {"scene_index": 0, "expected_name": "Intro"}),
])
def test_modifying_commands_are_scheduled_on_the_main_thread(inst, command, params):
    run(inst, command, **params)
    assert inst.scheduled == [(0, "main_thread_task")]


def test_capabilities_are_advertised_at_the_end_and_version_is_untouched(script_module):
    caps = script_module.SCRIPT_CAPABILITIES
    assert set(SCENE_COMMANDS) <= set(caps)
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    first = min(caps.index(c) for c in SCENE_COMMANDS)
    assert set(caps[first:]) == set(SCENE_COMMANDS)


def test_bundled_copy_is_identical_to_the_source():
    assert BUNDLED_SCRIPT.read_bytes() == SOURCE_SCRIPT.read_bytes()


def test_tools_are_registered_and_modifying_ones_are_in_the_dataset_set():
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert set(SCENE_COMMANDS) <= tools
    for name in SCENE_COMMANDS:
        if name != "get_scenes":
            assert name in MODIFYING_TOOLS
    assert "get_scenes" not in MODIFYING_TOOLS


@pytest.mark.parametrize("name", SCENE_COMMANDS)
def test_every_tool_keeps_user_prompt(name):
    assert "user_prompt" in inspect.signature(getattr(server, name)).parameters


def test_audible_tools_say_so_in_their_docstrings():
    assert "AUDIBLE" in server.fire_scene.__doc__
    assert "Arrangement" in server.fire_scene.__doc__
    assert "Back to Arrangement" in server.fire_scene.__doc__
    assert "Audible" in server.stop_all_clips.__doc__


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


@pytest.mark.parametrize("name", [c for c in SCENE_COMMANDS if c != "get_scenes"])
def test_server_treats_scene_changes_as_modifying(name):
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command(name, {})
    assert conn.sock.timeouts[0] == 15.0


# ------------------------------------------------------------- server tools

class FakeConnection(object):
    def __init__(self, response=None, raise_exc=None):
        self.response = response if response is not None else {}
        self.raise_exc = raise_exc
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, params or {}))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


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


def test_get_scenes_tool_returns_the_json(conn):
    conn.response = {"scene_count": 1, "scenes": [{"index": 0, "name": "A"}]}
    out = json.loads(call(server.get_scenes, None))
    assert conn.sent == [("get_scenes", {})]
    assert out["scenes"][0]["name"] == "A"


def test_create_scene_tool_forwards_index_and_name(conn):
    call(server.create_scene, None, 2, "Bridge")
    call(server.create_scene, None)
    assert conn.sent == [("create_scene", {"index": 2, "name": "Bridge"}),
                         ("create_scene", {"index": -1})]


def test_simple_tools_forward_their_params(conn):
    call(server.duplicate_scene, None, 1)
    call(server.fire_scene, None, 2)
    call(server.set_scene_name, None, 0, "Hi")
    call(server.stop_all_clips, None)
    assert conn.sent == [
        ("duplicate_scene", {"scene_index": 1}),
        ("fire_scene", {"scene_index": 2}),
        ("set_scene_name", {"scene_index": 0, "name": "Hi"}),
        ("stop_all_clips", {}),
    ]


def test_delete_scene_tool_previews_by_default(conn):
    conn.response = {"name": "Verse", "deleted": False}
    out = call(server.delete_scene, None, 1, "Verse")
    assert conn.sent == [("delete_scene", {
        "scene_index": 1, "expected_name": "Verse", "dry_run": True})]
    assert out.startswith("NOT DELETED (preview only)")
    assert "confirm=true" in out


def test_delete_scene_tool_deletes_only_with_confirm(conn):
    conn.response = {"name": "Verse", "deleted": True}
    out = call(server.delete_scene, None, 1, "Verse", confirm=True)
    assert conn.sent == [("delete_scene", {
        "scene_index": 1, "expected_name": "Verse", "dry_run": False})]
    assert out.startswith("Deleted scene.")


def test_delete_scene_tool_accepts_an_empty_name_but_not_none(conn):
    call(server.delete_scene, None, 0, "")
    assert conn.sent[0][1]["expected_name"] == ""
    conn.sent.clear()
    out = call(server.delete_scene, None, 0, None, confirm=True)
    assert "expected_name is required" in out
    assert conn.sent == []


def test_tool_errors_come_back_as_text_not_exceptions(conn):
    conn.raise_exc = RuntimeError("Live did not create a scene (the set has 8 scenes)")
    out = call(server.create_scene, None)
    assert out.startswith("Error creating scene:")
    assert "Live did not create a scene" in out


def test_missing_capability_message_is_returned(monkeypatch, conn):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "Remote Script too old")
    assert call(server.fire_scene, None, 0) == "Remote Script too old"
    assert conn.sent == []
