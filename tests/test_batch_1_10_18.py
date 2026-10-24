"""1.10.18: A/B compare, clip automation overview and clear, crop, take lanes, group fold, UI state,
re-enable automation, capture MIDI, input meters, and the status fields.

The fakes follow what Live 12.4 Lite did (2026-10-24): save_preset_to_compare_ab_slot copies the
current settings into the other slot and is_using_compare_preset_b swaps; clip.automation_envelopes
lists envelopes that each have .parameter; fold_state is True when folded.
"""
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Param(object):
    is_quantized = False

    def __init__(self, name, value=0.5):
        self.name, self.min, self.max, self.value = name, 0.0, 1.0, value


class ABDevice(object):
    class_name = "AutoFilter2"

    def __init__(self, name="Auto Filter"):
        self.name = name
        self.can_compare_ab = True
        self._slots = {"a": 0.5, "b": None}
        self._on_b = False
        self.parameters = [Param("Frequency", 0.5)]
        self.saved = 0

    @property
    def is_using_compare_preset_b(self):
        return self._on_b

    @is_using_compare_preset_b.setter
    def is_using_compare_preset_b(self, value):
        here, there = ("b", "a") if self._on_b else ("a", "b")
        self._slots[here] = self.parameters[0].value
        self._on_b = bool(value)
        now = "b" if self._on_b else "a"
        if now != here and self._slots[now] is not None:
            self.parameters[0].value = self._slots[now]

    def save_preset_to_compare_ab_slot(self):
        self.saved += 1
        self._slots["b" if not self._on_b else "a"] = self.parameters[0].value


class Plain(object):
    name, class_name, can_compare_ab, parameters = "Tuner", "Tuner", False, []


class Envelope(object):
    def __init__(self, parameter):
        self.parameter = parameter


class Clip(object):
    is_midi_clip, is_audio_clip, looping = True, False, True
    name = "Riff"
    loop_start, loop_end, start_marker, end_marker, length = 0.0, 4.0, 0.0, 8.0, 4.0
    start_time, end_time = 0.0, 4.0
    is_arrangement_clip = False

    def __init__(self, envelopes=()):
        self.automation_envelopes = list(envelopes)
        self.cropped = 0

    def clear_all_envelopes(self):
        self.automation_envelopes = []

    def crop(self):
        self.cropped += 1
        self.length = 4.0 if self.looping else 8.0


class Lane(object):
    def __init__(self, name, clips=()):
        self.name, self.arrangement_clips = name, list(clips)


class Track(object):
    def __init__(self, name, devices=(), clip=None, group=False):
        self.name, self.devices = name, list(devices)
        self.clip_slots = [types.SimpleNamespace(has_clip=clip is not None, clip=clip)]
        self.arrangement_clips = []
        self.mixer_device = types.SimpleNamespace(volume=Param("Volume", 0.85), panning=Param("Pan", 0.0),
                                                  sends=[Param("Send A"), Param("Send B")])
        self.is_foldable = group
        self.fold_state = False
        self.take_lanes = [] if group else [Lane("Lane")]
        self.has_audio_input = True
        self.view = types.SimpleNamespace(selected_device=None)

    def create_take_lane(self):
        self.take_lanes.append(Lane("Lane %d" % (len(self.take_lanes) + 1)))


class Song(object):
    def __init__(self):
        self.ab = ABDevice()
        self.volume_param = None
        self.clip = Clip()
        self.pad = Track("Pad", [self.ab, Plain()], self.clip)
        self.clip.automation_envelopes = [Envelope(self.pad.mixer_device.volume),
                                          Envelope(self.ab.parameters[0]),
                                          Envelope(self.pad.mixer_device.sends[1])]
        self.group = Track("Backing", group=True)
        self.tracks = [self.pad, self.group]
        self.return_tracks = [Track("A-Reverb")]
        self.master_track = Track("Main")
        self.scenes = [types.SimpleNamespace(name="One"), types.SimpleNamespace(name="Two")]
        self.view = types.SimpleNamespace(selected_track=self.pad, selected_scene=self.scenes[0], detail_clip=None,
                                          selected_parameter=None, follow_song=False, draw_mode=False,
                                          highlighted_clip_slot=None, selected_device_called=None)
        self.view.select_device = lambda d: setattr(self.view, "selected_device_called", d)
        self.can_capture_midi = False
        self.re_enable_automation_enabled = True
        self.captured = []
        self.last_event_time, self.punch_in, self.punch_out = 96.0, False, True
        self.arrangement_overdub, self.record_mode, self.count_in_duration = False, False, 1

    def re_enable_automation(self):
        self.re_enable_automation_enabled = False

    def capture_midi(self, destination):
        self.captured.append(destination)
        self.can_capture_midi = False


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song):
    obj = make_inst(script_module, song)
    views = {"Arranger": True, "Session": False, "Detail": True, "Detail/Clip": False,
             "Detail/DeviceChain": True, "Browser": False}
    obj.focused = []
    app_view = types.SimpleNamespace(focused_document_view="Arranger", is_view_visible=lambda n: views[n],
                                     focus_view=lambda n: obj.focused.append(n))
    obj.application = lambda: types.SimpleNamespace(view=app_view)
    song.view.selected_track = song.pad
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


