"""1.10.20: clip launch settings and why a track is silent (muted_via_solo, frozen) in the overview.

Measured on Live 12.4 Lite (2026-10-24): Clip.launch_quantization takes Live.Clip.ClipLaunchQuantization
(0 follows the Set), launch_mode Live.Clip.LaunchMode, legato; all apply at once.
"""
import sys
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


@pytest.fixture(autouse=True)
def live(monkeypatch):
    fake = types.ModuleType("Live")
    fake.Clip = types.SimpleNamespace(
        ClipLaunchQuantization=types.SimpleNamespace(
            q_global=0, q_none=1, q_8_bars=2, q_4_bars=3, q_2_bars=4, q_bar=5, q_half=6, q_half_triplet=7,
            q_quarter=8, q_quarter_triplet=9, q_eighth=10, q_eighth_triplet=11, q_sixteenth=12,
            q_sixteenth_triplet=13, q_thirtysecond=14),
        LaunchMode=types.SimpleNamespace(trigger=0, gate=1, toggle=2, repeat=3))
    monkeypatch.setitem(sys.modules, "Live", fake)


class Clip(object):
    name, length, is_midi_clip, is_audio_clip, is_playing, looping = "Riff", 4.0, True, False, False, True
    loop_start, loop_end, start_marker, end_marker, muted, color_index = 0.0, 4.0, 0.0, 4.0, False, 0

    def __init__(self):
        self.launch_quantization, self.launch_mode, self.legato = 0, 0, False

    def get_notes_extended(self, *a):
        return []


class Track(object):
    def __init__(self, name, clip=None, **flags):
        self.name = name
        self.clip_slots = [types.SimpleNamespace(has_clip=clip is not None, clip=clip)]
        self.devices = []
        self.mixer_device = types.SimpleNamespace(volume=types.SimpleNamespace(str_for_value=lambda v: "0.0 dB", value=0.85),
                                                  panning=types.SimpleNamespace(str_for_value=lambda v: "C", value=0.0),
                                                  sends=[])
        self.mute = self.solo = False
        self.has_midi_input = True
        self.is_foldable = False
        self.arrangement_clips = []
        self.can_be_armed = False
        self.__dict__.update(flags)


class Song(object):
    def __init__(self):
        self.clip = Clip()
        self.tracks = [Track("Pad", self.clip), Track("Bass", muted_via_solo=True), Track("Lead", is_frozen=True),
                       Track("Keys", muted_via_solo=False, is_frozen=False)]
        self.return_tracks = []
        self.master_track = Track("Main")
        self.tempo, self.signature_numerator, self.signature_denominator, self.is_playing = 120.0, 4, 4, False
        self.scenes, self.cue_points = [], []


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song):
    return make_inst(script_module, song)


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


LAUNCH = dict(track_index=0, clip_index=0, expected_name="Pad")


def test_launch_settings_are_set_and_read_back_by_name(inst, song):
    r = ok(run(inst, "set_clip_launch", launch_quantization="2 bars", launch_mode="Gate", legato=True, **LAUNCH))
    assert r["before"] == {"launch_quantization": "global", "launch_mode": "trigger", "legato": False}
    assert r["after"] == {"launch_quantization": "2 bars", "launch_mode": "gate", "legato": True}
    assert (song.clip.launch_quantization, song.clip.launch_mode, song.clip.legato) == (4, 1, True)


def test_one_setting_leaves_the_others_alone(inst, song):
    song.clip.launch_mode = 2
    ok(run(inst, "set_clip_launch", launch_quantization="bar", **LAUNCH))
    assert (song.clip.launch_quantization, song.clip.launch_mode) == (5, 2)


def test_bad_launch_values_change_nothing(inst, song):
    assert "launch_quantization must be one of" in err(run(inst, "set_clip_launch", launch_quantization="3 bars", legato=True, **LAUNCH))
    assert "launch_mode must be one of" in err(run(inst, "set_clip_launch", launch_mode="loop", **LAUNCH))
    assert "true or false" in err(run(inst, "set_clip_launch", legato="yes", **LAUNCH))
    assert "Give launch_quantization" in err(run(inst, "set_clip_launch", **LAUNCH))
    assert "expected_name" in err(run(inst, "set_clip_launch", track_index=0, clip_index=0, launch_mode="gate"))
    assert "not 'Wrong'" in err(run(inst, "set_clip_launch", launch_mode="gate", **dict(LAUNCH, expected_name="Wrong")))
    assert (song.clip.launch_quantization, song.clip.launch_mode, song.clip.legato) == (0, 0, False)


def test_get_clip_info_shows_the_launch_settings(inst, song):
    song.clip.launch_quantization, song.clip.launch_mode = 8, 3
    info = ok(run(inst, "get_clip_info", track_index=0, clip_index=0))
    assert info["launch_quantization"] == "quarter" and info["launch_mode"] == "repeat" and info["legato"] is False


def test_a_clip_that_does_not_expose_them_is_still_readable(inst, song):
    class Bare(Clip):
        launch_quantization = property(lambda self: 1 / 0, lambda self, v: None)
    song.tracks[0].clip_slots[0].clip = Bare()
    info = ok(run(inst, "get_clip_info", track_index=0, clip_index=0))
    assert "launch_mode" not in info and info["name"] == "Riff"


def test_the_overview_says_why_a_track_is_silent_only_when_true(inst):
    rows = {t["name"]: t for t in ok(run(inst, "get_tracks_overview"))["tracks"]}
    assert rows["Bass"]["muted_via_solo"] is True and "frozen" not in rows["Bass"]
    assert rows["Lead"]["frozen"] is True and "muted_via_solo" not in rows["Lead"]
    assert "muted_via_solo" not in rows["Keys"] and "frozen" not in rows["Keys"]


def test_the_tool_forwards_its_arguments(conn):
    call(server.set_clip_launch, None, 1, "Pad", 2, "bar", "gate", True)
    assert conn.sent[-1] == ("set_clip_launch", {"track_index": 1, "clip_index": 2, "expected_name": "Pad",
                                                 "launch_quantization": "bar", "launch_mode": "gate", "legato": True})
    assert "required" in call(server.set_clip_launch, None, 1, None)
    assert "set_clip_launch" in MODIFYING_TOOLS
