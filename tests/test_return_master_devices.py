"""Device parameters and track info for return tracks and the master (track_type)."""
import json
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Param(object):
    def __init__(self, name, lo, hi, value):
        self.name, self.min, self.max, self.value = name, lo, hi, value


class Device(object):
    def __init__(self, name, cls, params):
        self.name, self.class_name, self.parameters = name, cls, params


def mixer():
    return types.SimpleNamespace(volume=Param("Volume", 0, 1, 0.85), panning=Param("Pan", -1, 1, 0.0))


def track(name, devices):
    return types.SimpleNamespace(name=name, devices=devices, mixer_device=mixer(),
                                 has_audio_input=True, has_midi_input=False)


class Song(object):
    def __init__(self):
        self.tracks = [track("Bass", [Device("EQ", "Eq8", [Param("Gain", -15, 15, 0)])])]
        self.return_tracks = [track("A-Reverb", [Device("Reverb", "Reverb", [Param("Decay", 0.2, 60, 2.0), Param("Dry/Wet", 0, 1, 1.0)])]),
                              track("B-Delay", [Device("Delay", "Delay", [Param("Feedback", 0, 1, 0.3)])])]
        self.master_track = track("Main", [Device("Limiter", "Limiter", [Param("Gain", -24, 24, 0.0)])])


@pytest.fixture
def inst(script_module):
    obj = make_inst(script_module, Song())
    obj._get_device_type = lambda d: "audio_effect"
    obj._serialize_device = lambda device, index, **kw: {
        "index": index, "name": device.name,
        "parameters": [{"index": i, "name": p.name, "value": p.value} for i, p in enumerate(device.parameters)]}
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_a_return_track_lists_its_devices_and_mixer(inst):
    info = ok(run(inst, "get_track_info", track_index=1, track_type="return"))
    assert info["name"] == "B-Delay" and info["track_type"] == "return"
    assert info["devices"][0]["name"] == "Delay" and info["volume"] == 0.85


def test_the_master_ignores_the_index(inst):
    info = ok(run(inst, "get_track_info", track_index=7, track_type="master"))
    assert info["name"] == "Main" and info["devices"][0]["name"] == "Limiter" and info["index"] is None


def test_parameters_of_a_return_device_are_read_and_a_regular_track_still_works(inst):
    def names(result):
        return json.dumps(result)
    assert "Decay" in names(ok(run(inst, "get_device_parameters", track_index=0, device_index=0,
                                   track_type="return")))
    assert "Gain" in names(ok(run(inst, "get_device_parameters", track_index=0, device_index=0)))
    assert "Decay" not in names(ok(run(inst, "get_device_parameters", track_index=0, device_index=0)))
    assert "Feedback" in names(ok(run(inst, "get_device_parameters", track_index=1, device_index=0,
                                      track_type="return")))
    assert "Limiter" in names(ok(run(inst, "get_device_parameters", track_index=0, device_index=0,
                                     track_type="master")))


def test_a_return_device_parameter_is_set_and_reports_the_old_value(inst):
    result = ok(run(inst, "set_device_parameter", track_index=0, device_index=0, parameter_index=0,
                    value=4.5, track_type="return"))
    assert (result["name"], result["old_value"], result["value"], result["track_type"]) == ("Decay", 2.0, 4.5, "return")
    assert inst._song.return_tracks[0].devices[0].parameters[0].value == 4.5
    assert inst._song.tracks[0].devices[0].parameters[0].value == 0      # the regular track's EQ is untouched


def test_a_master_device_parameter_is_set(inst):
    result = ok(run(inst, "set_device_parameter", track_index=0, device_index=0, parameter_index=0,
                    value=-3.0, track_type="master"))
    assert result["name"] == "Gain" and result["value"] == -3.0
    assert inst._song.master_track.devices[0].parameters[0].value == -3.0


@pytest.mark.parametrize("kwargs,needle", [
    (dict(track_index=5, track_type="return"), "return index 5 out of range"),
    (dict(track_index=0, track_type="sideways"), "Unknown track_type"),
    (dict(track_index=0, device_index=3, track_type="return"), "Device index out of range"),
    (dict(track_index=0, value=99.0, track_type="return"), "outside the range"),
])
def test_bad_return_or_master_targets_change_nothing(inst, kwargs, needle):
    args = dict(device_index=0, parameter_index=0, value=1.0)
    args.update(kwargs)
    assert needle in err(run(inst, "set_device_parameter", **args))
    assert inst._song.return_tracks[0].devices[0].parameters[0].value == 2.0


def test_tools_forward_track_type_only_when_it_is_not_the_default(conn):
    conn.response = {"name": "x", "old_value": 1, "value": 2}
    call(server.set_device_parameter, None, 0, 0, 1, 0.5, "return")
    assert conn.sent[-1][1]["track_type"] == "return"
    call(server.set_device_parameter, None, 0, 0, 1, 0.5)
    assert "track_type" not in conn.sent[-1][1]
    call(server.get_device_parameters, None, 0, 0, track_type="master")
    assert conn.sent[-1][1]["track_type"] == "master"
    call(server.get_track_info, None, 1, "return")
    assert conn.sent[-1] == ("get_track_info", {"track_index": 1, "track_type": "return"})


