"""Clip automation envelopes and device (sidechain) routing against a fake Live.

The fake mirrors what was measured on Live 12.4 Lite (2026-10-24): a clip's
automation_envelope(parameter) is None until create_automation_envelope, its
value_at_time answers in the parameter's units, insert_step(time, length, value)
writes a constant stretch, and a device lists the channels of a new routing type
only a moment after the type is set.
"""
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Param(object):
    def __init__(self, name, lo=0.0, hi=1.0, value=0.5):
        self.name, self.min, self.max, self.value = name, lo, hi, value

    def str_for_value(self, v):
        return "%.2f" % v


class Envelope(object):
    def __init__(self, default):
        self.default, self.steps = default, []

    def insert_step(self, time, length, value):
        self.steps = [s for s in self.steps if s[0] + s[1] <= time or s[0] >= time + length]
        self.steps.append((time, length, value))

    def value_at_time(self, t):
        # Live: at the exact start of a step two events share the time, and the
        # answer is the value from BEFORE the jump; the step holds on (start, end].
        for time, length, value in self.steps:
            if time < t <= time + length:
                return value
        return self.default


class Clip(object):
    def __init__(self, length=8.0, start=0.0):
        self.name, self.length = "Pattern", length
        self.start_time, self.end_time = start, start + length
        self.envelopes = {}

    def automation_envelope(self, p):
        return self.envelopes.get(id(p))

    def create_automation_envelope(self, p):
        self.envelopes[id(p)] = Envelope(p.value)
        return self.envelopes[id(p)]

    def clear_envelope(self, p):
        self.envelopes.pop(id(p), None)


class Routing(object):
    def __init__(self, name):
        self.display_name = name


class Compressor(object):
    name, class_name = "Compressor", "Compressor2"

    def __init__(self):
        self.parameters = [Param("Threshold", -60.0, 0.0, -20.0), Param("S/C On", 0.0, 1.0, 0.0)]
        self.available_input_routing_types = [Routing("Kick"), Routing("Mic"), Routing("No Input")]
        self._type = self.available_input_routing_types[2]
        self._applied = "No Input"
        self._channel = Routing("")
        self.channel_sets = []

    def tick(self):
        self._applied = self._type.display_name

    @property
    def input_routing_type(self):
        return self._type

    @input_routing_type.setter
    def input_routing_type(self, value):
        self._type = value

    @property
    def available_input_routing_channels(self):
        return [Routing("")] if self._applied == "No Input" else [Routing("Pre FX"), Routing("Post FX")]

    @property
    def input_routing_channel(self):
        return self._channel

    @input_routing_channel.setter
    def input_routing_channel(self, value):
        if value.display_name not in [c.display_name for c in self.available_input_routing_channels]:
            raise RuntimeError("channel not available yet")
        self.channel_sets.append(value.display_name)
        self._channel = value


class Gain(object):
    name, class_name = "Utility", "StereoGain"
    parameters = [Param("Gain", -35.0, 35.0, 0.0)]


class Track(object):
    def __init__(self, name, clip):
        self.name = name
        self.clip_slots = [types.SimpleNamespace(has_clip=True, clip=clip)]
        self.arrangement_clips = [clip]
        self.devices = [Gain(), Compressor()]
        self.mixer_device = types.SimpleNamespace(
            volume=Param("Volume", 0.0, 1.0, 0.85), panning=Param("Pan", -1.0, 1.0, 0.0),
            sends=[Param("Send A"), Param("Send B")])


class Song(object):
    def __init__(self):
        self.clip = Clip()
        self.tracks = [Track("Bass", self.clip)]
        self.return_tracks, self.master_track = [], None


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    monkeypatch.setattr(script_module.time, "sleep", lambda s: song.tracks[0].devices[1].tick())
    return make_inst(script_module, song)


def run(inst, command, **params):
    params.setdefault("track_index", 0)
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


VOL = dict(expected_name="Bass", parameter="volume", clip_index=0)


# ------------------------------------------------------------------ envelopes

def test_read_says_there_is_no_automation_yet(inst):
    result = ok(run(inst, "get_clip_envelope", parameter="volume"))
    assert result["has_envelope"] is False and "samples" not in result
    assert result["parameter"]["name"] == "Volume" and result["clip_span"] == 8.0


def test_writing_previews_by_default_and_changes_nothing(inst, song):
    result = ok(run(inst, "set_clip_envelope", points=[{"time": 0, "value": 0.2}], **VOL))
    assert result["applied"] is False and result["dry_run"] is True and result["step_count"] == 1
    assert song.clip.envelopes == {}


