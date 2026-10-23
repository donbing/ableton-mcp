"""Tests for clear / trim / split / move / create of Arrangement clips.

The fake Live reproduces what was measured on Live 12.4 Lite (2026-10-23):
placing a clip over others overwrites them like a paste (tail shortened, head
starts later with its content offset kept, a middle splits the clip in two);
Track.duplicate_clip_to_arrangement accepts an Arrangement clip and keeps its
extent and start_marker; Track.create_midi_clip(start, length) makes a clip of
exactly that length. Edits are checked by what is left on the timeline, not by
the calls made.
"""
import json

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401,E402

ERASER_NAME = "ableton_mcp_eraser_60s"


class Clip(object):
    def __init__(self, start, end, name="", start_marker=0.0, file_path=None):
        self.start_time = float(start)
        self.end_time = float(end)
        self.name = name
        self.start_marker = float(start_marker)
        self.file_path = file_path
        self.notes = ()

    def set_notes(self, notes):
        self.notes = tuple(notes)


class SessionAudio(object):
    def __init__(self, path, tempo=120.0):
        self.file_path = path
        self.name = ERASER_NAME
        self.length = 60.0 * tempo / 60.0
        self.loop_start = 0.0
        self.loop_end = self.length

    def __setattr__(self, key, value):
        if key == "loop_end" and hasattr(self, "length") and not 0 < value <= self.length:
            raise RuntimeError("loop_end out of range")
        object.__setattr__(self, key, value)


class Slot(object):
    def __init__(self, track):
        self.track = track
        self.clip = None

    @property
    def has_clip(self):
        return self.clip is not None

    def create_audio_clip(self, path):
        self.clip = SessionAudio(path)

    def delete_clip(self):
        self.clip = None


class Track(object):
    def __init__(self, name, midi=True, foldable=False, slots=2):
        self.name = name
        self.has_midi_input = midi
        self.is_foldable = foldable
        self.arrangement_clips = []
        self.clip_slots = [Slot(self) for _ in range(slots)]
        self.log = []

    def _place(self, new):
        survivors = []
        for c in self.arrangement_clips:
            if c.end_time <= new.start_time or c.start_time >= new.end_time:
                survivors.append(c)
                continue
            if c.start_time >= new.start_time and c.end_time <= new.end_time:
                continue                                           # covered: removed
            if c.start_time < new.start_time and c.end_time > new.end_time:
                right = Clip(new.end_time, c.end_time, c.name,
                             c.start_marker + (new.end_time - c.start_time), c.file_path)
                c.end_time = new.start_time
                survivors += [c, right]
            elif c.start_time < new.start_time:
                c.end_time = new.start_time
                survivors.append(c)
            else:
                c.start_marker += new.end_time - c.start_time
                c.start_time = new.end_time
                survivors.append(c)
        survivors.append(new)
        self.arrangement_clips = survivors

    def create_midi_clip(self, start, length):
        self.log.append(("create_midi_clip", start, length))
        clip = Clip(start, start + length)
        self._place(clip)
        return clip

    def create_audio_clip(self, path, start):
        clip = Clip(start, start + 4.0, "file", file_path=path)
        self._place(clip)
        return clip

    def delete_clip(self, clip):
        self.log.append(("delete_clip", clip.start_time))
        self.arrangement_clips = [c for c in self.arrangement_clips if c is not clip]

    def duplicate_clip_to_arrangement(self, clip, time):
        self.log.append(("duplicate", time))
        if isinstance(clip, Clip):
            copy = Clip(time, time + (clip.end_time - clip.start_time), clip.name,
                        clip.start_marker, clip.file_path)
        else:
            copy = Clip(time, time + (clip.loop_end - clip.loop_start), clip.name,
                        0.0, clip.file_path)
        self._place(copy)


class Song(object):
    def __init__(self, *tracks):
        self.tracks = list(tracks)