# ------------------------------------------------- monitoring and duplicating

class MonTrack(object):
    def __init__(self, name, state=1):
        self.name, self.current_monitoring_state, self.devices = name, state, []
        self.clip_slots = [types.SimpleNamespace(has_clip=True)]


class MonSong(object):
    def __init__(self, cap=8):
        self.tracks = [MonTrack("Guitar"), MonTrack("Bass")]
        self.cap = cap

    def duplicate_track(self, index):
        if len(self.tracks) >= self.cap:
            raise RuntimeError("Couldn't duplicate track")
        self.tracks.insert(index + 1, MonTrack(self.tracks[index].name + " copy"))


def test_monitoring_is_set_and_reports_before_and_after(script_module):
    inst = make_inst(script_module, MonSong())
    result = ok(run(inst, "set_track_monitoring", track_index=0, state="IN", expected_name="Guitar"))
    assert (result["previous"], result["state"]) == ("auto", "in")
    assert inst._song.tracks[0].current_monitoring_state == 0
    assert ok(run(inst, "set_track_monitoring", track_index=1, state="off"))["state"] == "off"


@pytest.mark.parametrize("kwargs,needle", [
    (dict(state="loud"), "state must be"),
    (dict(state="in", expected_name="Other"), "not 'Other'"),
    (dict(state="in", track_index=9), "out of range"),
])
def test_bad_monitoring_changes_nothing(script_module, kwargs, needle):
    inst = make_inst(script_module, MonSong())
    args = dict(track_index=0)
    args.update(kwargs)
    assert needle in err(run(inst, "set_track_monitoring", **args))
    assert inst._song.tracks[0].current_monitoring_state == 1


class GroupTrack(object):
    """hasattr is true for the monitoring state of a group track, but reading it raises."""
    name, is_foldable, can_be_armed, devices = "Drums", True, False, []
    mute, solo, color_index, group_track = False, False, 4, None
    clip_slots = []
    mixer_device = types.SimpleNamespace(volume=Param("Volume", 0, 1, 0.85), panning=Param("Pan", -1, 1, 0.0))

    @property
    def current_monitoring_state(self):
        raise RuntimeError("Main and Return Tracks have no monitoring state!")


def test_a_group_track_does_not_break_the_overview_or_the_monitoring_tool(script_module):
    song = Song()
    for plain in song.tracks + song.return_tracks + [song.master_track]:
        plain.clip_slots, plain.arrangement_clips, plain.mute, plain.solo = [], [], False, False
        plain.color_index, plain.group_track, plain.can_be_armed, plain.is_foldable = 1, None, False, False
    song.tracks.append(GroupTrack())
    song.scenes, song.cue_points, song.tempo, song.is_playing = [], [], 120.0, False
    song.signature_numerator = song.signature_denominator = 4
    inst = make_inst(script_module, song)
    inst._get_device_type = lambda d: "audio_effect"
    overview = ok(run(inst, "get_tracks_overview"))
    group = overview["tracks"][-1]
    assert group["kind"] == "group" and "monitoring" not in group
    assert "has no monitoring state" in err(run(inst, "set_track_monitoring", track_index=1, state="in"))
    assert overview["tracks"][0]["kind"] == "audio"


def test_a_track_without_monitoring_is_refused(script_module):
    song = MonSong()
    del song.tracks[0].__dict__["current_monitoring_state"]
    assert "no monitoring state" in err(run(make_inst(script_module, song), "set_track_monitoring",
                                            track_index=0, state="in"))


def test_duplicate_track_puts_the_copy_after_the_original(script_module):
    inst = make_inst(script_module, MonSong())
    result = ok(run(inst, "duplicate_track", track_index=0, expected_name="Guitar"))
    assert result["new_track_index"] == 1 and result["new_track_name"] == "Guitar copy"
    assert [t.name for t in inst._song.tracks] == ["Guitar", "Guitar copy", "Bass"]


def test_duplicate_track_at_the_lite_cap_changes_nothing_and_says_why(script_module):
    inst = make_inst(script_module, MonSong(cap=2))
    message = err(run(inst, "duplicate_track", track_index=0, expected_name="Guitar"))
    assert "Live Lite allows 8 tracks" in message and len(inst._song.tracks) == 2


def test_duplicate_track_needs_the_name(script_module):
    inst = make_inst(script_module, MonSong())
    assert "not 'Other'" in err(run(inst, "duplicate_track", track_index=0, expected_name="Other"))
    assert "expected_name is required" in err(run(inst, "duplicate_track", track_index=0, expected_name=None))
    assert len(inst._song.tracks) == 2


def test_monitoring_and_duplicate_tools(conn):
    conn.response = {"state": "in"}
    call(server.set_track_monitoring, None, 0, "in")
    assert conn.sent[-1] == ("set_track_monitoring", {"track_index": 0, "state": "in"})
    call(server.duplicate_track, None, 0, "Guitar")
    assert conn.sent[-1] == ("duplicate_track", {"track_index": 0, "expected_name": "Guitar"})
    assert "required" in call(server.duplicate_track, None, 0, None)
