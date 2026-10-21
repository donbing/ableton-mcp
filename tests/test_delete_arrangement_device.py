"""Tests for the guarded delete_arrangement_clips and delete_device.

The Remote Script runs against a mocked Live Object Model (``_Framework``
stubbed, no socket, no Ableton). The fakes keep the properties that make these
deletes dangerous: Track.delete_device shifts later indices, and Arrangement
clips are removed by object, not by index. Nothing here has run on a real Live.
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
        "ableton_mcp_script_delete_arr_dev", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


# --------------------------------------------------------------------- fakes

class FakeClip(object):
    def __init__(self, name, start, length):
        self.name = name
        self.start_time = float(start)
        self.length = float(length)
        self.end_time = float(start) + float(length)


class FakeDevice(object):
    def __init__(self, name):
        self.name = name
        self.class_name = "Fake" + name.replace(" ", "")


class FakeTrack(object):
    def __init__(self, name, devices=(), clips=(), foldable=False,
                 can_delete_clip=True, can_delete_device=True,
                 noop_delete_clip=False, noop_delete_device=False):
        self.name = name
        self.is_foldable = foldable
        self.devices = [FakeDevice(d) for d in devices]
        self.arrangement_clips = list(clips)
        self.clip_delete_calls = []
        self.device_delete_calls = []
        self._noop_clip = noop_delete_clip
        self._noop_device = noop_delete_device
        if not can_delete_clip:
            self.delete_clip = None
        if not can_delete_device:
            self.delete_device = None

    def delete_clip(self, clip):
        self.clip_delete_calls.append(clip)
        if not self._noop_clip:
            self.arrangement_clips = [c for c in self.arrangement_clips if c is not clip]

    def delete_device(self, index):
        self.device_delete_calls.append(index)
        if not self._noop_device:
            self.devices.pop(index)


class FakeSong(object):
    def __init__(self, tracks, returns=()):
        self.tracks = list(tracks)
        self.return_tracks = list(returns)
        self.master_track = FakeTrack("Master", devices=["Limiter"])


def make_clips():
    # contiguous 4-beat clips at 0, 4, 8, 12
    return [FakeClip("A", 0, 4), FakeClip("B", 4, 4), FakeClip("C", 8, 4),
            FakeClip("D", 12, 4)]


def make_song():
    return FakeSong(
        [FakeTrack("1-Drums", devices=["Drum Rack", "Compressor", "EQ Eight"],
                   clips=make_clips()),
         FakeTrack("2-Bass", devices=["Operator"]),
         FakeTrack("Group", foldable=True)],
        returns=[FakeTrack("A Reverb", devices=["Reverb", "Utility"]),
                 FakeTrack("B Delay", devices=["Echo"])])


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
    return make_song()


@pytest.fixture
def inst(script_module, song):
    return make_inst(script_module, song)


def run_clips(inst, **params):
    return inst._process_command({"type": "delete_arrangement_clips", "params": params})


def run_dev(inst, **params):
    return inst._process_command({"type": "delete_device", "params": params})


def clip_names(track):
    return [c.name for c in track.arrangement_clips]


def dev_names(track):
    return [d.name for d in track.devices]


# ======================================================= delete_arrangement_clips

def test_range_rule_is_start_inclusive_end_exclusive(inst, song):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=4.0, end_time=12.0)
    info = reply["result"]
    # B starts at 4 (in), C at 8 (in), D at 12 (out: end exclusive)
    assert [c["name"] for c in info["clips"]] == ["B", "C"]
    assert info["match_count"] == 2


def test_a_clip_overlapping_the_range_but_starting_before_it_is_not_selected(inst):
    info = run_clips(inst, track_index=0, expected_name="1-Drums",
                     start_time=5.0, end_time=9.0)["result"]
    # B (4..8) overlaps [5, 9) but starts at 4; only C starts inside
    assert [c["name"] for c in info["clips"]] == ["C"]


def test_preview_is_the_default_and_deletes_nothing(inst, song):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=0.0, end_time=8.0)
    info = reply["result"]
    assert reply["status"] == "success"
    assert info["deleted"] is False and info["dry_run"] is True
    assert [c["name"] for c in info["remaining"]] == ["C", "D"]
    assert song.tracks[0].clip_delete_calls == []
    assert clip_names(song.tracks[0]) == ["A", "B", "C", "D"]


def test_confirm_none_is_a_preview(inst, song):
    run_clips(inst, track_index=0, expected_name="1-Drums",
              start_time=0.0, end_time=8.0, confirm=None)
    assert song.tracks[0].clip_delete_calls == []


def test_confirm_with_matching_name_deletes_and_returns_the_remaining_clips(inst, song):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=4.0, end_time=12.0, confirm=True)
    assert reply["status"] == "success", reply
    info = reply["result"]
    assert info["deleted"] is True and info["deleted_count"] == 2
    assert clip_names(song.tracks[0]) == ["A", "D"]
    assert [(c["index"], c["name"]) for c in info["remaining"]] == [(0, "A"), (1, "D")]
    assert [c["name"] for c in info["clips"]] == ["B", "C"]


def test_zero_matches_deletes_nothing_and_is_not_an_error(inst, song):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=100.0, end_time=200.0, confirm=True)
    assert reply["status"] == "success"
    assert reply["result"]["match_count"] == 0
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("confirm", ["true", "false", 1, 0, "yes"])
def test_a_non_boolean_confirm_is_refused(inst, song, confirm):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=0.0, end_time=8.0, confirm=confirm)
    assert reply["status"] == "error"
    assert "confirm" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("confirm", [False, True])
def test_expected_name_is_required(inst, song, confirm):
    reply = run_clips(inst, track_index=0, start_time=0.0, end_time=8.0,
                      confirm=confirm)
    assert reply["status"] == "error"
    assert "expected_name is required" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("confirm", [False, True])
def test_name_mismatch_deletes_nothing(inst, song, confirm):
    reply = run_clips(inst, track_index=0, expected_name="2-Bass",
                      start_time=0.0, end_time=8.0, confirm=confirm)
    assert reply["status"] == "error"
    assert "indices may have shifted" in reply["message"]
    assert "Nothing was deleted" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("start,end", [(8.0, 8.0), (8.0, 4.0)])
def test_start_must_be_less_than_end(inst, song, start, end):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=start, end_time=end, confirm=True)
    assert reply["status"] == "error"
    assert "less than end_time" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("start,end", [
    (None, 8.0), (0.0, None), ("0", 8.0), (0.0, "8"), (True, 8.0),
    (float("nan"), 8.0), (0.0, float("inf")), (float("-inf"), 8.0),
])
def test_times_must_be_finite_numbers(inst, song, start, end):
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=start, end_time=end, confirm=True)
    assert reply["status"] == "error"
    assert song.tracks[0].clip_delete_calls == []


@pytest.mark.parametrize("index", [-1, 3, 50])
def test_out_of_range_track_index(inst, song, index):
    reply = run_clips(inst, track_index=index, expected_name="x",
                      start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]


@pytest.mark.parametrize("bad", ["0", 1.0, None, True])
def test_track_index_must_be_an_integer(inst, bad):
    reply = run_clips(inst, track_index=bad, expected_name="x",
                      start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"
    assert "integer" in reply["message"]


def test_group_track_is_refused(inst, song):
    reply = run_clips(inst, track_index=2, expected_name="Group",
                      start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"
    assert "group track" in reply["message"]


def test_more_than_64_matches_is_refused_even_in_preview(script_module):
    clips = [FakeClip("c%d" % i, i, 1) for i in range(65)]
    song = FakeSong([FakeTrack("Many", clips=clips)])
    inst = make_inst(script_module, song)
    for confirm in (False, True):
        reply = run_clips(inst, track_index=0, expected_name="Many",
                          start_time=0.0, end_time=1000.0, confirm=confirm)
        assert reply["status"] == "error"
        assert "refusing more than 64" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []
    # exactly 64 is allowed
    reply = run_clips(inst, track_index=0, expected_name="Many",
                      start_time=0.0, end_time=64.0, confirm=True)
    assert reply["status"] == "success"
    assert reply["result"]["deleted_count"] == 64
    assert clip_names(song.tracks[0]) == ["c64"]


def test_two_matching_clips_with_the_same_start_are_refused(script_module):
    song = FakeSong([FakeTrack("Dup", clips=[FakeClip("x", 4, 2), FakeClip("y", 4, 2)])])
    reply = run_clips(make_inst(script_module, song), track_index=0,
                      expected_name="Dup", start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"
    assert "ambiguous" in reply["message"]
    assert song.tracks[0].clip_delete_calls == []


def test_missing_track_delete_clip_is_a_clear_error_and_deletes_nothing(script_module):
    song = FakeSong([FakeTrack("Old", clips=make_clips(), can_delete_clip=False)])
    inst = make_inst(script_module, song)
    preview = run_clips(inst, track_index=0, expected_name="Old",
                        start_time=0.0, end_time=8.0)
    assert preview["result"]["delete_supported"] is False
    reply = run_clips(inst, track_index=0, expected_name="Old",
                      start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"
    assert "Track.delete_clip is not available" in reply["message"]
    assert clip_names(song.tracks[0]) == ["A", "B", "C", "D"]


def test_a_delete_that_live_does_not_perform_is_reported_as_an_error(script_module):
    song = FakeSong([FakeTrack("Stuck", clips=make_clips(), noop_delete_clip=True)])
    reply = run_clips(make_inst(script_module, song), track_index=0,
                      expected_name="Stuck", start_time=0.0, end_time=8.0,
                      confirm=True)
    assert reply["status"] == "error"
    assert "did not delete" in reply["message"]


def test_a_stale_track_index_after_a_track_is_removed_is_caught(inst, song):
    song.tracks.pop(0)  # tracks shifted: index 0 is now 2-Bass
    reply = run_clips(inst, track_index=0, expected_name="1-Drums",
                      start_time=0.0, end_time=8.0, confirm=True)
    assert reply["status"] == "error"


# ================================================================= delete_device

def test_device_preview_shows_the_chain_and_deletes_nothing(inst, song):
    reply = run_dev(inst, track_index=0, device_index=1,
                    expected_name="1-Drums", expected_device_name="Compressor")
    info = reply["result"]
    assert reply["status"] == "success"
    assert info["deleted"] is False and info["dry_run"] is True
    assert info["device_name"] == "Compressor"
    assert [(d["index"], d["name"], d["to_delete"]) for d in info["chain"]] == [
        (0, "Drum Rack", False), (1, "Compressor", True), (2, "EQ Eight", False)]
    assert song.tracks[0].device_delete_calls == []


def test_device_delete_removes_it_and_returns_the_reindexed_chain(inst, song):
    reply = run_dev(inst, track_index=0, device_index=1, expected_name="1-Drums",
                    expected_device_name="Compressor", confirm=True)
    assert reply["status"] == "success", reply
    info = reply["result"]
    assert info["deleted"] is True
    assert dev_names(song.tracks[0]) == ["Drum Rack", "EQ Eight"]
    assert [(d["index"], d["name"]) for d in info["chain"]] == [
        (0, "Drum Rack"), (1, "EQ Eight")]
    assert song.tracks[0].device_delete_calls == [1]


def test_device_delete_on_a_return_track(inst, song):
    reply = run_dev(inst, track_index=0, device_index=0, expected_name="A Reverb",
                    expected_device_name="Reverb", track_type="return", confirm=True)
    assert reply["status"] == "success", reply
    assert dev_names(song.return_tracks[0]) == ["Utility"]
    assert dev_names(song.tracks[0]) == ["Drum Rack", "Compressor", "EQ Eight"]


@pytest.mark.parametrize("confirm", ["true", 1, 0, "false"])
def test_device_non_boolean_confirm_is_refused(inst, song, confirm):
    reply = run_dev(inst, track_index=0, device_index=1, expected_name="1-Drums",
                    expected_device_name="Compressor", confirm=confirm)
    assert reply["status"] == "error"
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("missing", ["expected_name", "expected_device_name"])
@pytest.mark.parametrize("confirm", [False, True])
def test_both_names_are_required(inst, song, missing, confirm):
    params = dict(track_index=0, device_index=1, expected_name="1-Drums",
                  expected_device_name="Compressor", confirm=confirm)
    del params[missing]
    reply = run_dev(inst, **params)
    assert reply["status"] == "error"
    assert missing in reply["message"]
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("confirm", [False, True])
def test_track_name_mismatch_deletes_nothing(inst, song, confirm):
    reply = run_dev(inst, track_index=0, device_index=1, expected_name="2-Bass",
                    expected_device_name="Compressor", confirm=confirm)
    assert reply["status"] == "error"
    assert "indices may have shifted" in reply["message"]
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("confirm", [False, True])
def test_device_name_mismatch_deletes_nothing(inst, song, confirm):
    reply = run_dev(inst, track_index=0, device_index=1, expected_name="1-Drums",
                    expected_device_name="EQ Eight", confirm=confirm)
    assert reply["status"] == "error"
    assert "Nothing was deleted" in reply["message"]
    assert song.tracks[0].device_delete_calls == []


def test_a_stale_device_index_after_a_delete_is_caught(inst, song):
    run_dev(inst, track_index=0, device_index=0, expected_name="1-Drums",
            expected_device_name="Drum Rack", confirm=True)
    # the model still thinks EQ Eight is at 2; it is now at 1
    reply = run_dev(inst, track_index=0, device_index=2, expected_name="1-Drums",
                    expected_device_name="EQ Eight", confirm=True)
    assert reply["status"] == "error"
    assert dev_names(song.tracks[0]) == ["Compressor", "EQ Eight"]


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_device_index_out_of_range(inst, song, index):
    reply = run_dev(inst, track_index=0, device_index=index, expected_name="1-Drums",
                    expected_device_name="Compressor", confirm=True)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("bad", ["1", 1.0, None, True])
def test_device_index_must_be_an_integer(inst, song, bad):
    reply = run_dev(inst, track_index=0, device_index=bad, expected_name="1-Drums",
                    expected_device_name="Compressor", confirm=True)
    assert reply["status"] == "error"
    assert "integer" in reply["message"]
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("bad", ["0", 1.0, None, True, -1, 9])
def test_device_track_index_is_validated(inst, song, bad):
    reply = run_dev(inst, track_index=bad, device_index=0, expected_name="1-Drums",
                    expected_device_name="Drum Rack", confirm=True)
    assert reply["status"] == "error"
    assert song.tracks[0].device_delete_calls == []


@pytest.mark.parametrize("track_type", ["master", "MASTER", "bus", ""])
def test_master_and_unknown_track_types_are_refused(inst, song, track_type):
    reply = run_dev(inst, track_index=0, device_index=0, expected_name="Master",
                    expected_device_name="Limiter", track_type=track_type,
                    confirm=True)
    # "" falls back to 'track', where track 0 is '1-Drums' (name mismatch)
    assert reply["status"] == "error"
    assert dev_names(song.master_track) == ["Limiter"]
    assert song.tracks[0].device_delete_calls == []


def test_missing_track_delete_device_is_a_clear_error(script_module):
    song = FakeSong([FakeTrack("Old", devices=["A"], can_delete_device=False)])
    reply = run_dev(make_inst(script_module, song), track_index=0, device_index=0,
                    expected_name="Old", expected_device_name="A", confirm=True)
    assert reply["status"] == "error"
    assert "Track.delete_device is not available" in reply["message"]
    assert dev_names(song.tracks[0]) == ["A"]


def test_a_device_delete_that_live_does_not_perform_is_an_error(script_module):
    song = FakeSong([FakeTrack("Stuck", devices=["A", "B"], noop_delete_device=True)])
    reply = run_dev(make_inst(script_module, song), track_index=0, device_index=0,
                    expected_name="Stuck", expected_device_name="A", confirm=True)
    assert reply["status"] == "error"
    assert "did not delete" in reply["message"]


# --------------------------------------------- scheduling / handshake / bundle

@pytest.mark.parametrize("command,params", [
    ("delete_arrangement_clips", dict(track_index=0, expected_name="1-Drums",
                                      start_time=0.0, end_time=8.0)),
    ("delete_device", dict(track_index=0, device_index=0, expected_name="1-Drums",
                           expected_device_name="Drum Rack")),
])
def test_commands_run_on_the_main_thread(inst, command, params):
    inst._process_command({"type": command, "params": params})
    assert inst.scheduled == [(0, "main_thread_task")]


def test_capabilities_are_advertised_after_the_older_ones(script_module):
    caps = script_module.SCRIPT_CAPABILITIES
    after = caps.index("undo_confirm_guard")
    for name in ("delete_arrangement_clips", "delete_device"):
        assert name in caps and caps.index(name) > after
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION


def test_bundled_copy_is_byte_identical():
    source = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"
    assert source.read_bytes() == BUNDLED_SCRIPT.read_bytes()


def test_tools_are_in_the_dataset_modifying_set():
    assert {"delete_arrangement_clips", "delete_device"} <= MODIFYING_TOOLS


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


@pytest.mark.parametrize("command", ["delete_arrangement_clips", "delete_device"])
def test_server_treats_the_commands_as_modifying(command):
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command(command, {"track_index": 0})
    assert conn.sock.timeouts[0] == 15.0


# ---------------------------------------------------------------- server tools

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


def test_clips_tool_defaults_to_preview(conn):
    conn.responses = [{"clips": [], "remaining": []}]
    out = call(server.delete_arrangement_clips, None, 0, "1-Drums", 0.0, 8.0)
    assert out.startswith("NOT DELETED (preview only)")
    assert "confirm=true" in out
    assert conn.sent == [("delete_arrangement_clips", {
        "track_index": 0, "expected_name": "1-Drums", "start_time": 0.0,
        "end_time": 8.0, "confirm": False})]


def test_clips_tool_with_confirm_sends_confirm_true(conn):
    conn.responses = [{"deleted": True, "remaining": []}]
    out = call(server.delete_arrangement_clips, None, 0, "1-Drums", 0.0, 8.0,
               confirm=True)
    assert out.startswith("Deleted arrangement clips.")
    assert conn.sent[0][1]["confirm"] is True


def test_clips_tool_refuses_without_a_name_or_with_a_bad_range(conn):
    assert call(server.delete_arrangement_clips, None, 0, "", 0.0, 8.0,
                confirm=True).startswith("Error")
    assert "less than end_time" in call(
        server.delete_arrangement_clips, None, 0, "x", 8.0, 8.0, confirm=True)
    assert conn.sent == []


def test_clips_tool_returns_connection_errors_as_text(conn):
    conn.raise_exc = RuntimeError("boom")
    out = call(server.delete_arrangement_clips, None, 0, "x", 0.0, 8.0, confirm=True)
    assert out.startswith("Error deleting arrangement clips") and "boom" in out


def test_device_tool_defaults_to_preview(conn):
    conn.responses = [{"chain": []}]
    out = call(server.delete_device, None, 0, 1, "1-Drums", "Compressor")
    assert out.startswith("NOT DELETED (preview only)")
    assert conn.sent == [("delete_device", {
        "track_index": 0, "device_index": 1, "expected_name": "1-Drums",
        "expected_device_name": "Compressor", "track_type": "track",
        "confirm": False})]


def test_device_tool_with_confirm_and_return_track(conn):
    conn.responses = [{"deleted": True, "chain": []}]
    out = call(server.delete_device, None, 0, 0, "A Reverb", "Reverb",
               confirm=True, track_type="return")
    assert out.startswith("Deleted device.")
    assert conn.sent[0][1]["confirm"] is True
    assert conn.sent[0][1]["track_type"] == "return"


def test_device_tool_requires_both_names(conn):
    assert call(server.delete_device, None, 0, 0, "", "X", confirm=True).startswith("Error")
    assert call(server.delete_device, None, 0, 0, "X", "", confirm=True).startswith("Error")
    assert conn.sent == []


@pytest.mark.parametrize("name,required", [
    ("delete_arrangement_clips",
     {"track_index", "expected_name", "start_time", "end_time"}),
    ("delete_device",
     {"track_index", "device_index", "expected_name", "expected_device_name"}),
])
def test_tool_schema_and_annotations(name, required):
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(t for t in tools if t.name == name)
    assert tool.annotations.destructiveHint is True
    schema = tool.inputSchema
    assert required <= set(schema["required"])
    assert "confirm" not in schema["required"]
    assert schema["properties"]["confirm"]["default"] is False
    assert "user_prompt" in schema["properties"]