def spans(track):
    return sorted((c.start_time, c.end_time, c.start_marker) for c in track.arrangement_clips)


@pytest.fixture
def midi():
    t = Track("Piano")
    t.arrangement_clips = [Clip(8, 16, "A"), Clip(24, 32, "B")]
    return t


@pytest.fixture
def audio(script_module):
    t = Track("Guitar", midi=False)
    t.arrangement_clips = [Clip(8, 16, "A", file_path="/x.wav")]
    return t


def make(script_module, *tracks):
    return make_inst(script_module, Song(*tracks))


def run(inst, command, **params):
    params.setdefault("track_index", 0)
    params.setdefault("expected_name", "Piano")
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------------ guards

@pytest.mark.parametrize("command,params", [
    ("clear_arrangement_range", {"start_time": 10, "end_time": 12}),
    ("trim_arrangement_clip", {"clip_start_time": 8, "new_end_time": 12}),
    ("split_arrangement_clip", {"clip_start_time": 8, "split_time": 12}),
    ("move_arrangement_clip", {"clip_start_time": 8, "new_start_time": 40}),
    ("create_arrangement_clip", {"start_time": 40, "length": 4}),
])
def test_every_edit_previews_by_default_and_changes_nothing(script_module, midi, command, params):
    before = spans(midi)
    result = ok(run(make(script_module, midi), command, **params))
    assert result["applied"] is False and result["dry_run"] is True
    assert spans(midi) == before and midi.log == []


@pytest.mark.parametrize("command,params", [
    ("clear_arrangement_range", {"start_time": 10, "end_time": 12}),
    ("trim_arrangement_clip", {"clip_start_time": 8, "new_end_time": 12}),
    ("split_arrangement_clip", {"clip_start_time": 8, "split_time": 12}),
    ("move_arrangement_clip", {"clip_start_time": 8, "new_start_time": 40}),
    ("create_arrangement_clip", {"start_time": 40, "length": 4}),
])
def test_a_stale_track_name_or_a_group_track_changes_nothing(script_module, midi, command, params):
    inst = make(script_module, midi)
    assert "not 'Other'" in err(run(inst, command, expected_name="Other", confirm=True, **params))
    assert "expected_name is required" in err(run(inst, command, expected_name=None, confirm=True, **params))
    midi.is_foldable = True
    assert "group track" in err(run(inst, command, confirm=True, **params))
    assert midi.log == []


def test_confirm_must_be_a_real_boolean(script_module, midi):
    message = err(run(make(script_module, midi), "clear_arrangement_range",
                      start_time=10, end_time=12, confirm="false"))
    assert "confirm must be true or false" in message


# ------------------------------------------------------------------- clear

def test_clear_a_tail_a_head_and_the_middle_without_losing_content(script_module, midi):
    inst = make(script_module, midi)
    ok(run(inst, "clear_arrangement_range", start_time=14, end_time=20, confirm=True))
    assert spans(midi) == [(8, 14, 0), (24, 32, 0)]
    ok(run(inst, "clear_arrangement_range", start_time=22, end_time=26, confirm=True))
    assert spans(midi) == [(8, 14, 0), (26, 32, 2)]
    ok(run(inst, "clear_arrangement_range", start_time=10, end_time=12, confirm=True))
    assert spans(midi) == [(8, 10, 0), (12, 14, 4), (26, 32, 2)]


def test_clear_reports_what_it_will_do_and_removes_covered_clips(script_module, midi):
    inst = make(script_module, midi)
    preview = ok(run(inst, "clear_arrangement_range", start_time=4, end_time=20))
    assert [(a["name"], a["effect"]) for a in preview["affected"]] == [
        ("A", "removed")]
    result = ok(run(inst, "clear_arrangement_range", start_time=4, end_time=28, confirm=True))
    assert result["verified"] is True
    assert spans(midi) == [(28, 32, 4)]


