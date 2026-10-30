"""1.10.26: playhead moves made while stopped stick, start_playback(at_beat), no Stop while stopped.

The fake Song follows what Push 3 standalone, Live 12.4.15 did (2026-10-30, Main down): a move made
while stopped reads back and Play starts there, until a Stop is pressed while already stopped. That
Stop sends the playhead home, and from then on Play starts at beat 0 whatever was set while stopped
(even a second later). A move made while playing always holds, also right after Play.
"""
import types

import pytest

import MCP_Server.script_handshake as sh
import MCP_Server.server as server
from tests.test_batch_1_10_19 import err, ok, run
from tests.test_batch_1_10_21 import Track, inst, live, pump  # noqa: F401
from tests.test_notes_edit import script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Song(object):
    def __init__(self):
        self.tracks = [Track("Vox", armed=True)]
        self.signature_numerator, self.signature_denominator = 4, 4
        self.is_playing = self.session_record = False
        self.back_to_arranger = self.loop = self.arrangement_overdub = False
        self.loop_start, self.loop_length = 0.0, 16.0
        self.count_in_duration = 0
        self._time, self.home, self.stops = 130.0, False, 0
        self._record_mode, self.recorded_from = False, None

    @property
    def current_song_time(self):
        return self._time

    @current_song_time.setter
    def current_song_time(self, value):
        self._time = float(value)

    @property
    def record_mode(self):
        return self._record_mode

    @record_mode.setter
    def record_mode(self, value):
        if value and not self._record_mode and self.is_playing:
            self.recorded_from = self._time
        self._record_mode = value

    def start_playing(self):
        if not self.is_playing:
            if self.home:
                self._time = 0.0
            self.is_playing = True
            if self._record_mode:
                self.recorded_from = self._time

    def stop_playing(self):
        self.stops += 1
        if not self.is_playing:
            self.home, self._time = True, 0.0
        self.is_playing = False


@pytest.fixture
def song():
    return Song()


def test_a_move_made_while_stopped_sticks_after_a_second_stop(inst, song):
    song.stop_playing()
    r = ok(run(inst, "set_current_song_time", time=32.0))
    assert r["stopped"] is True and r["current_song_time"] == 32.0
    r = ok(run(inst, "start_playback"))
    assert song.is_playing and song.current_song_time == 32.0
    assert r["from_beat"] == 32.0 and r["was_playing"] is False and "warning" not in r


def test_start_playback_from_a_beat(inst, song):
    song.home = True
    r = ok(run(inst, "start_playback", at_beat=64.0))
    assert song.current_song_time == 64.0 and r["from_beat"] == 64.0
    # already playing: a jump, Play is not pressed again
    r = ok(run(inst, "start_playback", at_beat=8.0))
    assert song.current_song_time == 8.0 and r["was_playing"] is True


def test_without_a_move_play_starts_where_live_is(inst, song):
    r = ok(run(inst, "start_playback"))
    assert song.current_song_time == 130.0 and "from_beat" not in r


def test_a_move_overtaken_on_the_push_is_not_replayed(inst, song):
    ok(run(inst, "set_current_song_time", time=32.0))
    # Play and Stop on the Push since: the playhead is elsewhere
    song.current_song_time = 40.0
    r = ok(run(inst, "start_playback"))
    assert song.current_song_time == 40.0 and "from_beat" not in r


def test_a_move_while_playing_leaves_nothing_for_the_next_play(inst, song):
    song.is_playing = True
    assert ok(run(inst, "set_current_song_time", time=32.0))["stopped"] is False
    song.stop_playing()
    song.current_song_time = 32.0
    assert "from_beat" not in ok(run(inst, "start_playback"))


def test_bad_at_beat_is_refused(inst, song):
    assert "0 or later" in err(run(inst, "start_playback", at_beat=-4.0))
    assert song.is_playing is False


