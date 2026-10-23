"""Tests for create_locator against a fake Live that behaves like the real one.

Measured on Live 12 Lite (2026-10-23): writing Song.current_song_time is read
back at once but only APPLIED after a tick, Song.set_or_delete_cue toggles at
the applied position, and the cue lands on a whole beat. The fake applies a
pending position when the code sleeps, and nowhere else.
"""
import pytest

from tests.test_notes_edit import make_inst, ok, err, script_module  # noqa: F401


class FakeCue(object):
    def __init__(self, time):
        self.time = float(time)
        self.name = ""


class FakeSong(object):
    def __init__(self, playhead=90.85, playing=False):
        self.cue_points = []
        self._applied = playhead
        self._written = playhead
        self.is_playing = playing

    @property
    def current_song_time(self):
        return self._written

    @current_song_time.setter
    def current_song_time(self, value):
        self._written = float(value)

    def tick(self):
        self._applied = self._written

    def set_or_delete_cue(self):
        at = float(int(self._applied))
        for cue in list(self.cue_points):
            if abs(cue.time - at) < 1e-6:
                self.cue_points.remove(cue)
                return
        self.cue_points.append(FakeCue(at))
        self.cue_points.sort(key=lambda c: c.time)
        self._applied = self._written = at   # Live moves the playhead onto the cue


@pytest.fixture
def song():
    return FakeSong()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    monkeypatch.setattr(script_module.time, "sleep", lambda seconds: song.tick())
    return make_inst(script_module, song)


def create(inst, time, name="x"):
    return inst._process_command({"type": "create_locator", "params": {"time": time, "name": name}})


def test_creates_one_named_locator_and_restores_the_playhead(inst, song):
    result = ok(create(inst, 64, "Intro"))
    assert [(c.time, c.name) for c in song.cue_points] == [(64.0, "Intro")]
    assert result["created"] is True and "note" not in result
    song.tick()
    assert song._applied == pytest.approx(90.85)


def test_several_locators_leave_no_strays(inst, song):
    for beat, label in ((64, "A"), (16, "B"), (0, "C")):
        ok(create(inst, beat, label))
    assert [(c.time, c.name) for c in song.cue_points] == [(0.0, "C"), (16.0, "B"), (64.0, "A")]


def test_an_existing_locator_is_renamed_not_deleted(inst, song):
    ok(create(inst, 64, "Intro"))
    result = ok(create(inst, 64, "Intro 2"))
    assert result["created"] is False
    assert [(c.time, c.name) for c in song.cue_points] == [(64.0, "Intro 2")]


def test_a_fractional_time_lands_on_a_beat_and_says_so(inst, song):
    result = ok(create(inst, 200.5, "Fim"))
    assert [(c.time, c.name) for c in song.cue_points] == [(200.0, "Fim")]
    assert result["requested_time"] == 200.5 and "whole beats" in result["note"]
    song.tick()
    assert song._applied == pytest.approx(90.85)


def test_refuses_while_playing_and_changes_nothing(script_module, monkeypatch):
    song = FakeSong(playing=True)
    monkeypatch.setattr(script_module.time, "sleep", lambda seconds: song.tick())
    message = err(create(make_inst(script_module, song), 64))
    assert "Stop playback" in message
    assert song.cue_points == [] and song._written == 90.85


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_rejects_bad_times(inst, song, bad):
    assert "time must be" in err(create(inst, bad))
    assert song.cue_points == []


def test_if_live_never_applies_the_move_the_stray_cue_is_removed(inst, song, monkeypatch, script_module):
    monkeypatch.setattr(script_module.time, "sleep", lambda seconds: None)
    real_tick = song.tick
    song.tick = lambda: None
    # Without ticks Live toggles at the old playhead (beat 90): a stray cue.
    message = err(create(inst, 64))
    assert "did not apply the playhead move" in message and "removed" in message
    assert "beat 90.0" in message
    assert song.cue_points == []


# ------------------------------------------------------------- delete_locator

from tests.test_scenes import call, conn  # noqa: E402,F401
import MCP_Server.server as server  # noqa: E402
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS  # noqa: E402


def delete(inst, time, expected_name, dry_run=True):
    return inst._process_command({"type": "delete_locator", "params": {
        "time": time, "expected_name": expected_name, "dry_run": dry_run}})


def with_cues(inst, song, *cues):
    for beat, label in cues:
        ok(create(inst, beat, label))
    song.tick()


def test_delete_previews_by_default_and_changes_nothing(inst, song):
    with_cues(inst, song, (16, "Verso"), (64, "Intro"))
    result = ok(delete(inst, 64, "Intro"))
    assert result["deleted"] is False and result["dry_run"] is True
    assert result["remaining"] == [{"name": "Verso", "time": 16.0}]
    assert [c.name for c in song.cue_points] == ["Verso", "Intro"]


def test_delete_removes_the_locator_and_restores_the_playhead(inst, song):
    with_cues(inst, song, (16, "Verso"), (64, "Intro"))
    result = ok(delete(inst, 64, "Intro", dry_run=False))
    assert result["deleted"] is True
    assert [(c.name, c.time) for c in song.cue_points] == [("Verso", 16.0)]
    song.tick()
    assert song._applied == pytest.approx(90.85)


def test_delete_with_the_wrong_name_deletes_nothing(inst, song):
    with_cues(inst, song, (64, "Intro"))
    assert "is 'Intro', not 'Outro'" in err(delete(inst, 64, "Outro", dry_run=False))
    assert len(song.cue_points) == 1


def test_delete_where_there_is_no_locator_lists_the_ones_that_exist(inst, song):
    with_cues(inst, song, (64, "Intro"))
    message = err(delete(inst, 65, "x", dry_run=False))
    assert "No locator at beat 65.0" in message and "Intro @ 64.0" in message


def test_delete_needs_both_time_and_name(inst, song):
    assert "time is required" in err(delete(inst, None, "x"))
    assert "expected_name is required" in err(delete(inst, 64, None))


def test_delete_is_refused_while_playing_but_the_preview_works(inst, song):
    with_cues(inst, song, (64, "Intro"))
    song.is_playing = True
    assert ok(delete(inst, 64, "Intro"))["deleted"] is False
    assert "Stop playback" in err(delete(inst, 64, "Intro", dry_run=False))
    assert len(song.cue_points) == 1


def test_delete_tool_previews_by_default(conn):
    conn.response = {"name": "Intro", "time": 64.0, "remaining": []}
    out = call(server.delete_locator, None, 64.0, "Intro")
    assert conn.sent == [("delete_locator", {"time": 64.0, "expected_name": "Intro", "dry_run": True})]
    assert out.startswith("NOT DELETED")


def test_delete_tool_deletes_only_with_confirm_and_needs_a_name(conn):
    conn.response = {"deleted": True}
    out = call(server.delete_locator, None, 64.0, "Intro", confirm=True)
    assert conn.sent[-1][1]["dry_run"] is False and out.startswith("Deleted locator")
    assert "expected_name is required" in call(server.delete_locator, None, 64.0, None, confirm=True)


def test_delete_locator_is_a_modifying_tool():
    assert "delete_locator" in MODIFYING_TOOLS
