"""Tests for the mixer tools from #122 (get_mixer, set_track_volume,
set_track_panning, set_send) and the fixes made on top of it.

Remote Script side runs against a mocked Live Object Model (no Ableton, no
socket). The mixer fakes mirror DeviceParameter: a non-linear fader taper
(0.85 = 0 dB, 1.0 = +6 dB, 0.0 = -inf), a pan parameter that displays "C",
"50L" and "25R", and sends. The main track has no sends.
"""

import asyncio
import importlib.util
import inspect
import json
import math
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

SETTERS = ("set_track_volume", "set_track_panning", "set_send")


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
        "ableton_mcp_script_mixer", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


def fader_db(v):
    if v <= 1e-4:  # Live shows -inf at the very bottom of the fader
        return float("-inf")
    if v >= 0.85:
        return 6.0 * (v - 0.85) / 0.15
    return 40.0 * math.log10(v / 0.85)


def fader_text(v):
    db = fader_db(v)
    return "-inf dB" if db == float("-inf") else "%.1f dB" % db


def pan_text(v):
    amount = int(round(abs(v) * 50))
    if amount == 0:
        return "C"
    return "%d%s" % (amount, "L" if v < 0 else "R")


class FakeParam(object):
    def __init__(self, name, value, minimum, maximum, text):
        self.name = name
        self.value = value
        self.min = minimum
        self.max = maximum
        self._text = text

    def str_for_value(self, value):
        return self._text(value)


def fader(name="Volume", value=0.85):
    return FakeParam(name, value, 0.0, 1.0, fader_text)


class FakeMixer(object):
    def __init__(self, sends=2, with_sends=True):
        self.volume = fader()
        self.panning = FakeParam("Pan", 0.0, -1.0, 1.0, pan_text)
        if with_sends:
            self.sends = [fader("Send " + "AB"[i], 0.0) for i in range(sends)]


class FakeTrack(object):
    def __init__(self, name, with_sends=True):
        self.name = name
        self.mixer_device = FakeMixer(with_sends=with_sends)


class FakeSong(object):
    def __init__(self):
        self.tracks = [FakeTrack("1-Drums"), FakeTrack("2-Bass")]
        self.return_tracks = [FakeTrack("A Reverb"), FakeTrack("B Delay")]
        self.master_track = FakeTrack("Master", with_sends=False)


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


# ------------------------------------------------------------------ get_mixer

def test_get_mixer_reports_value_display_and_db(inst):
    result = run(inst, "get_mixer", track_index=0)["result"]
    assert result["name"] == "1-Drums" and result["track_type"] == "track"
    assert result["volume"] == {"value": 0.85, "display": "0.0 dB", "db": 0.0}
    assert [s["name"] for s in result["sends"]] == ["Send A", "Send B"]
    assert [s["index"] for s in result["sends"]] == [0, 1]
    assert result["sends"][0]["display"] == "-inf dB"


def test_get_mixer_centre_pan(inst):
    pan = run(inst, "get_mixer", track_index=0)["result"]["panning"]
    assert pan == {"value": 0.0, "display": "C", "db": None, "pan_percent": 0}


def test_get_mixer_return_and_master(inst):
    ret = run(inst, "get_mixer", track_index=1, track_type="return")["result"]
    assert ret["name"] == "B Delay" and ret["track_type"] == "return"
    master = run(inst, "get_mixer", track_type="master")["result"]
    assert master["name"] == "Master" and master["sends"] == []


def test_get_mixer_is_served_inline_not_scheduled(inst):
    run(inst, "get_mixer", track_index=0)
    assert inst.scheduled == []


# ------------------------------------------------------- the pan regression

@pytest.mark.parametrize("value,display,percent", [
    (-1.0, "50L", -50), (-0.5, "25L", -25), (0.5, "25R", 25), (1.0, "50R", 50),
])
def test_off_centre_pan_is_pan_not_db(inst, song, value, display, percent):
    """Regression: '25L'/'50R' used to come back as db=25.0 / 50.0."""
    result = run(inst, "set_track_panning", track_index=0, value=value)["result"]
    assert result["display"] == display
    assert result["db"] is None
    assert result["pan_percent"] == percent
    assert run(inst, "get_mixer", track_index=0)["result"]["panning"]["db"] is None


