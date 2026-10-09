"""Tests for get_meters.

The Remote Script samples output_meter_left/right on the client handler thread
(not on Live's main thread, and not by scheduling hundreds of main-thread
callbacks). These tests drive it against a mocked Live Object Model with a
virtual clock, so the sampling schedule, the aggregation and the threading
contract are all checked without Ableton and without real sleeping.
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
        "ableton_mcp_script_meters", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class Clock(object):
    """Virtual clock standing in for the ``time`` module inside the script."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def time(self):
        return 1000.0 + self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTrack(object):
    """Meter values come from a function of virtual time, per channel."""

    def __init__(self, name, clock, left=0.0, right=0.0):
        self.name = name
        self._clock = clock
        self._left = left if callable(left) else (lambda t, v=left: v)
        self._right = right if callable(right) else (lambda t, v=right: v)
        self.reads = 0

    @property
    def output_meter_left(self):
        self.reads += 1
        return self._left(self._clock.now)

    @property
    def output_meter_right(self):
        return self._right(self._clock.now)


class FakeSong(object):
    def __init__(self, clock):
        self.is_playing = True
        self.tracks = [
            FakeTrack("1-Drums", clock, left=0.5, right=0.25),
            FakeTrack("2-Bass", clock, left=0.0, right=0.0),
        ]
        self.return_tracks = [FakeTrack("A Reverb", clock, left=0.1, right=0.1)]
        self.master_track = FakeTrack("Master", clock, left=1.0, right=0.5)


@pytest.fixture
def clock(script_module, monkeypatch):
    c = Clock()
    monkeypatch.setattr(script_module, "time", c)
    return c


@pytest.fixture
def song(clock):
    return FakeSong(clock)


@pytest.fixture
def inst(script_module, song):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.running = True
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    return obj


def meters(inst, **params):
    return inst._process_command({"type": "get_meters", "params": params})


# --------------------------------------------------------- aggregation

def test_default_window_is_two_seconds_at_twenty_hz(inst, clock):
    reply = meters(inst)
    assert reply["status"] == "success"
    result = reply["result"]
    assert result["hz"] == 20
    assert result["seconds_requested"] == 2.0
    assert result["samples"] == 41  # 2 s * 20 Hz, both ends of the window
    assert result["seconds_elapsed"] == pytest.approx(2.0, abs=0.01)


def test_peak_and_mean_for_a_constant_signal(inst):
    result = meters(inst, seconds=1, hz=10)["result"]
    drums = result["tracks"][0]
    assert drums["name"] == "1-Drums" and drums["index"] == 0
    assert drums["peak_left"] == 0.5 and drums["peak_right"] == 0.25
    assert drums["mean_left"] == 0.5 and drums["mean_right"] == 0.25
    assert drums["peak"] == 0.5
    assert drums["mean"] == pytest.approx(0.375)


def test_db_approx_conversion_is_linear_in_db(inst):
    """Live's meter is ~linear in dB: (raw - 0.85) / 0.01325, not 20*log10."""
    drums = meters(inst, seconds=1, hz=10)["result"]["tracks"][0]
    assert drums["peak_db_approx"] == pytest.approx((0.5 - 0.85) / 0.01325, abs=0.01)
    assert drums["mean_db_approx"] == pytest.approx((0.375 - 0.85) / 0.01325, abs=0.01)


def test_db_approx_matches_the_live_calibration_points(inst, song):
    """Real Live: fader at -36..-6 dB read raw 0.3582..0.7550 (peak)."""
    for raw, expected_db in ((0.85, 0.0), (0.4301, -31.7), (0.3582, -37.1),
                             (0.7550, -7.2), (0.4, -34.0)):
        song.tracks[0]._left = lambda t, v=raw: v
        song.tracks[0]._right = lambda t, v=raw: v
        drums = meters(inst, seconds=0.5, hz=10)["result"]["tracks"][0]
        assert drums["peak_db_approx"] == pytest.approx(expected_db, abs=0.1)


def test_old_linear_amplitude_formula_is_not_used(inst, song):
    song.tracks[0]._left = lambda t: 0.4301
    song.tracks[0]._right = lambda t: 0.4301
    drums = meters(inst, seconds=0.5, hz=10)["result"]["tracks"][0]
    # 20*log10(0.4301) would be -7.33 dB, ~24 dB too loud for a -30 dB fader.
    assert drums["peak_db_approx"] != pytest.approx(20 * math.log10(0.4301), abs=1.0)
    assert drums["peak_db_approx"] < -30
    assert not any(k.endswith("_dbfs") for k in drums)


