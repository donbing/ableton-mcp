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
    """insert_step holds a value over (time, time+length]; create_event adds a real breakpoint and
    Live draws straight lines between breakpoints (measured on Live 12.4 Lite)."""

    def __init__(self, default):
        self.default, self.steps, self.events = default, [], []

    def insert_step(self, time, length, value):
        self.steps = [s for s in self.steps if s[0] + s[1] <= time or s[0] >= time + length]
        self.steps.append((time, length, value))

    def create_event(self, event):
        self.events.append((event.time, event.value))
        self.events.sort(key=lambda e: e[0])

    def delete_events_in_range(self, a, b):
        self.events = [e for e in self.events if not (a <= e[0] <= b)]

    def value_at_time(self, t):
        if self.events:
            ev = self.events
            if t <= ev[0][0]:
                return ev[0][1]
            for (t0, v0), (t1, v1) in zip(ev, ev[1:]):
                if t0 <= t <= t1:
                    return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
            return ev[-1][1]
        # Live: at the exact start of a step two events share the time, and the answer is the
        # value from BEFORE the jump; the step holds on (start, end].
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
    assert result["applied"] is False and result["dry_run"] is True and result["event_count"] == 2
    assert song.clip.envelopes == {}


def test_steps_mode_holds_each_value_until_the_next_point(inst, song):
    result = ok(run(inst, "set_clip_envelope", confirm=True, mode="steps",
                    points=[{"time": 0, "value": 0.2}, {"time": 4, "value": 0.8}], **VOL))
    assert result["verified"] is True
    read = ok(run(inst, "get_clip_envelope", parameter="volume", step=2.0))
    assert [s["value"] for s in read["samples"]] == [0.2, 0.2, 0.8, 0.8]
    assert read["samples"][0]["display"] == "0.20"


def test_linear_mode_writes_real_breakpoints_and_holds_the_last_value(inst, song):
    result = ok(run(inst, "set_clip_envelope", confirm=True, end=4.0,
                    points=[{"time": 0, "value": 0.0}, {"time": 2, "value": 1.0}], **VOL))
    assert result["verified"] is True and result["event_count"] == 3 and result["mode"] == "linear"
    env = song.clip.envelopes[id(song.tracks[0].mixer_device.volume)]
    assert env.events == [(0.0, 0.0), (2.0, 1.0), (4.0, 1.0)] and env.steps == []
    read = ok(run(inst, "get_clip_envelope", parameter="volume", step=0.5, end=4.5))
    assert [round(s["value"], 3) for s in read["samples"]] == [0.0, 0.25, 0.5, 0.75, 1.0, 1.0, 1.0, 1.0, 1.0]


def test_ramp_is_the_same_as_linear(inst, song):
    result = ok(run(inst, "set_clip_envelope", confirm=True, mode="ramp",
                    points=[{"time": 0, "value": 0.0}, {"time": 2, "value": 1.0}], **VOL))
    assert result["mode"] == "linear"


