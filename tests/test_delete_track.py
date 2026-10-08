"""Tests for the guarded two-step delete_track.

Remote Script side runs against a mocked Live Object Model (``_Framework``
stubbed, no socket, no Ableton). The fake Song implements delete_track with
the index-shifting semantics that make deleting by a remembered index
dangerous, and has switches for the two group behaviours that cannot be
confirmed without a real Live set (deleting a group does or does not take its
members with it; Live does or does not drop a group once its last member is
gone). The tool must produce the right end state under every combination.
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
        "ableton_mcp_script_delete_track", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeDevice(object):
    def __init__(self, name):
        self.name = name


class FakeSlot(object):
    def __init__(self, has_clip):
        self.has_clip = has_clip


class FakeTrack(object):
    def __init__(self, name, midi=True, group=None, devices=(), clips=0,
                 arrangement=0, foldable=False):
        self.name = name
        self.has_midi_input = midi
        self.has_audio_input = not midi
        self.is_foldable = foldable
        self.group_track = group
        self.devices = [FakeDevice(d) for d in devices]
        self.clip_slots = [FakeSlot(i < clips) for i in range(4)]
        self.arrangement_clips = [object()] * arrangement
        self.can_be_armed = not foldable
        self.arm = False


class FakeSong(object):
    """tracks / return_tracks / master_track + delete_track with shifting."""

    def __init__(self, tracks, group_deletes_members=True,
                 drops_empty_group=False):
        self.tracks = list(tracks)
        self.return_tracks = [FakeTrack("A Reverb"), FakeTrack("B Delay")]
        self.master_track = FakeTrack("Master")
        self.group_deletes_members = group_deletes_members
        self.drops_empty_group = drops_empty_group
        self.delete_calls = []

    def delete_track(self, index):
        self.delete_calls.append(index)
        victim = self.tracks.pop(index)
        if victim.is_foldable and self.group_deletes_members:
            self.tracks = [t for t in self.tracks if t.group_track is not victim]
        if self.drops_empty_group and victim.group_track is not None:
            parent = victim.group_track
            if not any(t.group_track is parent for t in self.tracks):
                self.tracks = [t for t in self.tracks if t is not parent]


def basic_tracks():
    return [
        FakeTrack("1-Drums", devices=["Drum Rack", "Compressor"], clips=2, arrangement=3),
        FakeTrack("2-Bass", midi=False, devices=["Operator"]),
        FakeTrack("3-Keys"),
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
def song():
    return FakeSong(basic_tracks())


@pytest.fixture
def inst(script_module, song):
    return make_inst(script_module, song)


def run(inst, **params):
    return inst._process_command({"type": "delete_track", "params": params})


def names(song):
    return [t.name for t in song.tracks]


# ------------------------------------------------------------------ preview

def test_preview_reports_the_facts_and_deletes_nothing(inst, song):
    reply = run(inst, track_index=0, expected_name="1-Drums", dry_run=True)
    assert reply["status"] == "success"
    info = reply["result"]
    assert info["name"] == "1-Drums"
    assert info["type"] == "midi"
    assert info["devices"] == ["Drum Rack", "Compressor"]
    assert info["session_clip_count"] == 2
    assert info["arrangement_clip_count"] == 3
    assert info["group_members"] == []
    assert info["deleted"] is False and info["dry_run"] is True
    assert info["remaining"] == [{"index": 0, "name": "2-Bass"},
                                 {"index": 1, "name": "3-Keys"}]
    assert song.delete_calls == []
    assert len(song.tracks) == 3


def test_audio_track_type_in_preview(inst):
    info = run(inst, track_index=1, expected_name="2-Bass", dry_run=True)["result"]
    assert info["type"] == "audio"


def test_dry_run_is_the_default_when_the_flag_is_missing(inst, song):
    """A caller that omits dry_run must get a preview, never a deletion."""
    reply = run(inst, track_index=0, expected_name="1-Drums")
    assert reply["result"]["dry_run"] is True
    assert song.delete_calls == []


def test_preview_without_expected_name_is_allowed_but_still_deletes_nothing(inst, song):
    reply = run(inst, track_index=0, dry_run=True)
    assert reply["status"] == "success"
    assert song.delete_calls == []


# ------------------------------------------------------------------- delete

def test_delete_with_matching_name_removes_the_track_and_returns_the_new_list(inst, song):
    reply = run(inst, track_index=1, expected_name="2-Bass", dry_run=False)
    assert reply["status"] == "success"
    info = reply["result"]
    assert info["deleted"] is True
    assert names(song) == ["1-Drums", "3-Keys"]
    assert info["remaining"] == [{"index": 0, "name": "1-Drums"},
                                 {"index": 1, "name": "3-Keys"}]


def test_the_returned_list_shows_the_index_shift(inst, song):
    reply = run(inst, track_index=0, expected_name="1-Drums", dry_run=False)
    # 3-Keys was index 2 and is now index 1
    assert {"index": 1, "name": "3-Keys"} in reply["result"]["remaining"]
    assert song.tracks[1].name == "3-Keys"


def test_delete_requires_expected_name(inst, song):
    reply = run(inst, track_index=0, dry_run=False)
    assert reply["status"] == "error"
    assert "expected_name is required" in reply["message"]
    assert song.delete_calls == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_name_mismatch_deletes_nothing_even_in_preview(inst, song, dry_run):
    reply = run(inst, track_index=0, expected_name="2-Bass", dry_run=dry_run)
    assert reply["status"] == "error"
    assert "indices may have shifted" in reply["message"]
    assert "Nothing was deleted" in reply["message"]
    assert song.delete_calls == []


def test_a_stale_index_after_a_delete_is_caught(inst, song):
    """The realistic failure: the model deletes 0, then reuses its old index
    for the track that used to be at 1."""
    run(inst, track_index=0, expected_name="1-Drums", dry_run=False)
    reply = run(inst, track_index=1, expected_name="2-Bass", dry_run=False)
    assert reply["status"] == "error"
    assert names(song) == ["2-Bass", "3-Keys"]


# ----------------------------------------------------------------- refusals

@pytest.mark.parametrize("track_type", ["return", "master", "RETURN"])
def test_return_and_master_tracks_are_refused(inst, song, track_type):
    reply = run(inst, track_index=0, expected_name="A Reverb",
                track_type=track_type, dry_run=False)
    assert reply["status"] == "error"
    assert "cannot be deleted" in reply["message"]
    assert song.delete_calls == []
    assert len(song.return_tracks) == 2


def test_unknown_track_type_is_rejected(inst, song):
    reply = run(inst, track_index=0, expected_name="1-Drums", track_type="bus",
                dry_run=False)
    assert reply["status"] == "error"
    assert song.delete_calls == []


def test_last_remaining_track_is_refused(script_module):
    song = FakeSong([FakeTrack("Only")])
    reply = run(make_inst(script_module, song), track_index=0,
                expected_name="Only", dry_run=False)
    assert reply["status"] == "error"
    assert "last remaining track" in reply["message"]
    assert song.delete_calls == []


def test_deleting_a_group_that_holds_every_track_is_refused(script_module):
    group = FakeTrack("Group", foldable=True)
    song = FakeSong([group, FakeTrack("In1", group=group), FakeTrack("In2", group=group)])
    reply = run(make_inst(script_module, song), track_index=0,
                expected_name="Group", dry_run=False)
    assert reply["status"] == "error"
    assert "last remaining track" in reply["message"]
    assert len(song.tracks) == 3


@pytest.mark.parametrize("index", [-1, 3, 50])
def test_out_of_range_index(inst, song, index):
    reply = run(inst, track_index=index, expected_name="x", dry_run=False)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]
    assert song.delete_calls == []


@pytest.mark.parametrize("bad", ["0", 1.0, None, True])
def test_index_must_be_an_integer(inst, song, bad):
    reply = run(inst, track_index=bad, expected_name="x", dry_run=False)
    assert reply["status"] == "error"
    assert "integer" in reply["message"]
    assert song.delete_calls == []


# ------------------------------------------------------------------- groups

def group_song(script_module, **flags):
    group = FakeTrack("Group", foldable=True)
    tracks = [
        FakeTrack("Lead"),
        group,
        FakeTrack("In1", group=group),
        FakeTrack("In2", midi=False, group=group),
        FakeTrack("Outro"),
    ]
    song = FakeSong(tracks, **flags)
    return song, make_inst(script_module, song)


def test_group_preview_lists_the_members_that_would_go(script_module):
    song, inst = group_song(script_module)
    info = run(inst, track_index=1, expected_name="Group", dry_run=True)["result"]
    assert info["is_group"] is True and info["type"] == "group"
    assert info["group_members"] == ["In1", "In2"]
    assert info["remaining"] == [{"index": 0, "name": "Lead"},
                                 {"index": 1, "name": "Outro"}]
    assert len(song.tracks) == 5


@pytest.mark.parametrize("group_deletes_members", [True, False])
@pytest.mark.parametrize("drops_empty_group", [True, False])
def test_group_delete_ends_in_the_same_state_whatever_live_does(
        script_module, group_deletes_members, drops_empty_group):
    song, inst = group_song(script_module,
                            group_deletes_members=group_deletes_members,
                            drops_empty_group=drops_empty_group)
    reply = run(inst, track_index=1, expected_name="Group", dry_run=False)
    assert reply["status"] == "success", reply
    assert names(song) == ["Lead", "Outro"]
    assert reply["result"]["deleted"] is True
    assert reply["result"]["remaining"] == [{"index": 0, "name": "Lead"},
                                            {"index": 1, "name": "Outro"}]


def test_group_delete_never_deletes_a_neighbour_by_stale_index(script_module):
    """If Live drops the group after its last member, the group's old index
    now points at 'Outro'. Each victim is re-found by identity first."""
    song, inst = group_song(script_module, group_deletes_members=False,
                            drops_empty_group=True)
    run(inst, track_index=1, expected_name="Group", dry_run=False)
    assert "Outro" in names(song) and "Lead" in names(song)


def test_deleting_a_group_member_leaves_the_group_alone(script_module):
    song, inst = group_song(script_module, group_deletes_members=False)
    reply = run(inst, track_index=2, expected_name="In1", dry_run=False)
    assert reply["result"]["group_members"] == []
    assert names(song) == ["Lead", "Group", "In2", "Outro"]


def test_nested_group_members_are_found(script_module):
    outer = FakeTrack("Outer", foldable=True)
    inner = FakeTrack("Inner", foldable=True, group=outer)
    song = FakeSong([FakeTrack("Keep"), outer, inner,
                     FakeTrack("Deep", group=inner), FakeTrack("Shallow", group=outer)])
    inst = make_inst(script_module, song)
    info = run(inst, track_index=1, expected_name="Outer", dry_run=True)["result"]
    assert sorted(info["group_members"]) == ["Deep", "Inner", "Shallow"]
    run(inst, track_index=1, expected_name="Outer", dry_run=False)
    assert names(song) == ["Keep"]


def test_a_delete_that_live_does_not_perform_is_reported_as_an_error(
        script_module, inst, song):
    song.delete_track = lambda index: None  # Live silently refuses
    inst = make_inst(script_module, song)
    reply = run(inst, track_index=0, expected_name="1-Drums", dry_run=False)
    assert reply["status"] == "error"
    assert "did not delete" in reply["message"]


# --------------------------------------------- scheduling / handshake / docs

def test_command_is_scheduled_on_the_main_thread(inst):
    run(inst, track_index=0, expected_name="1-Drums", dry_run=True)
    run(inst, track_index=0, expected_name="1-Drums", dry_run=False)
    assert inst.scheduled == [(0, "main_thread_task"), (0, "main_thread_task")]


def test_version_capability_and_dispatch(script_module, inst):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    assert "delete_track" in script_module.SCRIPT_CAPABILITIES
    reply = run(inst, track_index=0, expected_name="1-Drums")
    assert not reply.get("message", "").startswith("Unknown command")


def test_tool_is_in_the_dataset_modifying_set():
    assert "delete_track" in MODIFYING_TOOLS


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


def test_server_treats_delete_track_as_modifying():
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command("delete_track", {"track_index": 0})
    assert conn.sock.timeouts[0] == 15.0


def test_tool_is_annotated_destructive():
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(t for t in tools if t.name == "delete_track")
    assert tool.annotations.destructiveHint is True
    assert tool.annotations.readOnlyHint in (None, False)


def test_tool_schema_requires_expected_name_and_defaults_confirm_false():
    tools = asyncio.run(server.mcp.list_tools())
    schema = next(t for t in tools if t.name == "delete_track").inputSchema
    assert "expected_name" in schema["required"]
    assert "track_index" in schema["required"]
    assert "confirm" not in schema["required"]
    assert schema["properties"]["confirm"]["default"] is False


# ------------------------------------------------------------- server tool

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


def test_tool_defaults_to_preview_and_sends_dry_run_true(conn):
    conn.responses = [{"name": "1-Drums", "remaining": []}]
    out = call(server.delete_track, None, 0, "1-Drums")
    assert out.startswith("NOT DELETED (preview only)")
    assert "confirm=true" in out
    assert conn.sent == [("delete_track", {
        "track_index": 0, "expected_name": "1-Drums", "track_type": "track",
        "dry_run": True})]


def test_tool_with_confirm_sends_dry_run_false_and_returns_the_list(conn):
    conn.responses = [{"deleted": True, "name": "1-Drums",
                       "remaining": [{"index": 0, "name": "2-Bass"}]}]
    out = call(server.delete_track, None, 0, "1-Drums", confirm=True)
    assert out.startswith("Deleted track.")
    assert '"2-Bass"' in out
    assert [c[1]["dry_run"] for c in conn.sent] == [False]
    assert conn.sent[0][1]["expected_name"] == "1-Drums"


def test_tool_refuses_an_empty_expected_name_without_talking_to_live(conn):
    out = call(server.delete_track, None, 0, "", confirm=True)
    assert out.startswith("Error deleting track: expected_name is required")
    assert conn.sent == []


def test_tool_reports_script_errors(conn):
    conn.raise_exc = Exception("Track 0 is 'A', not 'B'. Nothing was deleted.")
    out = call(server.delete_track, None, 0, "B", confirm=True)
    assert out.startswith("Error deleting track:")
    assert "Nothing was deleted" in out


def test_tool_returns_the_capability_message_for_an_old_script(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.delete_track, None, 0, "x", confirm=True) == "missing delete_track"
    assert conn.sent == []