def test_silence_has_zero_levels_and_null_db_approx(inst, song):
    bass = meters(inst, seconds=1, hz=10)["result"]["tracks"][1]
    assert bass["peak"] == 0.0 and bass["mean"] == 0.0
    assert bass["peak_db_approx"] is None and bass["mean_db_approx"] is None
    # The floor: anything at or below 0.03 is silence, just above is a number.
    song.tracks[0]._left = lambda t: 0.03
    song.tracks[0]._right = lambda t: 0.03
    drums = meters(inst, seconds=0.5, hz=10)["result"]["tracks"][0]
    assert drums["peak_db_approx"] is None
    song.tracks[0]._left = lambda t: 0.031
    song.tracks[0]._right = lambda t: 0.031
    drums = meters(inst, seconds=0.5, hz=10)["result"]["tracks"][0]
    assert drums["peak_db_approx"] is not None


def test_every_track_return_and_master_is_reported(inst):
    result = meters(inst, seconds=1, hz=10)["result"]
    assert [t["name"] for t in result["tracks"]] == ["1-Drums", "2-Bass"]
    assert [t["name"] for t in result["return_tracks"]] == ["A Reverb"]
    assert result["master"]["name"] == "Master"
    assert result["master"]["peak"] == 1.0
    assert result["master"]["peak_db_approx"] == pytest.approx(
        (1.0 - 0.85) / 0.01325, abs=0.01)


def test_peak_catches_a_transient_the_mean_averages_away(inst, song, clock):
    """A 1-sample spike at t=0.5 s in an otherwise quiet signal."""
    song.tracks[0]._left = lambda t: 0.9 if abs(t - 0.5) < 1e-6 else 0.1
    song.tracks[0]._right = lambda t: 0.0
    drums = meters(inst, seconds=1, hz=10)["result"]["tracks"][0]
    assert drums["peak_left"] == 0.9
    assert drums["mean_left"] < 0.2
    assert drums["peak"] == 0.9


def test_a_ramp_is_averaged_across_the_whole_window(inst, song):
    song.tracks[0]._left = lambda t: t  # 0 .. 1 over a 1 s window
    song.tracks[0]._right = lambda t: t
    drums = meters(inst, seconds=1, hz=10)["result"]["tracks"][0]
    assert drums["peak"] == pytest.approx(1.0)
    assert drums["mean"] == pytest.approx(0.5, abs=0.01)


def test_the_note_explains_the_scale(inst):
    note = meters(inst, seconds=0.5, hz=10)["result"]["note"]
    assert "linear in dB" in note and "NOT linear amplitude" in note
    assert "20*log10" not in note


def test_response_carries_a_scale_object(inst):
    scale = meters(inst, seconds=0.5, hz=10)["result"]["scale"]
    assert scale == {
        "raw": ("Live's 0..1 meter reading, approximately linear in dB, "
                "NOT linear amplitude"),
        "db_approx": "(raw-0.85)/0.01325",
        "calibrated_range_db": [-37, -7],
        "accuracy_db": ("about +-1 dB (1 sigma), single readings up to about +-4 dB, "
                        "inside the calibrated range; extrapolated outside it (unverified)"),
    }


def test_tool_docstring_states_the_scale():
    doc = server.get_meters.__doc__ or ""
    assert "LINEAR IN dB" in doc and "db_approx" in doc
    assert "dBFS conversion" not in doc


def test_reports_transport_state(inst, song):
    assert meters(inst, seconds=0.5, hz=10)["result"]["is_playing"] is True
    song.is_playing = False
    assert meters(inst, seconds=0.5, hz=10)["result"]["is_playing"] is False


# ------------------------------------------------- limits and validation

def test_seconds_are_capped_at_ten(inst):
    result = meters(inst, seconds=60, hz=10)["result"]
    assert result["seconds_requested"] == 10.0
    assert result["capped_to_max_seconds"] is True
    assert result["samples"] == 101
    assert result["seconds_elapsed"] <= 10.01


def test_not_capped_flag_is_false_within_the_limit(inst):
    assert meters(inst, seconds=3, hz=10)["result"]["capped_to_max_seconds"] is False


def test_hz_is_clamped_to_the_supported_range(inst):
    assert meters(inst, seconds=1, hz=1000)["result"]["hz"] == 50
    assert meters(inst, seconds=1, hz=0.01)["result"]["hz"] == 1


@pytest.mark.parametrize("bad", [0, -1, "2", None, True, float("nan"), float("inf")])
def test_invalid_seconds_is_an_error(inst, bad):
    reply = meters(inst, seconds=bad)
    assert reply["status"] == "error"
    assert "seconds must be a positive number" in reply["message"]


@pytest.mark.parametrize("bad", [0, -5, "20", None])
def test_invalid_hz_is_an_error(inst, bad):
    reply = meters(inst, hz=bad)
    assert reply["status"] == "error"
    assert "hz must be a positive number" in reply["message"]