def test_clear_leaves_no_eraser_behind(script_module, midi):
    ok(run(make(script_module, midi), "clear_arrangement_range",
           start_time=10, end_time=12, confirm=True))
    assert [c.name for c in midi.arrangement_clips] == ["A", "A", "B"]


def test_clear_rejects_empty_and_tiny_ranges(script_module, midi):
    inst = make(script_module, midi)
    assert "at least" in err(run(inst, "clear_arrangement_range", start_time=10, end_time=10.01, confirm=True))
    assert "must be" in err(run(inst, "clear_arrangement_range", start_time="x", end_time=12, confirm=True))


def test_clear_on_an_audio_track_uses_and_releases_a_session_slot(script_module, audio):
    inst = make(script_module, audio)
    ok(run(inst, "clear_arrangement_range", track_index=0, expected_name="Guitar",
           start_time=10, end_time=12, confirm=True))
    assert spans(audio) == [(8, 10, 0), (12, 16, 4)]
    assert all(not slot.has_clip for slot in audio.clip_slots)


def test_a_long_range_on_an_audio_track_is_erased_in_pieces(script_module, audio):
    audio.arrangement_clips = [Clip(0, 400, "Long", file_path="/x.wav")]
    ok(run(make(script_module, audio), "clear_arrangement_range", track_index=0,
           expected_name="Guitar", start_time=10, end_time=390, confirm=True))
    assert spans(audio) == [(0, 10, 0), (390, 400, 390)]
    assert audio.log.count(("duplicate", 10.0)) == 1 and len([l for l in audio.log if l[0] == "duplicate"]) >= 4


def test_an_audio_track_with_no_empty_session_slot_is_refused_untouched(script_module, audio):
    for slot in audio.clip_slots:
        slot.clip = SessionAudio("/y.wav")
    before = spans(audio)
    message = err(run(make(script_module, audio), "clear_arrangement_range", track_index=0,
                      expected_name="Guitar", start_time=10, end_time=12, confirm=True))
    assert "empty Session slot" in message and spans(audio) == before


# -------------------------------------------------------------------- trim

def test_trim_the_end_the_start_and_both(script_module, midi):
    inst = make(script_module, midi)
    ok(run(inst, "trim_arrangement_clip", clip_start_time=8, new_end_time=12, confirm=True))
    assert spans(midi) == [(8, 12, 0), (24, 32, 0)]
    result = ok(run(inst, "trim_arrangement_clip", clip_start_time=24, new_start_time=26,
                    new_end_time=30, confirm=True))
    assert result["verified"] is True
    assert spans(midi) == [(8, 12, 0), (26, 30, 2)]


def test_trim_never_lengthens_and_needs_something_to_do(script_module, midi):
    inst = make(script_module, midi)
    assert "only be shortened" in err(run(inst, "trim_arrangement_clip", clip_start_time=8, new_end_time=20, confirm=True))
    assert "only be shortened" in err(run(inst, "trim_arrangement_clip", clip_start_time=8, new_start_time=4, confirm=True))
    assert "new_start_time and/or new_end_time" in err(run(inst, "trim_arrangement_clip", clip_start_time=8, confirm=True))
    assert "shorter than" in err(run(inst, "trim_arrangement_clip", clip_start_time=8, new_end_time=8.01, confirm=True))
    assert spans(midi) == [(8, 16, 0), (24, 32, 0)]


def test_trim_names_the_clip_starts_when_the_start_is_wrong(script_module, midi):
    message = err(run(make(script_module, midi), "trim_arrangement_clip",
                      clip_start_time=9, new_end_time=12, confirm=True))
    assert "No Arrangement clip starts at beat 9.0" in message and "8.0, 24.0" in message


def test_trim_does_not_touch_the_neighbours(script_module):
    t = Track("Piano")
    t.arrangement_clips = [Clip(0, 8, "A"), Clip(8, 16, "B"), Clip(16, 24, "C")]
    ok(run(make(script_module, t), "trim_arrangement_clip", clip_start_time=8,
           new_start_time=10, new_end_time=14, confirm=True))
    assert spans(t) == [(0, 8, 0), (10, 14, 2), (16, 24, 0)]


