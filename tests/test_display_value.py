"""display_value: set a parameter in the unit Live shows (Hz, ms, dB), and write envelopes in it.

The fake reproduces what Live 12.4 Lite did: Auto Filter Frequency is exponential (20 x 1000^raw Hz),
a number outside the range is limited without an error, a choice cannot take a display value.
"""
import math
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS  # noqa: F401
from tests.test_envelope_and_device_routing import Clip, run as env_run  # noqa: F401
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class FreqParam(object):
    """Frequency: raw 0..1, Hz = 20 x 1000^raw."""
    name, min, max, is_quantized = "Frequency", 0.0, 1.0, False

    def __init__(self):
        self.value = 0.9

    @property
    def display_value(self):
        return 20.0 * 1000.0 ** self.value

    @display_value.setter
    def display_value(self, hz):
        hz = min(20000.0, max(20.0, hz))
        self.value = math.log(hz / 20.0) / math.log(1000.0)

    def str_for_value(self, v):
        hz = 20.0 * 1000.0 ** v
        return "%.2f kHz" % (hz / 1000.0) if hz >= 999.95 else "%.1f Hz" % hz


class Choice(object):
    name, min, max, is_quantized, value = "Filter Type", 0.0, 9.0, True, 0.0

    def str_for_value(self, v):
        return "Low-pass"

    @property
    def display_value(self):
        raise RuntimeError("Invalid display value")


class Ratio(object):
    name, min, max, is_quantized, value = "Ratio", 0.0, 1.0, False, 1.0
    display_value = 3.4028232635611926e+38

    def str_for_value(self, v):
        return "inf : 1"


class Device(object):
    name, class_name = "Auto Filter", "AutoFilter2"

    def __init__(self):
        self.parameters = [FreqParam(), Choice(), Ratio()]


class Song(object):
    def __init__(self):
        self.clip = Clip()
        self.device = Device()
        track = types.SimpleNamespace(
            name="Pad", devices=[self.device], arrangement_clips=[self.clip],
            clip_slots=[types.SimpleNamespace(has_clip=True, clip=self.clip)],
            mixer_device=types.SimpleNamespace(volume=None, panning=None, sends=[]))
        self.tracks = [track]
        self.return_tracks, self.master_track = [], None


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song):
    return make_inst(script_module, song)


def setp(inst, **params):
    base = dict(track_index=0, device_index=0, parameter_index=0)
    base.update(params)
    return inst._process_command({"type": "set_device_parameter", "params": base})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_a_frequency_is_set_in_hz_and_read_back(inst, song):
    r = ok(setp(inst, display_value=1000.0))
    assert song.device.parameters[0].display_value == pytest.approx(1000.0)
    assert r["display"] == "1.00 kHz" and r["old_display"] == "10.02 kHz"
    assert r["display_value"] == pytest.approx(1000.0) and r["clamped"] is False
    assert r["value"] == pytest.approx(math.log(50) / math.log(1000))


def test_a_number_outside_the_range_is_reported_as_clamped(inst):
    r = ok(setp(inst, display_value=90000.0))
    assert r["clamped"] is True and r["display_value"] == pytest.approx(20000.0)


def test_exactly_one_of_value_and_display_value(inst):
    assert "exactly one" in err(setp(inst))
    assert "exactly one" in err(setp(inst, value=0.5, display_value=100.0))


def test_a_raw_value_still_works_and_has_no_clamped_field(inst):
    r = ok(setp(inst, value=0.5))
    assert r["value"] == 0.5 and "clamped" not in r and r["display"] == "632.5 Hz"


def test_a_choice_refuses_a_display_value(inst):
    assert "choice" in err(setp(inst, parameter_index=1, display_value=1.0))


def test_a_non_number_is_refused(inst):
    assert "number" in err(setp(inst, display_value="loud"))
    assert "number" in err(setp(inst, display_value=True))