def test_sampling_is_paced_by_sleeping_not_spinning(inst, clock):
    meters(inst, seconds=1, hz=10)
    assert len(clock.sleeps) == 10  # one gap between each of 11 samples
    assert all(s == pytest.approx(0.1, abs=1e-6) for s in clock.sleeps)


def test_slow_reads_do_not_make_the_window_longer(inst, song, clock):
    """Pacing targets absolute sample times, so read cost is not added up."""
    original = song.tracks[0].__class__.output_meter_left

    def slow(self):
        clock.now += 0.03  # each read costs 30 ms of virtual time
        return original.fget(self)

    song.tracks[0].__class__.output_meter_left = property(slow)
    try:
        result = meters(inst, seconds=1, hz=10)["result"]
    finally:
        song.tracks[0].__class__.output_meter_left = original
    assert result["seconds_elapsed"] < 1.5


def test_stops_early_when_the_script_is_shutting_down(inst, clock):
    inst.running = False
    result = meters(inst, seconds=5, hz=10)["result"]
    assert result["samples"] == 0
    assert clock.sleeps == []


# --------------------------------------------------------- robustness

def test_an_unreadable_meter_is_reported_and_does_not_fail_the_call(inst, song):
    class Broken(FakeTrack):
        @property
        def output_meter_left(self):
            raise RuntimeError("no meter on this track")

    song.tracks[1] = Broken("2-Bass", song.tracks[0]._clock)
    result = meters(inst, seconds=0.5, hz=10)["result"]
    assert result["tracks"][1] == {"index": 1, "name": "2-Bass", "meter_available": False}
    assert result["tracks"][0]["meter_available"] is True


def test_non_finite_meter_values_are_dropped(inst, song):
    song.tracks[0]._left = lambda t: float("nan")
    result = meters(inst, seconds=0.5, hz=10)["result"]
    assert result["tracks"][0]["meter_available"] is False


def test_result_is_valid_json_without_infinity_or_nan(inst):
    text = json.dumps(meters(inst, seconds=0.5, hz=10)["result"], allow_nan=False)
    assert "Infinity" not in text and "NaN" not in text


# ----------------------------------------- threading / scheduling contract

def test_get_meters_is_not_scheduled_on_the_main_thread(inst):
    """The whole point: sampling must not occupy Live's main thread."""
    meters(inst, seconds=1, hz=10)
    assert inst.scheduled == []


def test_a_main_thread_modifier_is_still_scheduled(inst):
    """Control: the same harness does register real modifying commands."""
    inst._process_command({"type": "set_tempo", "params": {"tempo": 120.0}})
    assert len(inst.scheduled) == 1


def test_meters_are_read_on_the_calling_thread_only(inst, song):
    import threading
    seen = set()
    cls = song.tracks[0].__class__
    original = cls.output_meter_right

    def spy(self):
        seen.add(threading.get_ident())
        return original.fget(self)

    cls.output_meter_right = property(spy)
    try:
        meters(inst, seconds=0.5, hz=10)
    finally:
        cls.output_meter_right = original
    assert seen == {threading.get_ident()}


# ------------------------------------------------ handshake / bundle / server

def test_version_capability_and_dispatch(script_module, inst):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    assert "get_meters" in script_module.SCRIPT_CAPABILITIES
    assert script_module.METER_MAX_SECONDS == 10.0


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


def test_server_allows_get_meters_more_than_the_default_socket_budget():
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command("get_meters", {"seconds": 10, "hz": 20})
    assert conn.sock.timeouts[0] > 10.0


class FakeConnection(object):
    def __init__(self):
        self.response = {"tracks": []}
        self.raise_exc = None
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, dict(params or {})))
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


def test_tool_defaults(conn):
    call(server.get_meters, None)
    assert conn.sent == [("get_meters", {"seconds": 2.0, "hz": 20})]


def test_tool_caps_seconds_before_sending(conn):
    call(server.get_meters, None, seconds=999)
    assert conn.sent[0][1]["seconds"] == 10.0


def test_tool_rejects_non_positive_arguments_without_talking_to_live(conn):
    assert call(server.get_meters, None, seconds=0).startswith("Error getting meters:")
    assert call(server.get_meters, None, hz=0).startswith("Error getting meters:")
    assert conn.sent == []


def test_tool_returns_the_result_as_json(conn):
    conn.response = {"samples": 41, "tracks": [{"index": 0, "peak": 0.5}]}
    assert json.loads(call(server.get_meters, None))["samples"] == 41


def test_tool_reports_errors_as_text(conn):
    conn.raise_exc = Exception("boom")
    assert call(server.get_meters, None).startswith("Error getting meters: boom")


def test_tool_returns_the_capability_message_for_an_old_script(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.get_meters, None) == "missing get_meters"
    assert conn.sent == []
