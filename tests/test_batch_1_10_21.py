"""1.10.21: start and end a take (record_into_slot, start_arrangement_record, stop_recording).

The fakes follow what Push 3 standalone, Live 12.4.6 did (2026-10-26): ClipSlot.fire takes
record_length in beats (the fallback is for a Live without the keyword: Boost.Python raises a TypeError
subclass for an unknown one), an empty slot fired on an armed track waits for the launch quantization
(is_triggered) and then records (is_recording), firing a recording slot ends the take, and
Song.record_mode is the Arrangement record button.
"""
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_batch_1_10_19 import FakeLive, err, ok, run
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


@pytest.fixture(autouse=True)
def live(monkeypatch):
    import sys
    fake = FakeLive()
    monkeypatch.setitem(sys.modules, "Live", fake)
    return fake


class Slot(object):
    def __init__(self, clip_name=None, takes_length=True):
        self.clip = types.SimpleNamespace(name=clip_name) if clip_name else None
        self.is_triggered = self.is_recording = False
        self.takes_length = takes_length
        self.fired, self.stopped = [], 0

    @property
    def has_clip(self):
        return self.clip is not None

    def fire(self, **kwargs):
        if kwargs and not self.takes_length:
            raise TypeError("fire() got an unexpected keyword argument")
        self.fired.append(kwargs)
        if self.is_recording:
            self.is_recording = False
        elif self.clip is None:
            self.is_triggered = True

    def stop(self):
        self.stopped += 1
        self.is_triggered = False


def routing(name):
    return types.SimpleNamespace(display_name=name)


class Track(object):
    def __init__(self, name, armed=False, can_be_armed=True, slots=3, input_type="Ext. In",
                 input_channel="1", monitoring=1, clips=()):
        self.name, self.arm, self.can_be_armed = name, armed, can_be_armed
        self.clip_slots = [Slot() for _ in range(slots)]
        self.input_routing_type, self.input_routing_channel = routing(input_type), routing(input_channel)
        self.current_monitoring_state = monitoring
        self.arrangement_clips = [types.SimpleNamespace(name=n, start_time=s, end_time=e) for n, s, e in clips]


class Song(object):
    def __init__(self):
        self.tracks = [Track("Drums", clips=[("Beat", 0.0, 32.0)]),
                       Track("Vox", armed=True, clips=[("Old take", 16.0, 24.0), ("Later", 64.0, 72.0)]),
                       Track("Group", can_be_armed=False)]
        self.signature_numerator, self.signature_denominator = 4, 4
        self.clip_trigger_quantization, self.midi_recording_quantization = 4, 0
        self.is_playing = self.record_mode = self.session_record = False
        self.back_to_arranger = self.loop = self.arrangement_overdub = False
        self.punch_in = self.punch_out = False
        self.loop_start, self.loop_length = 0.0, 16.0
        self.current_song_time = 0.0
        self.count_in_duration = 0

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    obj = make_inst(script_module, song)
    monkeypatch.setattr(script_module.time, "sleep", lambda s: None)
    obj.later = []

    def schedule_message(delay, callback):
        # tick 0 runs now (main-thread tasks); later ticks wait for pump()
        if delay == 0:
            callback()
        else:
            obj.later.append(callback)

    obj.schedule_message = schedule_message
    return obj


def pump(inst):
    pending, inst.later = inst.later, []
    for callback in pending:
        callback()


VOX = dict(track_index=1, clip_index=0, expected_name="Vox")


# --------------------------------------------------------------------------- record_into_slot

def test_a_slot_take_is_previewed_by_default(inst, song):
    r = ok(run(inst, "record_into_slot", length_bars=2, **VOX))
    assert r["dry_run"] is True and r["applied"] is False
    assert r["input"] == {"monitoring": "auto", "input_type": "Ext. In", "input_channel": "1"}
    assert r["length_beats"] == 8.0 and r["launch_quantization"] == "bar" and r["warnings"] == []
    assert song.tracks[1].clip_slots[0].fired == [] and "after" not in r