def test_stop_while_stopped_presses_nothing(inst, song):
    r = ok(run(inst, "stop_playback"))
    assert r == {"playing": False, "already_stopped": True}
    assert song.stops == 0 and song.current_song_time == 130.0


def test_an_arrangement_take_from_stopped_records_from_its_start_not_from_bar_1(inst, song):
    song.home = True
    r = ok(run(inst, "start_arrangement_record", start_time=16.0, end_time=48.0, confirm=True))
    assert song.recorded_from == 16.0 and r["after"]["recording"] is True and "pre_roll_beats" not in r
    song.current_song_time = 48.1
    pump(inst)
    assert song.record_mode is False


def test_an_arrangement_take_without_start_time_records_from_the_playhead_it_read(inst, song):
    song.current_song_time = 24.0
    song.home = True
    r = ok(run(inst, "start_arrangement_record", confirm=True))
    assert r["start_time"] == 24.0 and song.recorded_from == 24.0


def test_a_count_in_becomes_pre_roll_and_recording_punches_in_at_the_start(inst, song):
    song.count_in_duration = 1
    r = ok(run(inst, "start_arrangement_record", start_time=16.0, end_time=48.0, confirm=True))
    assert r["pre_roll_beats"] == 4.0 and song.current_song_time == 12.0 and song.record_mode is False
    song.current_song_time = 14.0
    pump(inst)
    assert song.record_mode is False
    song.current_song_time = 16.05
    pump(inst)
    assert song.record_mode is True and song.recorded_from == 16.05
    song.current_song_time = 48.1
    pump(inst)
    pump(inst)
    assert song.record_mode is False


def test_the_pre_roll_ignores_the_old_position_read_back_before_the_move_lands(inst, song):
    song.count_in_duration = 1
    ok(run(inst, "start_arrangement_record", start_time=16.0, confirm=True))
    song.current_song_time = 130.2
    pump(inst)
    assert song.record_mode is False


def test_a_stop_during_the_pre_roll_ends_it(inst, song):
    song.count_in_duration = 2
    ok(run(inst, "start_arrangement_record", start_time=16.0, confirm=True))
    assert song.current_song_time == 8.0
    song.is_playing = False
    pump(inst)
    song.is_playing, song.current_song_time = True, 16.5
    pump(inst)
    assert song.record_mode is False and inst.later == []


def test_stop_recording_with_the_transport_stopped_presses_no_stop(inst, song):
    ok(run(inst, "stop_recording", stop_transport=True))
    assert song.stops == 0 and song.current_song_time == 130.0


# --------------------------------------------------------------------------- the tools

def test_tool_messages(conn, monkeypatch):
    monkeypatch.setattr(sh, "_script_info", {"script_version": "1.10.26", "capabilities": ["start_playback_at_beat"]})
    conn.response = {"current_song_time": 32.0, "requested": 32.0, "stopped": True}
    assert "Live is stopped: start_playback plays from here" in call(server.set_arrangement_time, None, 32.0)
    conn.response = {"playing": False, "already_stopped": True}
    assert call(server.stop_playback, None).startswith("Live was already stopped; nothing was pressed")
    conn.response = {"playing": True, "was_playing": False, "from_beat": 64.0, "current_song_time": 64.25}
    assert call(server.start_playback, None, at_beat=64.0) == "Started playback from beat 64.0 (the playhead is at 64.25)"
    assert conn.sent[-1] == ("start_playback", {"at_beat": 64.0})
    conn.response = {"playing": True, "was_playing": True}
    assert call(server.start_playback, None) == "Already playing"


def test_an_older_script_gets_play_then_the_jump(conn, monkeypatch):
    monkeypatch.setattr(sh, "_script_info", {"script_version": "1.10.25", "capabilities": ["get_slot_state"]})
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    conn.response = {"current_song_time": 64.2}
    out = call(server.start_playback, None, at_beat=64.0)
    assert [c for c, _ in conn.sent] == ["start_playback", "set_current_song_time"]
    assert out == "Started playback, then moved the playhead to beat 64.2"