AB = dict(track_index=0, device_index=0, expected_name="Pad", expected_device_name="Auto Filter")


# ------------------------------------------------------------------ A/B compare

def test_ab_save_then_switch_keeps_each_slot(inst, song):
    assert ok(run(inst, "compare_device_ab", **AB))["now_on"] == "A"
    ok(run(inst, "compare_device_ab", action="save", **AB))
    song.ab.parameters[0].value = 0.9
    r = ok(run(inst, "compare_device_ab", action="switch", **AB))
    assert (r["was_on"], r["now_on"]) == ("A", "B") and song.ab.parameters[0].value == 0.5
    ok(run(inst, "compare_device_ab", action="use_a", **AB))
    assert song.ab.parameters[0].value == 0.9


def test_ab_refuses_a_device_without_it_a_wrong_name_and_an_unknown_action(inst):
    assert "no A/B" in err(run(inst, "compare_device_ab", **dict(AB, device_index=1, expected_device_name="Tuner")))
    assert "not 'Wrong'" in err(run(inst, "compare_device_ab", **dict(AB, expected_name="Wrong")))
    assert "action must be" in err(run(inst, "compare_device_ab", action="toggle", **AB))


# -------------------------------------------------------- clip automation overview

def test_listing_names_where_each_automated_parameter_lives(inst):
    r = ok(run(inst, "list_clip_envelopes", track_index=0, clip_index=0))
    rows = {e["parameter"]: e for e in r["envelopes"]}
    assert r["count"] == 3 and rows["volume"]["owner"] == "mixer" and rows["send B"]["owner"] == "mixer"
    assert rows["Frequency"]["device_index"] == 0 and rows["Frequency"]["device_name"] == "Auto Filter"


def test_clearing_everything_previews_first_and_needs_the_track_name(inst, song):
    r = ok(run(inst, "clear_all_clip_envelopes", track_index=0, clip_index=0, expected_name="Pad"))
    assert r["applied"] is False and len(r["would_remove"]) == 3 and len(song.clip.automation_envelopes) == 3
    r = ok(run(inst, "clear_all_clip_envelopes", track_index=0, clip_index=0, expected_name="Pad", confirm=True))
    assert r["applied"] is True and r["remaining"] == 0
    assert "expected_name" in err(run(inst, "clear_all_clip_envelopes", track_index=0, clip_index=0))
    assert "not 'Other'" in err(run(inst, "clear_all_clip_envelopes", track_index=0, clip_index=0, expected_name="Other",
                                    confirm=True))


# ------------------------------------------------------------------------- crop

def test_crop_previews_what_is_kept_and_then_crops(inst, song):
    r = ok(run(inst, "crop_clip", track_index=0, clip_index=0, expected_name="Pad"))
    assert (r["keeps_from"], r["keeps_to"], r["looping"], r["applied"]) == (0.0, 4.0, True, False) and song.clip.cropped == 0
    r = ok(run(inst, "crop_clip", track_index=0, clip_index=0, expected_name="Pad", confirm=True))
    assert r["applied"] is True and song.clip.cropped == 1


def test_a_clip_that_does_not_loop_is_cropped_to_its_markers(inst, song):
    song.clip.looping = False
    r = ok(run(inst, "crop_clip", track_index=0, clip_index=0, expected_name="Pad"))
    assert (r["keeps_from"], r["keeps_to"]) == (0.0, 8.0)


def test_crop_needs_the_right_track_name(inst, song):
    assert "expected_name" in err(run(inst, "crop_clip", track_index=0, clip_index=0, confirm=True))
    assert "not 'Bass'" in err(run(inst, "crop_clip", track_index=0, clip_index=0, expected_name="Bass", confirm=True))
    assert song.clip.cropped == 0


# ------------------------------------------------------------------ take lanes, fold

def test_take_lanes_are_read_and_one_is_added(inst, song):
    song.pad.take_lanes[0].arrangement_clips = [types.SimpleNamespace(name="take 1", start_time=0.0, end_time=8.0,
                                                                      is_audio_clip=True)]
    r = ok(run(inst, "get_take_lanes", track_index=0))
    assert r["lane_count"] == 1 and r["lanes"][0]["clips"][0]["name"] == "take 1"
    r = ok(run(inst, "create_take_lane", track_index=0, expected_name="Pad"))
    assert (r["lanes_before"], r["lanes_after"]) == (1, 2)
    assert "group track" in err(run(inst, "get_take_lanes", track_index=1))
    assert "not 'Pad2'" in err(run(inst, "create_take_lane", track_index=0, expected_name="Pad2"))