# ------------------------------------------------------------------- split

def test_split_leaves_two_adjacent_clips_with_the_right_content_offsets(script_module, midi):
    result = ok(run(make(script_module, midi), "split_arrangement_clip",
                    clip_start_time=8, split_time=11, confirm=True))
    assert result["verified"] is True
    assert spans(midi) == [(8, 11, 0), (11, 16, 3), (24, 32, 0)]
    assert [c.name for c in midi.arrangement_clips].count("A") == 2


def test_split_leaves_no_scratch_clip_even_when_a_step_fails(script_module, midi, monkeypatch):
    inst = make(script_module, midi)
    original = inst._arr_erase
    calls = []

    def flaky(track, start, end):
        calls.append(start)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return original(track, start, end)

    monkeypatch.setattr(inst, "_arr_erase", flaky)
    assert "boom" in err(run(inst, "split_arrangement_clip", clip_start_time=8, split_time=11, confirm=True))
    assert all(c.start_time < 100 for c in midi.arrangement_clips)


def test_split_on_an_audio_track(script_module, audio):
    ok(run(make(script_module, audio), "split_arrangement_clip", track_index=0,
           expected_name="Guitar", clip_start_time=8, split_time=13, confirm=True))
    assert spans(audio) == [(8, 13, 0), (13, 16, 5)]
    assert all(not slot.has_clip for slot in audio.clip_slots)


def test_split_refuses_a_cut_at_the_edge(script_module, midi):
    inst = make(script_module, midi)
    assert "inside the clip" in err(run(inst, "split_arrangement_clip", clip_start_time=8, split_time=8.01, confirm=True))
    assert "inside the clip" in err(run(inst, "split_arrangement_clip", clip_start_time=8, split_time=16, confirm=True))


# -------------------------------------------------------------------- move

def test_move_keeps_length_and_offset_and_removes_the_original(script_module, midi):
    inst = make(script_module, midi)
    ok(run(inst, "trim_arrangement_clip", clip_start_time=8, new_start_time=10, confirm=True))
    result = ok(run(inst, "move_arrangement_clip", clip_start_time=10, new_start_time=40, confirm=True))
    assert result["verified"] is True
    assert spans(midi) == [(24, 32, 0), (40, 46, 2)]


def test_move_lists_what_the_destination_overwrites(script_module, midi):
    preview = ok(run(make(script_module, midi), "move_arrangement_clip",
                     clip_start_time=8, new_start_time=28))
    assert preview["overwrites"] == [{"name": "B", "start_time": 24.0, "end_time": 32.0,
                                      "effect": "tail cut, now ends at 28.0"}]


def test_move_over_its_own_old_range_goes_through_a_scratch_copy(script_module, midi):
    result = ok(run(make(script_module, midi), "move_arrangement_clip",
                    clip_start_time=8, new_start_time=12, confirm=True))
    assert result["verified"] is True
    assert spans(midi) == [(12, 20, 0), (24, 32, 0)]
    assert all(c.start_time < 100 for c in midi.arrangement_clips)


def test_copy_keeps_the_original_and_refuses_to_overlap_it(script_module, midi):
    inst = make(script_module, midi)
    ok(run(inst, "move_arrangement_clip", clip_start_time=8, new_start_time=40, copy=True, confirm=True))
    assert spans(midi) == [(8, 16, 0), (24, 32, 0), (40, 48, 0)]
    assert "cannot overlap" in err(run(inst, "move_arrangement_clip", clip_start_time=8,
                                       new_start_time=12, copy=True, confirm=True))


def test_move_to_the_same_place_or_a_negative_one_is_refused(script_module, midi):
    inst = make(script_module, midi)
    assert "already starts" in err(run(inst, "move_arrangement_clip", clip_start_time=8, new_start_time=8, confirm=True))
    assert ">= 0" in err(run(inst, "move_arrangement_clip", clip_start_time=8, new_start_time=-1, confirm=True))