def test_writing_again_replaces_the_old_breakpoints(inst, song):
    ok(run(inst, "set_clip_envelope", confirm=True, points=[{"time": 0, "value": 0.1}, {"time": 4, "value": 0.9}], **VOL))
    ok(run(inst, "set_clip_envelope", confirm=True, end=8.0, points=[{"time": 0, "value": 0.5}, {"time": 2, "value": 0.6}], **VOL))
    env = song.clip.envelopes[id(song.tracks[0].mixer_device.volume)]
    assert env.events == [(0.0, 0.5), (2.0, 0.6), (8.0, 0.6)]


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
    ok(run(inst, "set_clip_envelope", confirm=True, mode="steps",
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


# ------------------------------------------------------------------- shapes

PAN = dict(expected_name="Bass", parameter="pan", clip_index=0)


def shape(inst, spec, confirm=True, **extra):
    return ok(run(inst, "set_clip_envelope", shape=spec, confirm=confirm, **dict(PAN, **extra)))


def events_of(song):
    return song.clip.envelopes[id(song.tracks[0].mixer_device.panning)].events


def read(inst, step, end, parameter="pan"):
    return [round(s["value"], 3) for s in ok(run(inst, "get_clip_envelope", parameter=parameter,
                                                  step=step, end=end))["samples"]]


def test_a_sine_hits_its_quarter_points(inst, song):
    result = shape(inst, {"type": "sine", "period": 4})
    assert result["verified"] is True and result["max_error"] < 1e-3
    # 8 beats = 2 cycles, 16 points each, plus the closing point; pan range is -1..1
    assert result["point_count"] == 33
    values = read(inst, 1.0, 5.0)
    assert values == [0.0, 1.0, 0.0, -1.0, 0.0]


def test_a_sine_over_a_narrower_range_and_inverted(inst, song):
    shape(inst, {"type": "sine", "period": 4, "min": -0.5, "max": 0.3, "invert": True})
    values = read(inst, 1.0, 5.0)
    assert values == [-0.1, -0.5, -0.1, 0.3, -0.1]


def test_phase_starts_the_sine_at_the_bottom(inst, song):
    shape(inst, {"type": "sine", "period": 4, "phase": 0.75})
    assert read(inst, 1.0, 5.0) == [-1.0, 0.0, 1.0, 0.0, -1.0]


def test_cycles_instead_of_period(inst, song):
    shape(inst, {"type": "sine", "cycles": 4})        # the clip is 8 beats: a 2-beat period
    assert read(inst, 0.5, 2.5) == [0.0, 1.0, 0.0, -1.0, 0.0]


def test_a_sine_over_part_of_the_clip_leaves_the_rest_alone(inst, song):
    shape(inst, {"type": "sine", "period": 2, "start": 2, "end": 6})
    events = events_of(song)
    assert events[0][0] == 2.0 and events[-1][0] == 6.0


def test_more_points_per_cycle_is_a_better_sine(inst, song):
    coarse = shape(inst, {"type": "sine", "period": 4, "points_per_cycle": 4})["point_count"]
    fine = shape(inst, {"type": "sine", "period": 4, "points_per_cycle": 64})["point_count"]
    assert coarse == 9 and fine == 129


def test_a_triangle_has_its_vertices_exactly(inst, song):
    shape(inst, {"type": "triangle", "period": 4})
    assert events_of(song) == [(0.0, 0.0), (1.0, 1.0), (3.0, -1.0), (5.0, 1.0), (7.0, -1.0), (8.0, 0.0)]


def test_a_saw_jumps_back_at_each_cycle_and_every_ramp_reaches_the_top(inst, song):
    shape(inst, {"type": "saw_up", "period": 4})
    events = events_of(song)
    assert events[0] == (0.0, -1.0)
    assert any(abs(v - 1.0) < 0.02 for t, v in events if 3.9 < t < 4.0)        # the top, just before the wrap
    assert any(t == 4.0 and v == -1.0 for t, v in events)                       # the jump down
    assert any(abs(v - 1.0) < 0.02 for t, v in events if 7.9 < t < 8.0)        # and the second ramp too
    assert read(inst, 1.0, 8.0) == [-1.0, -0.5, 0.0, 0.5, -1.0, -0.5, 0.0, 0.5]
    shape(inst, {"type": "saw_down", "period": 4})
    assert events_of(song)[0] == (0.0, 1.0)
    assert read(inst, 1.0, 4.0) == [1.0, 0.5, 0.0, -0.5]


def test_a_square_holds_between_its_edges(inst, song):
    result = shape(inst, {"type": "square", "period": 4, "duty": 0.25})
    assert result["mode"] == "steps"
    assert read(inst, 0.5, 4.5) == [1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, 1.0]


def test_random_shapes_are_repeatable_with_a_seed_and_stay_in_range(inst, song):
    a = shape(inst, {"type": "random_smooth", "period": 1, "seed": 7, "min": -0.5, "max": 0.5})
    first = list(events_of(song))
    shape(inst, {"type": "random_smooth", "period": 1, "seed": 7, "min": -0.5, "max": 0.5})
    assert events_of(song) == first and a["mode"] == "linear"
    assert all(-0.5 <= v <= 0.5 for t, v in first)
    shape(inst, {"type": "random_steps", "period": 2, "seed": 3})
    assert len(read(inst, 2.0, 8.0)) == 4          # one value per 2-beat period: 0, 2, 4, 6


def test_a_curve_goes_from_min_to_max_with_the_exponent(inst, song):
    shape(inst, {"type": "curve", "exponent": 2.0, "min": 0.0, "max": 1.0})
    values = read(inst, 4.0, 8.0)
    assert values[0] == 0.0 and values[1] == pytest.approx(0.25, abs=0.01)
    shape(inst, {"type": "curve", "exponent": 1.0, "invert": True})
    assert read(inst, 4.0, 8.0) == [1.0, 0.0]


def test_a_shape_preview_writes_nothing(inst, song):
    result = shape(inst, {"type": "sine", "period": 4}, confirm=False)
    assert result["applied"] is False and result["shape"]["type"] == "sine" and result["event_count"] == 33
    assert song.clip.envelopes == {}


@pytest.mark.parametrize("spec,needle", [
    ({"type": "wobble"}, "shape.type must be"),
    ({"type": "sine", "perod": 4}, "unknown field(s) perod"),
    ({"type": "sine", "period": 4, "cycles": 2}, "period or shape.cycles, not both"),
    ({"type": "sine", "period": 0.001}, "period is too short"),
    ({"type": "sine", "min": -3}, "outside the parameter's range"),
    ({"type": "sine", "min": 0.5, "max": 0.1}, "max must be >= shape.min"),
    ({"type": "sine", "start": 6, "end": 2}, "start/end"),
    ({"type": "sine", "end": 99}, "start/end"),
    ({"type": "sine", "points_per_cycle": 2}, "points_per_cycle"),
    ({"type": "sine", "invert": "yes"}, "invert must be"),
    ({"type": "square", "duty": 1.5}, "duty"),
    ({"type": "curve", "exponent": 0}, "exponent"),
    ("sine", "shape must be an object"),
])
def test_bad_shapes_write_nothing(inst, song, spec, needle):
    assert needle in err(run(inst, "set_clip_envelope", shape=spec, confirm=True, **PAN))
    assert song.clip.envelopes == {}


def test_too_many_events_is_refused_with_advice(inst, song):
    message = err(run(inst, "set_clip_envelope", confirm=True, **dict(PAN, shape={
        "type": "sine", "period": 0.0625, "points_per_cycle": 128})))
    assert "at most 2048" in message and "points_per_cycle" in message


def test_points_and_shape_together_are_refused(inst):
    assert "not both" in err(run(inst, "set_clip_envelope", confirm=True, shape={"type": "sine"},
                                 points=[{"time": 0, "value": 0}], **PAN))


def test_the_tool_needs_exactly_one_of_points_and_shape(conn):
    assert "exactly one" in call(server.set_clip_envelope, None, 0, "Bass", "pan")
    assert "exactly one" in call(server.set_clip_envelope, None, 0, "Bass", "pan",
                                 [{"time": 0, "value": 0}], {"type": "sine"})
    conn.response = {"applied": False}
    call(server.set_clip_envelope, None, 0, "Bass", "pan", shape={"type": "sine", "period": 4})
    assert conn.sent[-1][1]["shape"] == {"type": "sine", "period": 4} and "points" not in conn.sent[-1][1]
    assert conn.sent[-1][1]["mode"] == "linear"
