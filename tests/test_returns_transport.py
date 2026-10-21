"""Tests for return-track creation / device loading and the transport tools.

Ported and tightened from open upstream PR ahujasid/ableton-mcp#99
(Zachary May). The Remote Script side runs against a mocked Live Object
Model (``_Framework`` stubbed, no socket, no Ableton).
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
        "ableton_mcp_script_returns_transport", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeDevice(object):
    def __init__(self, name):
        self.name = name


class FakeTrack(object):
    def __init__(self, name, devices=()):
        self.name = name
        self.devices = [FakeDevice(d) for d in devices]


class FakeView(object):
    def __init__(self, selected):
        self.selected_track = selected


class FakeCue(object):
    def __init__(self, name, time):
        self.name = name
        self.time = time


class FakeSong(object):
    def __init__(self, returns=(), limit=None, raises_when_full=True):
        self.tracks = [FakeTrack("1-Drums"), FakeTrack("2-Bass")]
        self.return_tracks = list(returns)
        self.master_track = FakeTrack("Master")
        self.view = FakeView(self.tracks[0])
        self.limit = limit
        self.raises_when_full = raises_when_full
        self.create_calls = 0
        # transport
        self.signature_numerator = 4
        self.signature_denominator = 4
        self.metronome = False
        self.loop = False
        self.loop_start = 0.0
        self.loop_length = 4.0
        self.current_song_time = 0.0
        self.cue_points = []
        self.jumps = []

    def create_return_track(self):
        self.create_calls += 1
        if self.limit is not None and len(self.return_tracks) >= self.limit:
            if self.raises_when_full:
                raise Exception("Maximum number of return tracks reached")
            return
        self.return_tracks.append(FakeTrack(
            chr(ord("A") + len(self.return_tracks)) + "-Return"))

    def jump_to_next_cue(self):
        self.jumps.append("next")

    def jump_to_prev_cue(self):
        self.jumps.append("previous")


class FakeBrowser(object):
    """load_item adds the device to the selected track, but only becomes
    visible once the settle sleep has happened (when slow=True)."""

    def __init__(self, song, slow=False, adds_device=True, raises=None):
        self.song = song
        self.slow = slow
        self.adds_device = adds_device
        self.raises = raises
        self.pending = []
        self.loaded = []

    def load_item(self, item):
        if self.raises is not None:
            raise self.raises
        target = self.song.view.selected_track
        self.loaded.append((target, item.name))
        if not self.adds_device:
            return
        if self.slow:
            self.pending.append((target, FakeDevice(item.name)))
        else:
            target.devices.append(FakeDevice(item.name))

    def settle(self):
        for target, device in self.pending:
            target.devices.append(device)
        self.pending = []


class FakeItem(object):
    def __init__(self, name):
        self.name = name


def make_inst(script_module, song, browser=None, item=FakeItem("Reverb")):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []
    obj.browser = browser

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    obj.application = lambda: types.SimpleNamespace(browser=browser)
    obj._find_browser_item_by_uri = (
        lambda b, uri: item if uri.startswith("query:") else None)
    return obj


@pytest.fixture(autouse=True)
def no_settle_delay(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "LOAD_SETTLE_SECONDS", 0)


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


# ------------------------------------------------------ create_return_track

def test_create_return_track_returns_the_new_list(script_module):
    song = FakeSong(returns=[FakeTrack("A-Reverb", ["Reverb"])], limit=2)
    inst = make_inst(script_module, song)
    reply = run(inst, "create_return_track")
    assert reply["status"] == "success"
    result = reply["result"]
    assert result["created"] is True
    assert result["index"] == 1
    assert [r["name"] for r in result["return_tracks"]] == ["A-Reverb", "B-Return"]
    assert result["return_tracks"][0]["devices"] == ["Reverb"]
    assert len(song.return_tracks) == 2


def test_create_return_track_applies_the_name(script_module):
    song = FakeSong()
    inst = make_inst(script_module, song)
    result = run(inst, "create_return_track", name="Delay")["result"]
    assert result["name"] == "Delay"
    assert song.return_tracks[0].name == "Delay"
    assert "name_error" not in result


def test_a_failed_rename_keeps_the_track_and_is_reported(script_module):
    class Unrenamable(FakeTrack):
        def __init__(self):
            self.devices = []

        @property
        def name(self):
            return "A-Return"

        @name.setter
        def name(self, value):
            raise RuntimeError("read only")

    song = FakeSong()
    song.create_return_track = lambda: song.return_tracks.append(Unrenamable())
    inst = make_inst(script_module, song)
    result = run(inst, "create_return_track", name="Delay")["result"]
    assert result["created"] is True
    assert "read only" in result["name_error"]


@pytest.mark.parametrize("raises", [True, False])
def test_a_full_set_gives_a_readable_error_and_creates_nothing(script_module, raises):
    song = FakeSong(returns=[FakeTrack("A-Reverb"), FakeTrack("B-Delay")],
                    limit=2, raises_when_full=raises)
    inst = make_inst(script_module, song)
    reply = run(inst, "create_return_track")
    assert reply["status"] == "error"
    assert "No return track was created" in reply["message"]
    assert "Lite allows only 2" in reply["message"]
    assert "A-Reverb" in reply["message"]
    assert len(song.return_tracks) == 2


def test_create_return_track_rejects_a_non_string_name(script_module):
    song = FakeSong()
    reply = run(make_inst(script_module, song), "create_return_track", name=5)
    assert reply["status"] == "error"
    assert song.create_calls == 0


# ----------------------------------------------------- load_device_on_return

def loaded_inst(script_module, **browser_kwargs):
    song = FakeSong(returns=[FakeTrack("A-Reverb", ["Utility"]), FakeTrack("B-Delay")])
    browser = FakeBrowser(song, **browser_kwargs)
    return make_inst(script_module, song, browser), song, browser


def test_load_selects_the_return_loads_and_restores_the_selection(script_module):
    inst, song, browser = loaded_inst(script_module)
    original = song.view.selected_track
    reply = run(inst, "load_device_on_return", return_track_index=0, uri="query:Fx#Reverb")
    assert reply["status"] == "success"
    result = reply["result"]
    assert browser.loaded == [(song.return_tracks[0], "Reverb")]
    assert song.view.selected_track is original
    assert result["selection_restored"] is True
    assert result["devices_before"] == ["Utility"]
    assert result["devices_after"] == ["Utility", "Reverb"]
    assert result["loaded"] is True
    assert result["return_track_name"] == "A-Reverb"
    assert "warning" not in result


def test_the_device_list_is_read_after_the_settle(script_module, monkeypatch):
    inst, song, browser = loaded_inst(script_module, slow=True)
    monkeypatch.setattr(script_module.time, "sleep", lambda s: browser.settle())
    result = run(inst, "load_device_on_return", return_track_index=0,
                 uri="query:Fx#Reverb")["result"]
    assert result["devices_before"] == ["Utility"]
    assert result["devices_after"] == ["Utility", "Reverb"]
    assert result["loaded"] is True


def test_the_settle_runs_on_the_client_thread_not_inside_the_main_task(
        script_module, monkeypatch):
    inst, song, browser = loaded_inst(script_module)
    in_task = []
    monkeypatch.setattr(script_module.time, "sleep",
                        lambda s: in_task.append(list(inst.scheduled)))
    run(inst, "load_device_on_return", return_track_index=0, uri="query:Fx#Reverb")
    # the load task had finished before the sleep; the read is a second task
    assert in_task == [[(0, "main_thread_task")]]
    assert inst.scheduled == [(0, "main_thread_task"), (0, "task")]


def test_a_load_that_adds_no_device_is_not_reported_as_loaded(script_module):
    inst, song, browser = loaded_inst(script_module, adds_device=False)
    result = run(inst, "load_device_on_return", return_track_index=1,
                 uri="query:Fx#Reverb")["result"]
    assert result["loaded"] is False
    assert "did not grow" in result["warning"]
    assert result["devices_after"] == []


def test_selection_is_restored_even_when_the_load_fails(script_module):
    inst, song, browser = loaded_inst(script_module, raises=RuntimeError("cannot load"))
    original = song.view.selected_track
    reply = run(inst, "load_device_on_return", return_track_index=0, uri="query:Fx#Reverb")
    assert reply["status"] == "error"
    assert "cannot load" in reply["message"]
    assert song.view.selected_track is original


def test_unknown_uri_changes_nothing(script_module):
    inst, song, browser = loaded_inst(script_module)
    original = song.view.selected_track
    reply = run(inst, "load_device_on_return", return_track_index=0, uri="nope")
    assert reply["status"] == "error"
    assert "not found" in reply["message"]
    assert song.view.selected_track is original
    assert browser.loaded == []


@pytest.mark.parametrize("index", [-1, 2, True, "0", 1.0])
def test_bad_return_index_is_rejected(script_module, index):
    inst, song, browser = loaded_inst(script_module)
    reply = run(inst, "load_device_on_return", return_track_index=index,
                uri="query:Fx#Reverb")
    assert reply["status"] == "error"
    assert browser.loaded == []


def test_empty_uri_is_rejected(script_module):
    inst, song, browser = loaded_inst(script_module)
    reply = run(inst, "load_device_on_return", return_track_index=0, uri="")
    assert reply["status"] == "error"
    assert browser.loaded == []


def test_regular_tracks_are_never_the_target(script_module):
    inst, song, browser = loaded_inst(script_module)
    song.return_tracks = []
    reply = run(inst, "load_device_on_return", return_track_index=0, uri="query:Fx#Reverb")
    assert reply["status"] == "error"
    assert browser.loaded == []


# -------------------------------------------------- capabilities / tool layer

RETURN_COMMANDS = ("create_return_track", "load_device_on_return")


def test_commands_are_advertised_and_dispatched(script_module):
    for command in RETURN_COMMANDS:
        assert command in script_module.SCRIPT_CAPABILITIES
        reply = run(make_inst(script_module, FakeSong()), command)
        assert not reply.get("message", "").startswith("Unknown command")


def test_version_is_untouched(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION


def test_return_tools_are_registered_with_user_prompt():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in RETURN_COMMANDS:
        assert name in tools
        assert "user_prompt" in tools[name].inputSchema["properties"]
    assert set(RETURN_COMMANDS) <= MODIFYING_TOOLS
    assert "side effect" in tools["load_device_on_return"].description.lower()


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


def test_create_return_track_tool_sends_the_name(conn):
    conn.responses = [{"created": True, "index": 0, "name": "Delay", "return_tracks": []}]
    out = call(server.create_return_track, None, "Delay")
    assert conn.sent == [("create_return_track", {"name": "Delay"})]
    assert json.loads(out)["created"] is True


def test_load_device_on_return_tool_sends_uri_and_returns_the_list(conn):
    conn.responses = [{"loaded": True, "devices_after": ["Reverb"]}]
    out = call(server.load_device_on_return, None, 1, "query:Fx#Reverb")
    assert conn.sent == [("load_device_on_return",
                          {"return_track_index": 1, "uri": "query:Fx#Reverb"})]
    assert json.loads(out)["devices_after"] == ["Reverb"]


@pytest.mark.parametrize("tool,args", [
    ("create_return_track", (None,)),
    ("load_device_on_return", (None, 0, "query:x")),
])
def test_return_tools_report_script_errors(conn, tool, args):
    conn.raise_exc = Exception("boom")
    out = call(getattr(server, tool), *args)
    assert out.startswith("Error ") and "boom" in out


def test_return_tools_return_the_capability_message_for_an_old_script(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.create_return_track, None) == "missing create_return_track"
    assert call(server.load_device_on_return, None, 0, "query:x") == \
        "missing load_device_on_return"
    assert conn.sent == []