def test_pan_value_is_clamped(inst, song):
    result = run(inst, "set_track_panning", track_index=0, value=3)["result"]
    assert result["value"] == 1.0 and result["display"] == "50R"


@pytest.mark.parametrize("text,expected", [
    ("C", 0), ("c", 0), ("50L", -50), ("25R", 25), (" 7R ", 7),
    ("L25", -25), ("R10", 10), ("12.5L", -12.5), ("0.0 dB", None),
    ("", None), ("hello", None),
])
def test_pan_display_parser(script_module, text, expected):
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    assert inst._pan_percent_for_display(text) == expected


def test_db_parser_refuses_a_pan_display(script_module, song):
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    pan = FakeMixer().panning
    pan.value = 0.5
    with pytest.raises(ValueError):
        inst._db_for_value(pan, pan.value)


def test_db_parser_handles_unicode_minus_and_decimal_commas(script_module):
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    p = FakeParam("v", 0.1, 0, 1, lambda v: "−3,5 dB")
    assert inst._db_for_value(p, 0.1) == -3.5


# ------------------------------------------------------------- set_track_volume

@pytest.mark.parametrize("target", [-60.0, -24.0, -6.0, -1.0, 0.0, 3.0, 5.5])
def test_db_target_lands_within_display_resolution(inst, song, target):
    """The bisection reads Live's own display, so accuracy is bounded by its
    resolution. The fake shows one decimal (0.1 dB); allow a step and a half."""
    result = run(inst, "set_track_volume", track_index=0, db=target)["result"]
    assert result["db"] == pytest.approx(target, abs=0.15)
    assert song.tracks[0].mixer_device.volume.value == pytest.approx(result["value"])


def test_raw_value_path(inst, song):
    result = run(inst, "set_track_volume", track_index=1, value=0.85)["result"]
    assert result["display"] == "0.0 dB" and result["name"] == "2-Bass"


def test_db_above_range_clamps_to_the_top(inst):
    result = run(inst, "set_track_volume", track_index=0, db=12)["result"]
    assert result["value"] == 1.0 and result["display"] == "6.0 dB"


def test_db_far_below_range_goes_to_the_bottom_of_the_fader_with_valid_json(inst):
    """A target below anything the fader can show lands at its bottom: either
    '-inf dB' or the lowest finite step. Either way the reply is valid JSON
    (no -Infinity token) and the display string says which."""
    result = run(inst, "set_track_volume", track_index=0, db=-200)["result"]
    assert result["value"] < 0.001
    assert result["display"].endswith("dB")
    assert result["db"] is None or result["db"] < -60
    json.dumps(result, allow_nan=False)


def test_silence_is_reported_as_null_db_with_the_display_saying_so(inst, song):
    run(inst, "set_track_volume", track_index=0, value=0.0)
    volume = run(inst, "get_mixer", track_index=0)["result"]["volume"]
    assert volume == {"value": 0.0, "display": "-inf dB", "db": None}
    json.dumps(volume, allow_nan=False)


def test_raw_value_is_clamped(inst):
    assert run(inst, "set_track_volume", track_index=0, value=5)["result"]["value"] == 1.0
    assert run(inst, "set_track_volume", track_index=0, value=-5)["result"]["value"] == 0.0


def test_volume_needs_db_or_value(inst):
    reply = run(inst, "set_track_volume", track_index=0)
    assert reply["status"] == "error"
    assert "db" in reply["message"] and "value" in reply["message"]


def test_volume_on_return_and_master(inst, song):
    run(inst, "set_track_volume", track_index=0, db=-3, track_type="return")
    run(inst, "set_track_volume", db=-1.5, track_type="master")
    assert fader_db(song.return_tracks[0].mixer_device.volume.value) == pytest.approx(-3, abs=0.15)
    assert fader_db(song.master_track.mixer_device.volume.value) == pytest.approx(-1.5, abs=0.15)
    assert song.tracks[0].mixer_device.volume.value == 0.85  # regular track untouched


# -------------------------------------------------------------------- set_send

def test_send_by_db(inst, song):
    result = run(inst, "set_send", track_index=0, send_index=1, db=-12)["result"]
    assert result["db"] == pytest.approx(-12, abs=0.15)
    assert result["send"] == "Send B" and result["index"] == 1
    assert song.tracks[0].mixer_device.sends[0].value == 0.0  # other send untouched