def test_only_a_group_folds_and_it_needs_a_real_bool(inst, song):
    r = ok(run(inst, "set_track_fold", track_index=1, expected_name="Backing", folded=True))
    assert r["was_folded"] is False and r["folded"] is True and song.group.fold_state is True
    assert "not a group" in err(run(inst, "set_track_fold", track_index=0, expected_name="Pad", folded=True))
    assert "true or false" in err(run(inst, "set_track_fold", track_index=1, expected_name="Backing", folded="yes"))


# ------------------------------------------------------------------------- UI

def test_ui_state_reports_the_selection(inst, song):
    r = ok(run(inst, "get_ui_state"))
    assert r["focused_view"] == "Arranger" and r["selected_track"] == {"track_type": "track", "index": 0, "name": "Pad"}
    assert r["selected_scene"] == 0 and r["detail_clip"] is None and "Detail/Clip" not in r["open_views"]


def test_a_field_that_cannot_be_read_does_not_stop_the_others(inst, song):
    song.view.follow_song = property(lambda self: 1 / 0)

    class Boom(object):
        @property
        def draw_mode(self):
            raise RuntimeError("no")

    song.view = types.SimpleNamespace(**dict(vars(song.view)))
    del song.view.draw_mode
    r = ok(run(inst, "get_ui_state"))
    assert r["draw_mode"] is None and r["selected_track"]["name"] == "Pad"


def test_show_in_ui_selects_and_focuses(inst, song):
    r = ok(run(inst, "show_in_ui", track_index=0, scene_index=1, clip_index=0, view_name="detail/clip"))
    assert song.view.selected_scene is song.scenes[1] and song.view.detail_clip is song.clip
    assert inst.focused == ["Detail/Clip"] and r["did"][-1] == "view Detail/Clip"
    assert r["detail_clip"]["track_name"] == "Pad" and r["detail_clip"]["clip_index"] == 0
    ok(run(inst, "show_in_ui", track_index=0, device_index=0))
    assert song.view.selected_device_called is song.ab


def test_show_in_ui_can_show_a_clips_envelope_parameter(inst, song):
    shown = []
    song.clip.view = types.SimpleNamespace(show_envelope=lambda: shown.append("show"),
                                           select_envelope_parameter=lambda p: shown.append(p.name))
    r = ok(run(inst, "show_in_ui", track_index=0, clip_index=0, envelope_parameter="volume"))
    assert shown == ["show", "Volume"] and "envelope 'Volume'" in r["did"]


def test_show_in_ui_refuses_nonsense(inst):
    assert "Give something" in err(run(inst, "show_in_ui"))
    assert "view_name must be" in err(run(inst, "show_in_ui", view_name="Foo"))
    assert "scene_index out of range" in err(run(inst, "show_in_ui", scene_index=9))
    assert "needs a regular track_index" in err(run(inst, "show_in_ui", clip_index=0))
    assert "needs a regular track_index" in err(run(inst, "show_in_ui", track_index=0, track_type="return", clip_index=0))
    assert "device_index needs" in err(run(inst, "show_in_ui", device_index=0))


def test_a_return_track_is_selected_by_type(inst, song):
    song.view.selected_track = song.return_tracks[0]
    assert ok(run(inst, "get_ui_state"))["selected_track"] == {"track_type": "return", "index": 0, "name": "A-Reverb"}


# ----------------------------------------------------- automation, capture, status

def test_re_enable_automation_only_acts_when_needed(inst, song):
    assert ok(run(inst, "re_enable_automation")) == {"was_needed": True, "needed_now": False}
    assert ok(run(inst, "re_enable_automation")) == {"was_needed": False, "needed_now": False}


def test_capture_midi_refuses_without_material_and_checks_the_destination(inst, song, script_module, monkeypatch):
    assert "Nothing to capture" in err(run(inst, "capture_midi"))
    song.can_capture_midi = True
    assert "destination must be" in err(run(inst, "capture_midi", destination="tape"))
    live = types.ModuleType("Live")
    live.Song = types.SimpleNamespace(CaptureDestination=types.SimpleNamespace(auto=0, session=1, arrangement=2))
    monkeypatch.setitem(__import__("sys").modules, "Live", live)
    r = ok(run(inst, "capture_midi", destination="session"))
    assert r["captured"] is True and song.captured == [1]