def test_steps_mode_holds_each_value_until_the_next_point(inst, song):
    result = ok(run(inst, "set_clip_envelope", confirm=True,
                    points=[{"time": 0, "value": 0.2}, {"time": 4, "value": 0.8}], **VOL))
    assert result["verified"] is True
    read = ok(run(inst, "get_clip_envelope", parameter="volume", step=2.0))
    assert [s["value"] for s in read["samples"]] == [0.2, 0.2, 0.8, 0.8]
    assert read["samples"][0]["display"] == "0.20"


def test_ramp_mode_draws_a_straight_line_in_steps(inst):
    result = ok(run(inst, "set_clip_envelope", confirm=True, mode="ramp", resolution=0.5, end=4.0,
                    points=[{"time": 0, "value": 0.0}, {"time": 2, "value": 1.0}], **VOL))
    assert result["verified"] is True and result["step_count"] == 5
    read = ok(run(inst, "get_clip_envelope", parameter="volume", step=0.5, end=2.5))
    assert [round(s["value"], 3) for s in read["samples"]] == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_a_device_parameter_and_a_send_are_found_by_name(inst):
    ok(run(inst, "set_clip_envelope", confirm=True, device_index=1, parameter="threshold",
           expected_name="Bass", clip_index=0, points=[{"time": 0, "value": -30}]))
    assert ok(run(inst, "get_clip_envelope", device_index=1, parameter="Threshold"))["samples"][0]["value"] == -30
    ok(run(inst, "set_clip_envelope", confirm=True, parameter="send b", expected_name="Bass",
           clip_index=0, points=[{"time": 0, "value": 0.4}]))
    assert ok(run(inst, "get_clip_envelope", parameter="send 1"))["has_envelope"] is True


def test_an_arrangement_clip_is_refused_with_the_way_round(inst):
    message = err(run(inst, "get_clip_envelope", parameter="volume", arrangement=True,
                      clip_start_time=16.0))
    assert "SESSION clips" in message and "duplicate_to_arrangement" in message
    assert "SESSION clips" in err(run(inst, "set_clip_envelope", arrangement=True, confirm=True,
                                      points=[{"time": 0, "value": 0.1}], **VOL))


@pytest.mark.parametrize("kwargs,needle", [
    (dict(points=[{"time": 0, "value": 1.5}]), "outside 'Volume' range"),
    (dict(points=[{"time": 9, "value": 0.5}]), "outside the clip"),
    (dict(points=[{"time": 2, "value": 0.5}, {"time": 1, "value": 0.5}]), "increasing time"),
    (dict(points=[]), "non-empty"),
    (dict(points=[{"time": 0, "value": 0.5}], mode="curve"), "mode must be"),
    (dict(points=[{"time": 0, "value": 0.5}], resolution=100), "resolution"),
    (dict(points=[{"time": 0, "value": 0.5}], parameter="reverb"), "Unknown mixer parameter"),
    (dict(points=[{"time": 0, "value": 0.5}], parameter="send D"), "Unknown send"),
    (dict(points=[{"time": 0, "value": 0.5}], expected_name="Other"), "not 'Other'"),
    (dict(points=[{"time": 0, "value": 0.5}], expected_name=None), "expected_name is required"),
])
def test_bad_envelopes_are_refused_and_write_nothing(inst, song, kwargs, needle):
    args = dict(VOL, confirm=True)
    args.update(kwargs)
    assert needle in err(run(inst, "set_clip_envelope", **args))
    assert song.clip.envelopes == {}


def test_a_device_parameter_that_does_not_exist_lists_the_ones_that_do(inst):
    message = err(run(inst, "set_clip_envelope", confirm=True, device_index=1, parameter="Nope",
                      expected_name="Bass", clip_index=0, points=[{"time": 0, "value": 0}]))
    assert "No parameter 'Nope'" in message and "Threshold" in message


def test_clear_previews_then_removes(inst, song):
    ok(run(inst, "set_clip_envelope", confirm=True, points=[{"time": 0, "value": 0.2}], **VOL))
    preview = ok(run(inst, "clear_clip_envelope", expected_name="Bass", parameter="volume", clip_index=0))
    assert preview["had_automation"] is True and preview["applied"] is False and song.clip.envelopes
    done = ok(run(inst, "clear_clip_envelope", expected_name="Bass", parameter="volume",
                  clip_index=0, confirm=True))
    assert done["applied"] is True and done["has_automation_now"] is False and not song.clip.envelopes