def test_get_device_parameters_lists_display_values_but_not_for_choices_or_infinite_ones(inst):
    out = ok(inst._process_command({"type": "get_device_parameters",
                                    "params": {"track_index": 0, "device_index": 0}}))
    params = {p["name"]: p for p in out["device"]["parameters"]}
    assert params["Frequency"]["display_value"] == pytest.approx(10023.74, rel=1e-4)
    assert "display_value" not in params["Filter Type"] and "display_value" not in params["Ratio"]


# --------------------------------------------------------------------- envelopes in display units

VOLUME = dict(track_index=0, expected_name="Pad", clip_index=0, device_index=0, parameter="Frequency")


def test_an_envelope_in_hz_is_converted_by_live_and_the_parameter_is_put_back(inst, song):
    before = song.device.parameters[0].value
    r = ok(env_run(inst, "set_clip_envelope", value_unit="display", confirm=True,
                   points=[{"time": 0, "value": 80.0}, {"time": 4, "value": 10000.0}], **{
                       k: v for k, v in VOLUME.items() if k != "track_index"}))
    assert r["verified"] is True and r["value_unit"] == "display"
    assert [round(c["raw"], 3) for c in r["converted"]] == [0.201, 0.9]
    env = song.clip.envelopes[id(song.device.parameters[0])]
    assert [round(v, 3) for _, v in env.events[:2]] == [0.201, 0.9]
    assert song.device.parameters[0].value == before


def test_a_shape_takes_its_ends_in_display_units(inst, song):
    r = ok(env_run(inst, "set_clip_envelope", value_unit="display", confirm=True,
                   shape={"type": "curve", "exponent": 3, "min": 80.0, "max": 10000.0},
                   **{k: v for k, v in VOLUME.items() if k != "track_index"}))
    assert r["shape"]["min"] == pytest.approx(0.2007, abs=1e-3) and r["shape"]["max"] == pytest.approx(0.9, abs=1e-3)


def test_raw_stays_the_default_and_a_wrong_unit_is_refused(inst):
    r = ok(env_run(inst, "set_clip_envelope", confirm=False, points=[{"time": 0, "value": 0.2}],
                   **{k: v for k, v in VOLUME.items() if k != "track_index"}))
    assert "value_unit" not in r
    assert "value_unit" in err(env_run(inst, "set_clip_envelope", value_unit="dB", points=[{"time": 0, "value": 1}],
                                       **{k: v for k, v in VOLUME.items() if k != "track_index"}))


def test_a_choice_cannot_be_given_in_display_units(inst):
    msg = err(env_run(inst, "set_clip_envelope", value_unit="display", parameter="Filter Type",
                      points=[{"time": 0, "value": 1.0}], expected_name="Pad", clip_index=0, device_index=0))
    assert "choice" in msg


# --------------------------------------------------------------------- the tool

def test_the_tool_forwards_display_value_and_words_the_reply(conn):
    conn.response = {"name": "Frequency", "old_value": 0.9, "value": 0.566, "display": "1.00 kHz",
                     "old_display": "10.0 kHz", "clamped": False}
    out = call(server.set_device_parameter, None, 0, 0, 0, None, "track", 1000.0)
    assert conn.sent[-1] == ("set_device_parameter", {"track_index": 0, "device_index": 0,
                                                       "parameter_index": 0, "display_value": 1000.0})
    assert "10.0 kHz → 1.00 kHz" in out and "clamped" not in out
    conn.response = {"name": "Frequency", "old_value": 0.9, "value": 1.0, "display": "20.0 kHz", "clamped": True}
    assert "clamped" in call(server.set_device_parameter, None, 0, 0, 0, None, "track", 99999.0)
    assert "exactly one" in call(server.set_device_parameter, None, 0, 0, 0, 0.5, "track", 100.0)
    assert "exactly one" in call(server.set_device_parameter, None, 0, 0, 0)