def test_a_slot_take_fires_with_its_length_in_beats(inst, song):
    song.signature_numerator, song.signature_denominator = 6, 8
    r = ok(run(inst, "record_into_slot", length_bars=2, confirm=True, **VOX))
    assert song.tracks[1].clip_slots[0].fired == [{"record_length": 6.0}]
    assert r["applied"] is True and r["record_length_applied"] is True
    assert r["after"]["triggered"] is True and r["after"]["has_clip"] is False


def test_without_a_length_the_take_runs_until_stopped(inst, song):
    r = ok(run(inst, "record_into_slot", confirm=True, **VOX))
    assert song.tracks[1].clip_slots[0].fired == [{}] and r["length_beats"] is None
    assert "record_length_applied" not in r


def test_a_live_without_record_length_falls_back_and_says_so(inst, song):
    song.tracks[1].clip_slots[0] = Slot(takes_length=False)
    r = ok(run(inst, "record_into_slot", length_bars=1, confirm=True, **VOX))
    assert song.tracks[1].clip_slots[0].fired == [{}] and r["record_length_applied"] is False
    assert any("stop_recording" in w for w in r["warnings"])


def test_a_slot_take_never_records_over_a_clip_or_on_an_unarmed_track(inst, song):
    song.tracks[1].clip_slots[0] = Slot("Verse take")
    assert "already holds 'Verse take'" in err(run(inst, "record_into_slot", confirm=True, **VOX))
    assert song.tracks[1].clip_slots[0].fired == []
    msg = err(run(inst, "record_into_slot", track_index=0, clip_index=0, expected_name="Drums", confirm=True))
    assert "not armed" in msg and "set_track_arm" in msg
    assert "cannot record" in err(run(inst, "record_into_slot", track_index=2, clip_index=0, expected_name="Group"))


def test_bad_slot_arguments_are_refused(inst, song):
    assert "not 'Bass'" in err(run(inst, "record_into_slot", **dict(VOX, expected_name="Bass")))
    assert "expected_name is required" in err(run(inst, "record_into_slot", track_index=1, clip_index=0))
    assert "out of range" in err(run(inst, "record_into_slot", **dict(VOX, clip_index=9)))
    assert "length_bars must be" in err(run(inst, "record_into_slot", length_bars=0, **VOX))
    assert "length_bars must be" in err(run(inst, "record_into_slot", length_bars=500, **VOX))
    assert "confirm must be true or false" in err(run(inst, "record_into_slot", confirm="yes", **VOX))
    assert song.tracks[1].clip_slots[0].fired == []


def test_a_silent_input_and_open_monitoring_are_warned_about(inst, song):
    vox = song.tracks[1]
    vox.input_routing_type, vox.current_monitoring_state = routing("No Input"), 0
    warnings = ok(run(inst, "record_into_slot", **VOX))["warnings"]
    assert any("No Input" in w for w in warnings) and any("headphones" in w for w in warnings)


# --------------------------------------------------------------------------- start_arrangement_record

def test_an_arrangement_take_is_previewed_with_what_it_records_over(inst, song):
    r = ok(run(inst, "start_arrangement_record", start_time=16.0, end_time=48.0))
    assert r["dry_run"] is True and [t["name"] for t in r["armed_tracks"]] == ["Vox"]
    assert [c["name"] for c in r["armed_tracks"][0]["records_over"]] == ["Old take"]
    assert song.record_mode is False and song.is_playing is False and song.current_song_time == 0.0


def test_an_arrangement_take_starts_and_stops_itself_at_end_time(inst, song):
    r = ok(run(inst, "start_arrangement_record", start_time=16.0, end_time=48.0, confirm=True))
    assert r["applied"] is True and r["after"] == {"recording": True, "transport_playing": True, "playhead": 16.0}
    song.current_song_time = 40.0
    pump(inst)
    assert song.record_mode is True and len(inst.later) == 1
    song.current_song_time = 48.1
    pump(inst)
    assert song.record_mode is False and inst.later == [] and song.is_playing is True


def test_without_end_time_nothing_is_scheduled(inst, song):
    song.current_song_time = 8.0
    r = ok(run(inst, "start_arrangement_record", confirm=True))
    assert r["start_time"] == 8.0 and song.record_mode is True and inst.later == []