def test_send_index_out_of_range(inst):
    reply = run(inst, "set_send", track_index=0, send_index=5, db=0)
    assert reply["status"] == "error"
    assert "Send index 5 out of range" in reply["message"]


def test_master_has_no_sends(inst):
    reply = run(inst, "set_send", send_index=0, db=0, track_type="master")
    assert reply["status"] == "error"
    assert "has 0 sends" in reply["message"]


# ---------------------------------------------------------- track resolution

@pytest.mark.parametrize("index,kind,message", [
    (-1, "track", "out of range"),
    (2, "track", "out of range (have 2)"),
    (2, "return", "out of range (have 2)"),
])
def test_bad_indices(inst, index, kind, message):
    reply = run(inst, "get_mixer", track_index=index, track_type=kind)
    assert reply["status"] == "error" and message in reply["message"]


def test_unknown_track_type(inst):
    reply = run(inst, "get_mixer", track_index=0, track_type="bus")
    assert reply["status"] == "error"
    assert "Unknown track_type" in reply["message"]


# ----------------------------------------- scheduling / handshake / bundle

@pytest.mark.parametrize("command,params", [
    ("set_track_volume", {"track_index": 0, "db": -3}),
    ("set_track_panning", {"track_index": 0, "value": 0.2}),
    ("set_send", {"track_index": 0, "send_index": 0, "db": -9}),
])
def test_setters_are_scheduled_on_the_main_thread(inst, command, params):
    run(inst, command, **params)
    assert inst.scheduled == [(0, "main_thread_task")]


def test_version_and_capabilities(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    for name in ("get_mixer",) + SETTERS:
        assert name in script_module.SCRIPT_CAPABILITIES


def test_setters_are_in_the_dataset_modifying_set():
    assert set(SETTERS) <= MODIFYING_TOOLS


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


@pytest.mark.parametrize("command", SETTERS)
def test_server_treats_setters_as_modifying(command):
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command(command, {})
    assert conn.sock.timeouts[0] == 15.0


def test_server_treats_get_mixer_as_a_read():
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command("get_mixer", {})
    assert conn.sock.timeouts[0] == 10.0


# ------------------------------------------------------------- server tools

class FakeConnection(object):
    def __init__(self):
        self.response = {}
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, dict(params or {})))
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


def test_set_track_volume_tool_forwards_and_formats(conn):
    conn.response = {"name": "1-Drums", "display": "-6.0 dB"}
    out = call(server.set_track_volume, None, 0, db=-6.0)
    assert conn.sent == [("set_track_volume", {
        "track_index": 0, "db": -6.0, "value": None, "track_type": "track"})]
    assert out == "Set volume of '1-Drums' to -6.0 dB"


def test_set_track_volume_tool_requires_db_or_value(conn):
    assert call(server.set_track_volume, None, 0).startswith("Error:")
    assert conn.sent == []


def test_set_track_panning_tool(conn):
    conn.response = {"name": "1-Drums", "display": "25L"}
    out = call(server.set_track_panning, None, 0, -0.5)
    assert out == "Set panning of '1-Drums' to 25L"


def test_set_send_tool(conn):
    conn.response = {"name": "1-Drums", "send": "Send A", "display": "-12.0 dB"}
    out = call(server.set_send, None, 0, 0, db=-12.0)
    assert out == "Set send Send A on '1-Drums' to -12.0 dB"


def test_get_mixer_tool_returns_json(conn):
    conn.response = {"name": "Master", "sends": []}
    assert json.loads(call(server.get_mixer, None, track_type="master"))["name"] == "Master"


@pytest.mark.parametrize("name,args", [
    ("get_mixer", ()), ("set_track_volume", (0,)),
    ("set_track_panning", (0, 0.0)), ("set_send", (0, 0)),
])
def test_tools_return_the_capability_message_for_an_old_script(conn, monkeypatch, name, args):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda cap: "missing " + cap)
    assert call(getattr(server, name), None, *args, **{"db": 0.0} if name in (
        "set_track_volume", "set_send") else {}) == "missing " + name
    assert conn.sent == []