def test_live_status_carries_the_song_state(inst, song):
    app = types.SimpleNamespace(
        get_version_string=lambda: "12.4.7", get_build_id=lambda: "b", get_variant=lambda: "Lite",
        average_process_usage=0.1, peak_process_usage=0.2, unavailable_features=[], open_dialog_count=0)
    inst.application = lambda: app
    song.is_playing, song.tempo, song.exclusive_arm, song.exclusive_solo = False, 120.0, True, True
    song.return_tracks = []
    r = ok(run(inst, "get_live_status"))
    assert r["last_event_time"] == 96.0 and r["punch_out"] is True and r["automation_overridden"] is True
    assert r["can_capture_midi"] is False and r["count_in_duration"] == 1


# ------------------------------------------------------------------- input meters

class Clock(object):
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_input_meters_read_the_input_side_and_skip_returns_and_master(script_module, monkeypatch):
    monkeypatch.setattr(script_module, "time", Clock())
    audio = types.SimpleNamespace(name="Guitar", has_audio_input=True, input_meter_left=0.6, input_meter_right=0.4,
                                  output_meter_left=0.1, output_meter_right=0.1)
    midi = types.SimpleNamespace(name="Keys", has_audio_input=False, input_meter_level=0.3,
                                 output_meter_left=0.1, output_meter_right=0.1)
    song = types.SimpleNamespace(is_playing=False, tracks=[audio, midi],
                                 return_tracks=[types.SimpleNamespace(name="A", output_meter_left=0.0, output_meter_right=0.0)],
                                 master_track=types.SimpleNamespace(name="Main", output_meter_left=0.0, output_meter_right=0.0))
    obj = make_inst(script_module, song)
    obj.running = True
    r = ok(obj._process_command({"type": "get_meters", "params": {"seconds": 1.0, "hz": 2, "source": "input"}}))
    assert r["source"] == "input" and r["tracks"][0]["peak_left"] == 0.6 and r["tracks"][0]["peak_right"] == 0.4
    assert r["tracks"][1]["peak"] == 0.3
    assert r["return_tracks"][0]["meter_available"] is False and r["master"]["meter_available"] is False
    out = ok(obj._process_command({"type": "get_meters", "params": {"seconds": 1.0, "hz": 2}}))
    assert out["source"] == "output" and out["tracks"][0]["peak"] == pytest.approx(0.1)
    assert "source must be" in err(obj._process_command({"type": "get_meters", "params": {"source": "tape"}}))


# ------------------------------------------------------------------------ tools

def test_the_tools_forward_their_arguments(conn):
    call(server.compare_device_ab, None, 0, 1, "Pad", "EQ", "save", "return")
    assert conn.sent[-1] == ("compare_device_ab", {"track_index": 0, "device_index": 1, "expected_name": "Pad",
                                                   "expected_device_name": "EQ", "action": "save", "track_type": "return"})
    call(server.list_clip_envelopes, None, 2, 3)
    assert conn.sent[-1] == ("list_clip_envelopes", {"track_index": 2, "clip_index": 3})
    out = call(server.clear_all_clip_envelopes, None, 0, "Pad", 1)
    assert "NOT REMOVED" in out and conn.sent[-1][1]["confirm"] is False
    assert "NOT CROPPED" in call(server.crop_clip, None, 0, "Pad", 0, 4.0)
    assert conn.sent[-1][1]["clip_start_time"] == 4.0
    call(server.get_take_lanes, None, 3)
    call(server.create_take_lane, None, 3, "Guitar")
    call(server.set_track_fold, None, 4, "Backing", True)
    assert conn.sent[-1] == ("set_track_fold", {"track_index": 4, "expected_name": "Backing", "folded": True})
    call(server.get_ui_state, None)
    call(server.show_in_ui, None, 1, "track", None, 0, None, "Detail/Clip")
    assert conn.sent[-1] == ("show_in_ui", {"track_type": "track", "track_index": 1, "clip_index": 0,
                                            "view_name": "Detail/Clip"})
    call(server.re_enable_automation, None)
    call(server.capture_midi, None, "session")
    assert conn.sent[-1] == ("capture_midi", {"destination": "session"})


def test_the_names_are_required_and_the_tools_are_listed_as_modifying(conn):
    assert "required" in call(server.compare_device_ab, None, 0, 0, None, "x")
    assert "required" in call(server.clear_all_clip_envelopes, None, 0, None)
    assert "required" in call(server.crop_clip, None, 0, None)
    assert "required" in call(server.create_take_lane, None, 0, None)
    assert "required" in call(server.set_track_fold, None, 0, None, True)
    for name in ("compare_device_ab", "clear_all_clip_envelopes", "crop_clip", "create_take_lane", "set_track_fold",
                 "re_enable_automation", "capture_midi"):
        assert name in MODIFYING_TOOLS
    assert "source must be" in call(server.get_meters, None, 1.0, 10, "tape")
    conn.response = {"tracks": []}
    call(server.get_meters, None, 1.0, 10, "input")
    assert conn.sent[-1][1]["source"] == "input"
