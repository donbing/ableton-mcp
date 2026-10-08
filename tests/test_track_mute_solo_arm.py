"""Tests for set_track_mute / set_track_solo / set_track_arm.

Two layers, both runnable with no Ableton and no network:

* Remote Script side. ``_Framework`` is stubbed and the script class is
  instantiated without ``__init__`` (which would open a socket). The Live
  Object Model (song, tracks, return tracks, master) is replaced by small fakes
  that reproduce the LOM behaviours that matter here: reading or writing
  ``arm`` on a group, return or main track raises ``RuntimeError``, and the
  main track has no ``mute`` / ``solo`` at all.
* Server side. The real tool functions run with the socket connection faked.
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

COMMANDS = ("set_track_mute", "set_track_solo", "set_track_arm")


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
        "ableton_mcp_script_mute_solo_arm", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeTrack(object):
    """A LOM Track. ``kind`` is midi, audio, group, return or master."""

    def __init__(self, name, kind="midi"):
        self.name = name
        self.kind = kind
        self.can_be_armed = kind in ("midi", "audio")
        self.is_foldable = kind == "group"
        self._mute = False
        self._solo = False
        self._arm = False
        self.arm_refused = False  # simulate Live ignoring an arm request

    @property
    def mute(self):
        if self.kind == "master":
            raise AttributeError("master track has no mute")
        return self._mute

    @mute.setter
    def mute(self, value):
        if self.kind == "master":
            raise AttributeError("master track has no mute")
        self._mute = value

    @property
    def solo(self):
        if self.kind == "master":
            raise AttributeError("master track has no solo")
        return self._solo

    @solo.setter
    def solo(self, value):
        if self.kind == "master":
            raise AttributeError("master track has no solo")
        self._solo = value

    @property
    def arm(self):
        if not self.can_be_armed:
            raise RuntimeError("Master and Return Tracks have no 'Arm' state!")
        return self._arm

    @arm.setter
    def arm(self, value):
        if not self.can_be_armed:
            raise RuntimeError("Master and Return Tracks have no 'Arm' state!")
        if not self.arm_refused:
            self._arm = value


class FakeSong(object):
    def __init__(self):
        self.tracks = [
            FakeTrack("1-Drums", "midi"),
            FakeTrack("2-Bass", "audio"),
            FakeTrack("Group", "group"),
        ]
        self.return_tracks = [FakeTrack("A Reverb", "return"),
                              FakeTrack("B Delay", "return")]
        self.master_track = FakeTrack("Master", "master")


@pytest.fixture
def song():
    return FakeSong()


@pytest.fixture
def inst(script_module, song):
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


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


# -------------------------------------------------- remote script: success

def test_mute_regular_track_reports_previous_and_new(inst, song):
    reply = run(inst, "set_track_mute", track_index=0, enabled=True)
    assert reply["status"] == "success"
    assert reply["result"] == {
        "track_index": 0, "track_type": "track", "name": "1-Drums",
        "flag": "mute", "previous": False, "value": True, "changed": True,
    }
    assert song.tracks[0].mute is True


def test_unmute_is_idempotent_and_reports_unchanged(inst, song):
    reply = run(inst, "set_track_mute", track_index=1, enabled=False)
    assert reply["result"]["previous"] is False
    assert reply["result"]["value"] is False
    assert reply["result"]["changed"] is False


def test_solo_regular_track(inst, song):
    reply = run(inst, "set_track_solo", track_index=1, enabled=True)
    assert reply["result"]["flag"] == "solo"
    assert reply["result"]["value"] is True
    assert song.tracks[1].solo is True
    assert song.tracks[0].solo is False


def test_arm_midi_and_audio_tracks(inst, song):
    assert run(inst, "set_track_arm", track_index=0, enabled=True)["result"]["value"] is True
    assert run(inst, "set_track_arm", track_index=1, enabled=True)["result"]["value"] is True
    assert song.tracks[0].arm and song.tracks[1].arm
    back = run(inst, "set_track_arm", track_index=0, enabled=False)["result"]
    assert (back["previous"], back["value"]) == (True, False)


def test_arm_reports_the_value_read_back_from_live(inst, song):
    """If Live ignores the request the reply must say so, not echo the ask."""
    song.tracks[0].arm_refused = True
    result = run(inst, "set_track_arm", track_index=0, enabled=True)["result"]
    assert result["value"] is False
    assert result["changed"] is False


# ---------------------------------------- remote script: return/main/group

def test_mute_and_solo_work_on_return_tracks(inst, song):
    run(inst, "set_track_mute", track_index=1, enabled=True, track_type="return")
    run(inst, "set_track_solo", track_index=0, enabled=True, track_type="return")
    assert song.return_tracks[1].mute is True
    assert song.return_tracks[0].solo is True
    assert song.tracks[1].mute is False  # the regular track at that index is untouched


def test_mute_and_solo_work_on_group_tracks(inst, song):
    assert run(inst, "set_track_mute", track_index=2, enabled=True)["result"]["value"] is True
    assert run(inst, "set_track_solo", track_index=2, enabled=True)["result"]["value"] is True


@pytest.mark.parametrize("command", COMMANDS)
def test_master_track_is_refused_for_every_flag(inst, command):
    reply = run(inst, command, track_index=0, enabled=True, track_type="master")
    assert reply["status"] == "error"
    assert "master track has no" in reply["message"]


def test_arm_refused_on_group_track_without_touching_it(inst, song):
    reply = run(inst, "set_track_arm", track_index=2, enabled=True)
    assert reply["status"] == "error"
    assert "cannot be armed" in reply["message"]
    assert "Group" in reply["message"]


def test_arm_refused_on_return_track(inst):
    reply = run(inst, "set_track_arm", track_index=0, enabled=True, track_type="return")
    assert reply["status"] == "error"
    assert "cannot be armed" in reply["message"]


def test_arm_never_reads_arm_on_unarmable_tracks(inst, song):
    """Reading .arm on a group/return track raises RuntimeError in Live. The
    guard must check can_be_armed first so that error never surfaces."""
    reply = run(inst, "set_track_arm", track_index=2, enabled=False)
    assert "RuntimeError" not in reply["message"]
    assert "no 'Arm' state" not in reply["message"]


# --------------------------------------------------- remote script: guards

def test_expected_name_match_allows_the_change(inst, song):
    reply = run(inst, "set_track_mute", track_index=1, enabled=True,
                expected_name="2-Bass")
    assert reply["status"] == "success"
    assert song.tracks[1].mute is True


def test_expected_name_mismatch_changes_nothing(inst, song):
    reply = run(inst, "set_track_solo", track_index=1, enabled=True,
                expected_name="1-Drums")
    assert reply["status"] == "error"
    assert "indices may have shifted" in reply["message"]
    assert song.tracks[1].solo is False


def test_expected_name_is_checked_for_return_tracks_too(inst, song):
    reply = run(inst, "set_track_mute", track_index=0, enabled=True,
                track_type="return", expected_name="B Delay")
    assert reply["status"] == "error"
    assert song.return_tracks[0].mute is False


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_out_of_range_track_index_is_a_clear_error(inst, index):
    reply = run(inst, "set_track_mute", track_index=index, enabled=True)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]


def test_out_of_range_return_index(inst):
    reply = run(inst, "set_track_mute", track_index=2, enabled=True, track_type="return")
    assert reply["status"] == "error"
    assert "return index 2 out of range (have 2)" in reply["message"]


@pytest.mark.parametrize("bad", [None, "true", 1, 0.0])
def test_enabled_must_be_a_real_boolean(inst, song, bad):
    """bool("false") is True: a stringly-typed flag must not be coerced."""
    reply = run(inst, "set_track_mute", track_index=0, enabled=bad)
    assert reply["status"] == "error"
    assert "true or false" in reply["message"]
    assert song.tracks[0].mute is False


@pytest.mark.parametrize("bad", ["0", 1.5, True, None])
def test_track_index_must_be_an_integer(inst, bad):
    reply = run(inst, "set_track_mute", track_index=bad, enabled=True)
    assert reply["status"] == "error"
    assert "integer" in reply["message"]


def test_unknown_track_type_is_rejected(inst):
    reply = run(inst, "set_track_mute", track_index=0, enabled=True, track_type="bus")
    assert reply["status"] == "error"
    assert "Unknown track_type" in reply["message"]


# ------------------------------------------- remote script: thread scheduling

@pytest.mark.parametrize("command", COMMANDS)
def test_commands_are_scheduled_on_the_main_thread(inst, command):
    """Writes must go through schedule_message like every other modifier."""
    run(inst, command, track_index=0, enabled=True)
    assert inst.scheduled == [(0, "main_thread_task")]


def test_a_failing_task_is_reported_not_swallowed(inst, song):
    reply = run(inst, "set_track_mute", track_index=0, enabled=True,
                expected_name="wrong")
    assert reply["status"] == "error"
    assert inst.scheduled  # it did go through the scheduler


# ------------------------------------------------ handshake / bundle / docs

def test_version_and_capabilities_are_advertised(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    for command in COMMANDS:
        assert command in script_module.SCRIPT_CAPABILITIES


def test_advertised_commands_are_dispatched(inst):
    for command in COMMANDS:
        reply = run(inst, command, track_index=0, enabled=True)
        assert not reply.get("message", "").startswith("Unknown command")


def test_tools_are_in_the_dataset_modifying_set():
    assert set(COMMANDS) <= MODIFYING_TOOLS


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []
        self.sent = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        self.sent.append(json.loads(data.decode("utf-8")))

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


@pytest.mark.parametrize("command", COMMANDS)
def test_server_treats_the_commands_as_modifying(command):
    """Modifying commands get the longer socket budget (15 s vs 10 s)."""
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command(command, {"track_index": 0, "enabled": True})
    assert conn.sock.timeouts[0] == 15.0


def test_server_treats_a_read_as_non_modifying():
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command("get_track_info", {"track_index": 0})
    assert conn.sock.timeouts[0] == 10.0


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


def test_tool_forwards_params_and_returns_the_result_json(conn):
    conn.response = {"name": "1-Drums", "flag": "mute", "previous": False, "value": True}
    out = json.loads(call(server.set_track_mute, None, 0, True))
    assert conn.sent == [("set_track_mute", {
        "track_index": 0, "enabled": True, "track_type": "track"})]
    assert out["previous"] is False and out["value"] is True


def test_tool_forwards_expected_name_and_track_type(conn):
    call(server.set_track_solo, None, 1, True, track_type="return",
         expected_name="B Delay")
    assert conn.sent == [("set_track_solo", {
        "track_index": 1, "enabled": True, "track_type": "return",
        "expected_name": "B Delay"})]


def test_arm_tool_uses_the_arm_command(conn):
    call(server.set_track_arm, None, 2, False)
    assert conn.sent[0][0] == "set_track_arm"
    assert conn.sent[0][1]["enabled"] is False


def test_tool_reports_script_errors_as_text(conn):
    conn.raise_exc = Exception("Track 'Group' cannot be armed")
    out = call(server.set_track_arm, None, 2, True)
    assert out.startswith("Error setting track arm:")
    assert "cannot be armed" in out


def test_tool_returns_the_capability_message_for_an_old_script(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.set_track_mute, None, 0, True) == "missing set_track_mute"
    assert conn.sent == []