# ------------------------------------------------------------------ create

def test_create_a_midi_clip_with_notes_at_a_position(script_module, midi):
    notes = [{"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100},
             {"pitch": 64, "start_time": 2, "duration": 1}]
    result = ok(run(make(script_module, midi), "create_arrangement_clip", start_time=40,
                    length=4, notes=notes, name="Riff", confirm=True))
    new = [c for c in midi.arrangement_clips if c.start_time == 40][0]
    assert (new.end_time, new.name) == (44.0, "Riff")
    assert new.notes == ((60, 0.0, 1.0, 100.0, False), (64, 2.0, 1.0, 100.0, False))
    assert result["created"]["end_time"] == 44.0


def test_create_refuses_notes_that_would_be_dropped_and_wrong_kinds(script_module, midi, audio):
    inst = make(script_module, midi)
    bad = err(run(inst, "create_arrangement_clip", start_time=40, length=4,
                  notes=[{"pitch": 60, "start_time": 4, "duration": 1}], confirm=True))
    assert "must start inside the clip" in bad
    assert "path is for audio tracks" in err(run(inst, "create_arrangement_clip", start_time=40,
                                                length=4, path="/x.wav", confirm=True))
    assert "must be a number" in err(run(inst, "create_arrangement_clip", start_time=40, confirm=True))
    assert spans(midi) == [(8, 16, 0), (24, 32, 0)]
    inst2 = make(script_module, audio)
    assert "existing audio file" in err(run(inst2, "create_arrangement_clip", track_index=0,
                                            expected_name="Guitar", start_time=40,
                                            path="/nope.wav", confirm=True))


def test_create_an_audio_clip_from_a_file(script_module, audio, tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF")
    ok(run(make(script_module, audio), "create_arrangement_clip", track_index=0,
           expected_name="Guitar", start_time=40, path=str(f), confirm=True))
    assert any(c.start_time == 40.0 for c in audio.arrangement_clips)


# ------------------------------------------------------------------- tools

@pytest.mark.parametrize("tool,args,command", [
    (server.clear_arrangement_range, (0, "Piano", 10.0, 12.0), "clear_arrangement_range"),
    (server.trim_arrangement_clip, (0, "Piano", 8.0, None, 12.0), "trim_arrangement_clip"),
    (server.split_arrangement_clip, (0, "Piano", 8.0, 12.0), "split_arrangement_clip"),
    (server.move_arrangement_clip, (0, "Piano", 8.0, 40.0), "move_arrangement_clip"),
    (server.create_arrangement_clip, (0, "Piano", 40.0, 4.0), "create_arrangement_clip"),
])
def test_tools_preview_by_default_and_apply_only_with_confirm(conn, tool, args, command):
    conn.response = {"applied": False}
    out = call(tool, None, *args)
    assert conn.sent[-1][0] == command and conn.sent[-1][1]["confirm"] is False
    assert out.startswith("NOT CHANGED")
    assert command in MODIFYING_TOOLS


def test_tools_send_confirm_true_only_when_asked(conn):
    conn.response = {"applied": True}
    out = call(server.trim_arrangement_clip, None, 0, "Piano", 8.0, None, 12.0, confirm=True)
    assert conn.sent[-1][1]["confirm"] is True and out.startswith("Done")
    assert "new_start_time" not in conn.sent[-1][1]


def test_tools_need_the_track_name(conn):
    assert "expected_name is required" in call(server.split_arrangement_clip, None, 0, None, 8.0, 12.0, confirm=True)


# ----------------------------------------------------- to another track

@pytest.fixture
def two(script_module):
    a = Track("Piano")
    a.arrangement_clips = [Clip(8, 16, "A"), Clip(24, 32, "B")]
    b = Track("Strings")
    b.arrangement_clips = [Clip(10, 12, "S")]
    return a, b, make(script_module, a, b)


def mv(inst, **params):
    base = dict(track_index=0, expected_name="Piano", clip_start_time=8)
    base.update(params)
    return run(inst, "move_arrangement_clip", **base)


def test_a_clip_moves_to_another_track_keeping_its_beat(two):
    a, b, inst = two
    result = ok(mv(inst, to_track_index=1, to_expected_name="Strings", confirm=True))
    assert result["verified"] is True and result["to_track"] == "Strings"
    assert spans(a) == [(24, 32, 0)]
    assert spans(b) == [(8, 16, 0)]          # it overwrote the 10-12 clip that sat under it
    assert [c["start_time"] for c in result["source_clips"]] == [24.0]


def test_a_clip_is_copied_to_another_track_at_a_new_beat(two):
    a, b, inst = two
    ok(mv(inst, to_track_index=1, to_expected_name="Strings", new_start_time=40.0, copy=True, confirm=True))
    assert spans(a) == [(8, 16, 0), (24, 32, 0)] and (40, 48, 0) in spans(b)


def test_the_preview_lists_what_the_other_track_loses(two):
    a, b, inst = two
    preview = ok(mv(inst, to_track_index=1, to_expected_name="Strings"))
    assert [o["name"] for o in preview["overwrites"]] == ["S"] and preview["applied"] is False
    assert spans(b) == [(10, 12, 0)]


def test_trimmed_content_offset_goes_with_the_clip(two):
    a, b, inst = two
    ok(run(inst, "trim_arrangement_clip", track_index=0, expected_name="Piano", clip_start_time=8,
           new_start_time=11, confirm=True))
    ok(mv(inst, clip_start_time=11, to_track_index=1, to_expected_name="Strings", new_start_time=50.0, confirm=True))
    assert (50, 55, 3) in spans(b)


def test_a_clip_cannot_go_to_a_track_of_another_kind(script_module):
    a = Track("Piano")
    a.arrangement_clips = [Clip(8, 16)]
    b = Track("Guitar", midi=False)
    reply = mv(make(script_module, a, b), to_track_index=1, to_expected_name="Guitar", confirm=True)
    assert "same kind" in err(reply) and spans(a) == [(8, 16, 0)] and b.arrangement_clips == []


def test_the_destination_track_needs_its_name_and_a_group_is_refused(two):
    a, b, inst = two
    assert "expected_name is required" in err(mv(inst, to_track_index=1, confirm=True))
    assert "not 'Other'" in err(mv(inst, to_track_index=1, to_expected_name="Other", confirm=True))
    b.is_foldable = True
    assert "group track" in err(mv(inst, to_track_index=1, to_expected_name="Strings", confirm=True))
    assert "to_expected_name needs to_track_index" in err(mv(inst, to_expected_name="Strings", new_start_time=40.0))
    assert spans(a) == [(8, 16, 0), (24, 32, 0)]


def test_giving_the_same_track_as_the_destination_is_a_plain_move(two):
    a, b, inst = two
    assert "new_start_time is required" in err(mv(inst, to_track_index=0, to_expected_name="Piano", confirm=True))
    ok(mv(inst, to_track_index=0, to_expected_name="Piano", new_start_time=40.0, confirm=True))
    assert spans(a) == [(24, 32, 0), (40, 48, 0)]


def test_tool_forwards_the_other_track_and_needs_both_names(conn):
    conn.response = {"applied": False}
    call(server.move_arrangement_clip, None, 0, "Piano", 8.0, None, False, 1, "Strings")
    assert conn.sent[-1][1]["to_track_index"] == 1 and "new_start_time" not in conn.sent[-1][1]
    assert "to_expected_name is required" in call(server.move_arrangement_clip, None, 0, "Piano", 8.0, 40.0,
                                                  False, 1, None)
    assert "give new_start_time" in call(server.move_arrangement_clip, None, 0, "Piano", 8.0)