def test_a_take_ended_by_hand_or_restarted_stops_the_old_poll(inst, song):
    ok(run(inst, "start_arrangement_record", end_time=48.0, confirm=True))
    song.record_mode = False
    pump(inst)
    assert inst.later == []
    ok(run(inst, "start_arrangement_record", end_time=48.0, confirm=True))
    assert len(inst.later) == 1
    ok(run(inst, "stop_recording"))
    # a take started by hand afterwards is not stopped by the old poll
    song.record_mode, song.current_song_time = True, 50.0
    pump(inst)
    assert song.record_mode is True and inst.later == []


def test_arrangement_record_refusals(inst, song):
    assert "end_time" in err(run(inst, "start_arrangement_record", start_time=16.0, end_time=8.0))
    assert "0 or later" in err(run(inst, "start_arrangement_record", start_time=-1.0))
    assert "longer than 256 bars" in err(run(inst, "start_arrangement_record", start_time=0.0, end_time=5000.0))
    song.record_mode = True
    assert "already on" in err(run(inst, "start_arrangement_record", confirm=True))
    song.record_mode, song.tracks[1].arm = False, False
    assert "No track is armed" in err(run(inst, "start_arrangement_record", confirm=True))
    assert song.is_playing is False


def test_session_playback_and_a_short_loop_are_warned_about(inst, song):
    song.back_to_arranger, song.loop = True, True
    warnings = ok(run(inst, "start_arrangement_record", start_time=0.0, end_time=32.0))["warnings"]
    assert any("back_to_arrangement" in w for w in warnings)
    assert any("loop ends at 16.0" in w for w in warnings)


# --------------------------------------------------------------------------- stop_recording

def test_stop_ends_and_cancels_every_take(inst, song):
    recording, waiting = song.tracks[1].clip_slots[0], song.tracks[1].clip_slots[1]
    recording.is_recording, waiting.is_triggered = True, True
    song.record_mode = song.session_record = song.is_playing = True
    r = ok(run(inst, "stop_recording", stop_transport=True))
    assert r["slots_ended"] == [{"track_index": 1, "track_name": "Vox", "clip_index": 0}]
    assert r["slots_cancelled"] == [{"track_index": 1, "track_name": "Vox", "clip_index": 1}]
    assert recording.fired == [{}] and waiting.stopped == 1 and r["was_recording"] is True
    assert r["after"] == {"arrangement_record": False, "session_record": False, "transport_playing": False}


def test_stop_with_nothing_recording_changes_nothing(inst, song):
    song.is_playing = True
    r = ok(run(inst, "stop_recording"))
    assert r["was_recording"] is False and r["after"]["transport_playing"] is True
    assert "true or false" in err(run(inst, "stop_recording", stop_transport="yes"))


# ------------------------------------------------------------------------------ tools

def test_the_tools_forward_their_arguments_and_preview(conn):
    out = call(server.record_into_slot, None, 1, 0, "Vox", 4)
    assert out.startswith("NOT RECORDING")
    assert conn.sent[-1] == ("record_into_slot", {"track_index": 1, "clip_index": 0, "expected_name": "Vox",
                                                  "confirm": False, "length_bars": 4})
    call(server.record_into_slot, None, 1, 0, "Vox", None, True)
    assert "length_bars" not in conn.sent[-1][1] and conn.sent[-1][1]["confirm"] is True
    assert "required" in call(server.record_into_slot, None, 1, 0, None)
    assert call(server.start_arrangement_record, None, 16.0, 48.0).startswith("NOT RECORDING")
    assert conn.sent[-1] == ("start_arrangement_record", {"confirm": False, "start_time": 16.0, "end_time": 48.0})
    call(server.start_arrangement_record, None, None, None, True)
    assert conn.sent[-1] == ("start_arrangement_record", {"confirm": True})
    call(server.stop_recording, None, True)
    assert conn.sent[-1] == ("stop_recording", {"stop_transport": True})


def test_the_recording_commands_are_capabilities_and_modifying_tools(script_module):
    for name in ("record_into_slot", "start_arrangement_record", "stop_recording"):
        assert name in script_module.SCRIPT_CAPABILITIES and name in MODIFYING_TOOLS