def test_sampling_exactly_on_a_step_start_still_reads_that_step(inst, song):
    ok(run(inst, "set_clip_envelope", confirm=True,
           points=[{"time": 0, "value": 0.2}, {"time": 2, "value": 0.8}], **VOL))
    env = song.clip.envelopes[id(song.tracks[0].mixer_device.volume)]
    assert env.value_at_time(2.0) == 0.2        # Live's answer on the boundary itself
    assert [s["value"] for s in ok(run(inst, "get_clip_envelope", parameter="volume",
                                       step=2.0, end=4.0))["samples"]] == [0.2, 0.8]


def test_the_sample_count_is_capped(inst):
    ok(run(inst, "set_clip_envelope", confirm=True, points=[{"time": 0, "value": 0.2}], **VOL))
    assert "at most 512" in err(run(inst, "get_clip_envelope", parameter="volume", step=0.001))


# ------------------------------------------------------------ device routing

def test_device_routing_is_read_with_the_sidechain_state(inst):
    result = ok(run(inst, "get_device_routing", device_index=1))
    assert result["device_name"] == "Compressor" and result["sidechain_on"] is False
    assert result["input"]["available_types"] == ["Kick", "Mic", "No Input"]


def test_a_device_without_routing_says_so(inst):
    assert "has no routing" in err(run(inst, "get_device_routing", device_index=0))


def test_sidechain_setup_in_one_call_waits_for_the_channels(inst, song):
    result = ok(run(inst, "set_device_routing", device_index=1, expected_name="Bass",
                    expected_device_name="Compressor", routing_type="kick",
                    routing_channel="Post FX", sidechain_on=True))
    assert result["verified"] is True
    assert result["before"] == {"type": "No Input", "channel": "", "sidechain_on": False}
    assert result["after"]["input"]["type"] == "Kick" and result["after"]["sidechain_on"] is True
    assert song.tracks[0].devices[1].channel_sets == ["Post FX"]


@pytest.mark.parametrize("kwargs,needle", [
    (dict(expected_name="Other"), "not 'Other'"),
    (dict(expected_device_name="Gate"), "not 'Gate'"),
    (dict(routing_type="Nope"), "Routing type 'Nope' not found"),
    (dict(routing_channel="Nope"), "Routing channel 'Nope' not found"),
    (dict(routing_type=None, routing_channel=None, sidechain_on=None), "Give routing_type"),
    (dict(sidechain_on="yes"), "sidechain_on must be"),
])
def test_bad_device_routing_changes_nothing(inst, song, kwargs, needle):
    args = dict(device_index=1, expected_name="Bass", expected_device_name="Compressor",
                routing_type="Kick")
    args.update(kwargs)
    message = err(run(inst, "set_device_routing", **args))
    assert needle in message
    assert song.tracks[0].devices[1].input_routing_type.display_name == "No Input"
    if "Routing channel" in needle:
        assert "put back to 'No Input'" in message


# -------------------------------------------------------------------- tools

def test_tools_preview_and_pass_the_right_commands(conn):
    conn.response = {"applied": False}
    out = call(server.set_clip_envelope, None, 0, "Bass", "volume", [{"time": 0, "value": 0.5}])
    assert conn.sent[-1][0] == "set_clip_envelope" and conn.sent[-1][1]["confirm"] is False
    assert out.startswith("NOT WRITTEN")
    out = call(server.clear_clip_envelope, None, 0, "Bass", "volume")
    assert out.startswith("NOT REMOVED") and conn.sent[-1][1]["confirm"] is False
    call(server.get_clip_envelope, None, 0, "volume", 2)
    assert conn.sent[-1] == ("get_clip_envelope", {"track_index": 0, "clip_index": 2,
                                                  "parameter": "volume", "step": 0.25})
    call(server.set_device_routing, None, 0, 1, "Bass", "Compressor", routing_type="Kick",
         sidechain_on=True)
    assert conn.sent[-1][1]["sidechain_on"] is True
    assert "required" in call(server.set_device_routing, None, 0, 1, None, "Compressor", routing_type="Kick")
    assert "required" in call(server.set_clip_envelope, None, 0, None, "volume", [], confirm=True)
    assert {"set_device_routing", "set_clip_envelope", "clear_clip_envelope"} <= MODIFYING_TOOLS
