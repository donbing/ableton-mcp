"""Tests for note editing and clip loop on Session clips.

Tools: get_clip_info, set_clip_loop, remove_notes_from_clip,
apply_note_modifications, quantize_clip.

The Remote Script side runs against a mocked Live Object Model (``_Framework``
stubbed, no socket, no Ableton). The fake clip mimics the parts of Live that
make these edits risky: get_notes_extended returns COPIES of the notes (edits
reach the clip only through apply_note_modifications), and the loop setters
reject an intermediate state where loop_start >= loop_end. Anything that
removes or rewrites notes must preview unless explicitly told to act.

Nothing here talks to Live. Names marked UNVERIFIED in the Remote Script have
only been exercised against this fake.
"""

import asyncio
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")


# ----------------------------------------------------------------- fixtures

def _load_script_module():
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)
    spec = importlib.util.spec_from_file_location(
        "ableton_mcp_script_notes_edit", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeNote(object):
    """Stand-in for a Live MidiNote returned by get_notes_extended."""

    def __init__(self, note_id, pitch, start_time, duration=0.25, velocity=100.0,
                 mute=False):
        self.note_id = note_id
        self.pitch = pitch
        self.start_time = start_time
        self.duration = duration
        self.velocity = velocity
        self.mute = mute

    def copy(self):
        return FakeNote(self.note_id, self.pitch, self.start_time, self.duration,
                        self.velocity, self.mute)


class FakeClip(object):
    def __init__(self, notes=None, length=4.0, midi=True, name="Clip",
                 loop_start=0.0, loop_end=None, looping=True):
        self.name = name
        self.length = length
        self.is_midi_clip = midi
        self.is_audio_clip = not midi
        self.is_playing = False
        self.muted = False
        self.color_index = 7
        self.looping = looping
        self.start_marker = 0.0
        self.end_marker = length
        self._loop_start = loop_start
        self._loop_end = length if loop_end is None else loop_end
        self.notes = list(notes or [])
        self.loop_writes = []        # ("loop_start"|"loop_end", value)
        self.apply_calls = []        # lists of note ids passed
        self.remove_calls = []
        self.quantize_calls = []
        self.loop_end_ignored = False   # a Live that silently refuses loop_end

    # --- loop markers: Live rejects an intermediate state with start >= end
    @property
    def loop_start(self):
        return self._loop_start

    @loop_start.setter
    def loop_start(self, value):
        self.loop_writes.append(("loop_start", value))
        if value >= self._loop_end:
            raise RuntimeError("loop_start must be before loop_end")
        self._loop_start = value

    @property
    def loop_end(self):
        return self._loop_end

    @loop_end.setter
    def loop_end(self, value):
        self.loop_writes.append(("loop_end", value))
        if value <= self._loop_start:
            raise RuntimeError("loop_end must be after loop_start")
        if not self.loop_end_ignored:
            self._loop_end = value

    # --- notes
    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return tuple(n.copy() for n in self.notes
                     if from_pitch <= n.pitch < from_pitch + pitch_span
                     and from_time <= n.start_time < from_time + time_span)

    def apply_note_modifications(self, notes):
        # Real Live (12 Lite, 2026-10-22) rejects a list with "did not match C++ signature".
        if not isinstance(notes, tuple):
            raise TypeError("Python argument types did not match C++ signature: got %s"
                            % type(notes).__name__)
        ids = [n.note_id for n in notes]
        self.apply_calls.append(ids)
        by_id = dict((n.note_id, n) for n in self.notes)
        for n in notes:
            if n.note_id not in by_id:
                raise RuntimeError("unknown note id %r" % n.note_id)
        for n in notes:
            by_id[n.note_id].__dict__.update(n.copy().__dict__)

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.remove_calls.append((from_pitch, pitch_span, from_time, time_span))
        doomed = set(id(n) for n in self.notes
                     if from_pitch <= n.pitch < from_pitch + pitch_span
                     and from_time <= n.start_time < from_time + time_span)
        self.notes = [n for n in self.notes if id(n) not in doomed]

    def quantize(self, grid, amount):
        self.quantize_calls.append((grid, amount))
        size = {1: 1.0, 2: 0.5, 3: 1.0 / 3, 5: 0.25, 6: 1.0 / 6, 8: 0.125}[grid]
        for n in self.notes:
            target = round(n.start_time / size) * size
            n.start_time = n.start_time + amount * (target - n.start_time)


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip
        self.has_clip = clip is not None


class FakeTrack(object):
    def __init__(self, slots):
        self.clip_slots = slots


class FakeSong(object):
    def __init__(self, clip):
        self.tracks = [FakeTrack([FakeSlot(clip), FakeSlot(None)])]


def make_notes():
    return [
        FakeNote(1, 36, 0.0, 0.25, 100.0),
        FakeNote(2, 38, 1.1, 0.5, 90.0, mute=True),
        FakeNote(3, 42, 2.0, 0.25, 80.0),
        FakeNote(4, 60, 3.05, 1.0, 70.0),
    ]


def make_inst(script_module, song):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    return obj


@pytest.fixture
def clip():
    return FakeClip(make_notes())


@pytest.fixture
def inst(script_module, clip):
    return make_inst(script_module, FakeSong(clip))


def run(inst, command, **params):
    params.setdefault("track_index", 0)
    params.setdefault("clip_index", 0)
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------ get_clip_info

def test_clip_info_reports_the_facts(inst):
    info = ok(run(inst, "get_clip_info"))
    assert info["name"] == "Clip"
    assert info["length"] == 4.0
    assert info["looping"] is True
    assert (info["loop_start"], info["loop_end"]) == (0.0, 4.0)
    assert (info["start_marker"], info["end_marker"]) == (0.0, 4.0)
    assert info["is_playing"] is False
    assert info["is_midi_clip"] is True
    assert info["note_count"] == 4
    assert info["muted"] is False
    assert info["color_index"] == 7


def test_clip_info_is_a_read_not_scheduled_on_the_main_thread(inst):
    run(inst, "get_clip_info")
    assert inst.scheduled == []


def test_clip_info_for_an_audio_clip_has_no_note_count(script_module):
    audio = FakeClip(midi=False)
    info = ok(run(make_inst(script_module, FakeSong(audio)), "get_clip_info"))
    assert info["is_audio_clip"] is True
    assert info["note_count"] is None


def test_clip_info_leaves_missing_properties_null(script_module):
    class Bare(object):
        is_midi_clip = False
        name = "x"
        length = 2.0

    info = ok(run(make_inst(script_module, FakeSong(Bare())), "get_clip_info"))
    assert info["muted"] is None
    assert info["color_index"] is None
    assert info["loop_start"] is None


@pytest.mark.parametrize("params,needle", [
    ({"track_index": 5}, "Track index out of range"),
    ({"clip_index": 9}, "Clip index out of range"),
    ({"clip_index": 1}, "No clip in slot"),
    ({"track_index": True}, "must be an integer"),
    ({"clip_index": 0.5}, "must be an integer"),
])
def test_clip_info_errors(inst, params, needle):
    assert needle in err(run(inst, "get_clip_info", **params))


# ------------------------------------------------------------ set_clip_loop

def loop_of(clip):
    return (clip.loop_start, clip.loop_end)


@pytest.mark.parametrize("start,end", [
    (0.0, 8.0),    # grow the end
    (1.0, 3.0),    # shrink on both sides
    (0.0, 2.0),    # shrink the end only
    (2.0, 4.0),    # move the start later, end unchanged
    (6.0, 8.0),    # jump entirely past the current end (start must not go first)
    (0.0, 1.0),    # new end lands before the current start (start must go first)
])
def test_loop_moves_in_an_order_live_accepts(script_module, start, end):
    # The fake raises if an intermediate state has start >= end, so reaching
    # the target at all proves the write order is safe.
    clip = FakeClip(make_notes(), length=4.0, loop_start=1.5, loop_end=3.0)
    inst = make_inst(script_module, FakeSong(clip))
    result = ok(run(inst, "set_clip_loop", loop_start=start, loop_end=end))
    assert loop_of(clip) == (start, end)
    assert result["after"]["loop_start"] == start
    assert result["after"]["loop_end"] == end
    assert result["before"]["loop_start"] == 1.5
    assert result["before"]["loop_end"] == 3.0


@pytest.mark.parametrize("old,new", [
    ((0.0, 4.0), (8.0, 12.0)),     # move later, past the old end
    ((8.0, 12.0), (0.0, 4.0)),     # move earlier, before the old start
    ((2.0, 6.0), (3.0, 5.0)),      # shrink inside
    ((3.0, 5.0), (2.0, 6.0)),      # grow outside
])
def test_loop_every_ordering_case(script_module, old, new):
    clip = FakeClip(length=16.0, loop_start=old[0], loop_end=old[1])
    inst = make_inst(script_module, FakeSong(clip))
    ok(run(inst, "set_clip_loop", loop_start=new[0], loop_end=new[1]))
    assert loop_of(clip) == new


def test_growing_writes_the_end_first_and_shrinking_to_before_the_start_writes_start_first(
        script_module):
    grow = FakeClip(length=16.0, loop_start=0.0, loop_end=4.0)
    ok(run(make_inst(script_module, FakeSong(grow)), "set_clip_loop",
           loop_start=0.0, loop_end=8.0))
    assert [name for name, _ in grow.loop_writes] == ["loop_end"]  # start unchanged

    back = FakeClip(length=16.0, loop_start=8.0, loop_end=12.0)
    ok(run(make_inst(script_module, FakeSong(back)), "set_clip_loop",
           loop_start=0.0, loop_end=4.0))
    assert [name for name, _ in back.loop_writes] == ["loop_start", "loop_end"]

    forward = FakeClip(length=16.0, loop_start=0.0, loop_end=4.0)
    ok(run(make_inst(script_module, FakeSong(forward)), "set_clip_loop",
           loop_start=8.0, loop_end=12.0))
    assert [name for name, _ in forward.loop_writes] == ["loop_end", "loop_start"]


def test_looping_flag_is_applied_and_omitted_means_unchanged(inst, clip):
    result = ok(run(inst, "set_clip_loop", loop_start=0.0, loop_end=2.0, looping=False))
    assert clip.looping is False
    assert result["after"]["looping"] is False
    ok(run(inst, "set_clip_loop", loop_start=0.0, loop_end=3.0))
    assert clip.looping is False


def test_loop_does_not_touch_the_notes(inst, clip):
    ok(run(inst, "set_clip_loop", loop_start=0.0, loop_end=1.0))
    assert [n.note_id for n in clip.notes] == [1, 2, 3, 4]


@pytest.mark.parametrize("start,end,needle", [
    (2.0, 2.0, "must be before"),
    (3.0, 1.0, "must be before"),
    (-1.0, 2.0, ">= 0"),
    (None, 2.0, "must be a number"),
    (0.0, None, "must be a number"),
    ("0", 2.0, "must be a number"),
    (True, 2.0, "must be a number"),
    (0.0, float("inf"), "must be finite"),
    (float("nan"), 2.0, "must be finite"),
])
def test_invalid_loops_are_refused_before_anything_is_written(inst, clip, start, end, needle):
    assert needle in err(run(inst, "set_clip_loop", loop_start=start, loop_end=end))
    assert clip.loop_writes == []


def test_looping_must_be_a_bool(inst, clip):
    assert "looping must be" in err(
        run(inst, "set_clip_loop", loop_start=0.0, loop_end=2.0, looping="yes"))
    assert clip.loop_writes == []


def test_a_loop_live_did_not_keep_is_rolled_back_and_reported(inst, clip):
    clip.loop_end_ignored = True
    message = err(run(inst, "set_clip_loop", loop_start=0.0, loop_end=2.0))
    assert "did not accept the loop" in message
    assert "loop_end is 4.0, wanted 2.0" in message
    assert "restored" in message
    assert loop_of(clip) == (0.0, 4.0)


def test_loop_on_a_slot_without_a_clip(inst):
    assert "No clip in slot" in err(
        run(inst, "set_clip_loop", clip_index=1, loop_start=0.0, loop_end=2.0))


def test_loop_is_scheduled_on_the_main_thread(inst):
    run(inst, "set_clip_loop", loop_start=0.0, loop_end=2.0)
    assert inst.scheduled == [(0, "main_thread_task")]


# ------------------------------------------------------ remove_notes_from_clip

# Selects notes 1 (pitch 36 at 0.0) and 2 (pitch 38 at 1.1); note 3 (pitch 42 at
# 2.0) is outside the 1.5 beat span and note 4 outside the pitch range.
WINDOW = dict(from_time=0.0, time_span=1.5, from_pitch=36, pitch_span=8)


def ids(clip):
    return [n.note_id for n in clip.notes]


def test_remove_previews_by_default_and_removes_nothing(inst, clip):
    result = ok(run(inst, "remove_notes_from_clip", **WINDOW))
    assert result["dry_run"] is True
    assert result["removed"] is False
    assert result["matched_count"] == 2
    assert [n["note_id"] for n in result["sample"]] == [1, 2]
    assert ids(clip) == [1, 2, 3, 4]
    assert clip.remove_calls == []


def test_remove_with_dry_run_false_removes_exactly_the_window(inst, clip):
    result = ok(run(inst, "remove_notes_from_clip", dry_run=False, **WINDOW))
    assert result["removed"] is True
    assert result["removed_count"] == 2
    assert result["remaining_in_window"] == 0
    assert ids(clip) == [3, 4]
    # Live's order for the extended call is from_pitch, pitch_span, from_time, time_span.
    assert clip.remove_calls == [(36, 8, 0.0, 1.5)]


def test_preview_and_removal_agree_on_the_count(inst, clip):
    window = dict(from_time=0.0, time_span=8.0, from_pitch=0, pitch_span=128)
    preview = ok(run(inst, "remove_notes_from_clip", **window))
    done = ok(run(inst, "remove_notes_from_clip", dry_run=False, **window))
    assert preview["matched_count"] == done["removed_count"] == 4


def test_the_sample_is_capped_and_sorted(script_module):
    many = [FakeNote(i, 40, 8.0 - i * 0.25) for i in range(1, 21)]
    clip = FakeClip(many, length=8.0)
    inst = make_inst(script_module, FakeSong(clip))
    result = ok(run(inst, "remove_notes_from_clip",
                    from_time=0.0, time_span=8.0, from_pitch=0, pitch_span=128))
    assert result["matched_count"] == 20
    assert len(result["sample"]) == 10
    assert result["sample_truncated"] is True
    starts = [n["start_time"] for n in result["sample"]]
    assert starts == sorted(starts)


def test_removing_an_empty_window_is_a_noop_that_does_not_call_live(inst, clip):
    result = ok(run(inst, "remove_notes_from_clip", dry_run=False,
                    from_time=0.0, time_span=1.0, from_pitch=100, pitch_span=10))
    assert result["removed_count"] == 0
    assert clip.remove_calls == []
    assert ids(clip) == [1, 2, 3, 4]


@pytest.mark.parametrize("window,needle", [
    (dict(from_time=None, time_span=1.0, from_pitch=0, pitch_span=128), "from_time must be a number"),
    (dict(from_time=0.0, time_span=None, from_pitch=0, pitch_span=128), "time_span must be a number"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=None, pitch_span=128), "from_pitch must be an integer"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=0, pitch_span=None), "pitch_span must be an integer"),
    (dict(from_time=-1.0, time_span=1.0, from_pitch=0, pitch_span=128), "from_time must be >= 0"),
    (dict(from_time=0.0, time_span=0.0, from_pitch=0, pitch_span=128), "time_span must be > 0"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=128, pitch_span=1), "from_pitch must be between"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=0, pitch_span=0), "pitch_span must be between"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=100, pitch_span=64), "must be <= 128"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=60.5, pitch_span=1), "whole number"),
    (dict(from_time=0.0, time_span=1.0, from_pitch=True, pitch_span=1), "must be an integer"),
])
def test_remove_rejects_bad_windows_even_when_confirmed(inst, clip, window, needle):
    assert needle in err(run(inst, "remove_notes_from_clip", dry_run=False, **window))
    assert ids(clip) == [1, 2, 3, 4]
    assert clip.remove_calls == []


def test_remove_with_no_window_at_all_does_not_clear_the_clip(inst, clip):
    err(run(inst, "remove_notes_from_clip", dry_run=False))
    assert ids(clip) == [1, 2, 3, 4]


def test_remove_refuses_audio_clips_and_empty_slots(script_module, inst):
    audio = FakeClip(midi=False)
    message = err(run(make_inst(script_module, FakeSong(audio)),
                      "remove_notes_from_clip", **WINDOW))
    assert "not a MIDI clip" in message
    assert "No clip in slot" in err(run(inst, "remove_notes_from_clip", clip_index=1, **WINDOW))


def test_integral_float_pitches_from_json_are_accepted(inst, clip):
    window = dict(WINDOW, from_pitch=36.0, pitch_span=8.0)
    assert ok(run(inst, "remove_notes_from_clip", **window))["matched_count"] == 2


def test_notes_left_in_the_window_are_an_error_not_a_success(inst, clip, monkeypatch):
    monkeypatch.setattr(clip, "remove_notes_extended", lambda *a: None)
    message = err(run(inst, "remove_notes_from_clip", dry_run=False, **WINDOW))
    assert "still in the window" in message


def test_legacy_live_without_extended_calls_still_works(script_module):
    class Legacy(object):
        is_midi_clip = True
        name = "legacy"
        length = 4.0

        def __init__(self):
            self.notes = [(36, 0.0, 0.25, 100, False), (60, 3.0, 0.25, 90, False)]
            self.removed = []

        def get_notes(self, from_time, from_pitch, time_span, pitch_span):
            return tuple(n for n in self.notes
                         if from_time <= n[1] < from_time + time_span
                         and from_pitch <= n[0] < from_pitch + pitch_span)

        def remove_notes(self, from_time, from_pitch, time_span, pitch_span):
            self.removed.append((from_time, from_pitch, time_span, pitch_span))
            gone = self.get_notes(from_time, from_pitch, time_span, pitch_span)
            self.notes = [n for n in self.notes if n not in gone]

    legacy = Legacy()
    inst = make_inst(script_module, FakeSong(legacy))
    result = ok(run(inst, "remove_notes_from_clip", dry_run=False, **WINDOW))
    assert result["removed_count"] == 1
    assert legacy.removed == [(0.0, 36, 1.5, 8)]
    assert len(legacy.notes) == 1


def test_remove_is_scheduled_on_the_main_thread(inst):
    run(inst, "remove_notes_from_clip", **WINDOW)
    assert inst.scheduled == [(0, "main_thread_task")]


# ------------------------------------------------- apply_note_modifications

def note(clip, note_id):
    return next(n for n in clip.notes if n.note_id == note_id)


def edit(inst, notes, **params):
    return run(inst, "apply_note_modifications", notes=notes, **params)


def test_apply_previews_by_default_and_changes_nothing(inst, clip):
    result = ok(edit(inst, [{"note_id": 1, "pitch": 40, "velocity": 64}]))
    assert result["dry_run"] is True
    assert result["applied"] is False
    change = result["changes"][0]
    assert change["note_id"] == 1
    assert change["before"]["pitch"] == 36 and change["after"]["pitch"] == 40
    assert change["before"]["velocity"] == 100.0 and change["after"]["velocity"] == 64.0
    assert note(clip, 1).pitch == 36
    assert clip.apply_calls == []


def test_apply_edits_in_place_and_returns_before_and_after(inst, clip):
    result = ok(edit(inst, [
        {"note_id": 2, "start_time": 1.0, "duration": 0.75, "mute": False},
        {"note_id": 3, "pitch": 43, "velocity": 55},
    ], dry_run=False))
    assert result["applied"] is True and result["verified"] is True
    assert result["changed_count"] == 2
    two = note(clip, 2)
    assert (two.start_time, two.duration, two.mute, two.pitch) == (1.0, 0.75, False, 38)
    three = note(clip, 3)
    assert (three.pitch, three.velocity, three.start_time) == (43, 55.0, 2.0)
    by_id = dict((c["note_id"], c) for c in result["changes"])
    assert by_id[2]["before"]["start_time"] == 1.1
    assert by_id[2]["after"]["start_time"] == 1.0
    assert by_id[3]["after"]["pitch"] == 43
    # ids survive and the other notes are untouched
    assert [n.note_id for n in clip.notes] == [1, 2, 3, 4]
    assert (note(clip, 1).pitch, note(clip, 4).velocity) == (36, 70.0)


def test_only_the_changed_notes_are_handed_to_live(inst, clip):
    ok(edit(inst, [{"note_id": 4, "velocity": 10}], dry_run=False))
    assert clip.apply_calls == [[4]]


def test_a_no_op_edit_is_reported_and_not_sent_to_live(inst, clip):
    result = ok(edit(inst, [{"note_id": 1, "pitch": 36}], dry_run=False))
    assert result["changed_count"] == 0
    assert result["unchanged_note_ids"] == [1]
    assert result["applied"] is False
    assert clip.apply_calls == []


def test_unknown_ids_are_an_error_and_nothing_is_changed(inst, clip):
    message = err(edit(inst, [{"note_id": 1, "pitch": 40},
                              {"note_id": 99, "pitch": 41}], dry_run=False))
    assert "Unknown note_id(s) 99" in message
    assert clip.apply_calls == []
    assert note(clip, 1).pitch == 36


def test_a_note_moved_beyond_the_clip_end_is_still_verified(inst, clip):
    result = ok(edit(inst, [{"note_id": 1, "start_time": 6.0}], dry_run=False))
    assert result["verified"] is True
    assert note(clip, 1).start_time == 6.0


def test_edit_falls_back_to_handing_over_every_note_when_live_rejects_the_edited_ones(
        inst, clip, monkeypatch):
    real = clip.apply_note_modifications
    monkeypatch.setattr(clip, "apply_note_modifications",
                        lambda notes: real(notes) if len(notes) == len(clip.notes)
                        else (_ for _ in ()).throw(TypeError("did not match C++ signature")))
    result = ok(edit(inst, [{"note_id": 1, "pitch": 40}], dry_run=False))
    assert result["method"] == "all notes tuple"
    assert result["verified"] is True
    assert note(clip, 1).pitch == 40


def test_edit_names_every_attempt_when_live_rejects_all_of_them(inst, clip, monkeypatch):
    def refuse(notes):
        raise TypeError("did not match C++ signature")
    monkeypatch.setattr(clip, "apply_note_modifications", refuse)
    monkeypatch.delattr(type(clip), "remove_notes_extended", raising=False)
    message = err(edit(inst, [{"note_id": 1, "pitch": 40}], dry_run=False))
    assert "every way of applying" in message and "edited list" in message and "all notes tuple" in message


def test_a_value_live_did_not_keep_is_flagged(inst, clip, monkeypatch):
    monkeypatch.setattr(clip, "apply_note_modifications", lambda notes: None)
    result = ok(edit(inst, [{"note_id": 1, "pitch": 40}], dry_run=False))
    assert result["verified"] is False
    assert "note 1 pitch is 36, wanted 40" in result["mismatches"][0]


@pytest.mark.parametrize("notes,needle", [
    (None, "non-empty list"),
    ([], "non-empty list"),
    ("x", "non-empty list"),
    ([5], "must be an object"),
    ([{"pitch": 40}], "needs a note_id"),
    ([{"note_id": "1", "pitch": 40}], "note_id must be an integer"),
    ([{"note_id": True, "pitch": 40}], "note_id must be an integer"),
    ([{"note_id": 1}], "changes nothing"),
    ([{"note_id": 1, "new_pitch": 40}], "unknown field"),
    ([{"note_id": 1, "pitch": 128}], "pitch must be between"),
    ([{"note_id": 1, "pitch": -1}], "pitch must be between"),
    ([{"note_id": 1, "pitch": 40.5}], "whole number"),
    ([{"note_id": 1, "start_time": -0.5}], "start_time must be >= 0"),
    ([{"note_id": 1, "start_time": "1"}], "start_time must be a number"),
    ([{"note_id": 1, "duration": 0}], "duration must be > 0"),
    ([{"note_id": 1, "velocity": 0}], "velocity must be between"),
    ([{"note_id": 1, "velocity": 128}], "velocity must be between"),
    ([{"note_id": 1, "mute": 1}], "mute must be true or false"),
    ([{"note_id": 1, "pitch": 40}, {"note_id": 1, "pitch": 41}], "more than once"),
])
def test_invalid_edits_are_refused_before_anything_changes(inst, clip, notes, needle):
    assert needle in err(edit(inst, notes, dry_run=False))
    assert clip.apply_calls == []
    assert [n.pitch for n in clip.notes] == [36, 38, 42, 60]


def test_one_bad_entry_blocks_the_whole_batch(inst, clip):
    err(edit(inst, [{"note_id": 1, "pitch": 40}, {"note_id": 2, "velocity": 500}],
             dry_run=False))
    assert note(clip, 1).pitch == 36


def test_apply_refuses_audio_clips_and_empty_slots(script_module, inst):
    audio = FakeClip(midi=False)
    other = make_inst(script_module, FakeSong(audio))
    assert "not a MIDI clip" in err(edit(other, [{"note_id": 1, "pitch": 40}]))
    assert "No clip in slot" in err(
        edit(inst, [{"note_id": 1, "pitch": 40}], clip_index=1))


def test_apply_on_a_live_without_the_extended_api_says_so(script_module):
    class Old(object):
        is_midi_clip = True
        name = "old"
        length = 4.0

    inst = make_inst(script_module, FakeSong(Old()))
    assert "Live 11+" in err(edit(inst, [{"note_id": 1, "pitch": 40}], dry_run=False))


def test_apply_is_scheduled_on_the_main_thread(inst):
    edit(inst, [{"note_id": 1, "pitch": 40}])
    assert inst.scheduled == [(0, "main_thread_task")]


# ------------------------------------------------------------- quantize_clip

def quantize(inst, **params):
    params.setdefault("grid", "1/4")
    return run(inst, "quantize_clip", **params)


def starts(clip):
    return [round(n.start_time, 6) for n in clip.notes]


def test_quantize_previews_by_default_and_changes_nothing(inst, clip):
    result = ok(quantize(inst, grid="1/8"))
    assert result["dry_run"] is True and result["applied"] is False
    assert result["grid"] == "1/8" and result["amount"] == 1.0
    assert result["note_count"] == 4
    # 1.1 -> 1.0 and 3.05 -> 3.0 move; 0.0 and 2.0 are already on the grid
    assert result["estimated_moved_count"] == 2
    moved = dict((m["note"], m) for m in result["sample"])
    assert moved[2]["start_estimated_after"] == pytest.approx(1.0)
    assert moved[4]["start_estimated_after"] == pytest.approx(3.0)
    assert "estimate" in result["estimate_note"].lower()
    assert clip.quantize_calls == []
    assert starts(clip) == [0.0, 1.1, 2.0, 3.05]


@pytest.mark.parametrize("name,enum", [
    ("1/4", 1), ("1/8", 2), ("1/8T", 3), ("1/16", 5), ("1/16T", 6), ("1/32", 8),
])
def test_each_grid_maps_to_its_live_enum(inst, clip, name, enum):
    ok(quantize(inst, grid=name, dry_run=False))
    assert clip.quantize_calls == [(enum, 1.0)]


def test_grid_names_are_case_and_space_tolerant(inst, clip):
    ok(quantize(inst, grid=" 1/8t ", dry_run=False))
    assert clip.quantize_calls == [(3, 1.0)]


def test_quantize_applies_and_reports_the_readback(inst, clip):
    result = ok(quantize(inst, grid="1/8", dry_run=False))
    assert result["applied"] is True
    assert result["moved_count"] == 2
    assert starts(clip) == [0.0, 1.0, 2.0, 3.0]
    by_note = dict((m["note"], m) for m in result["sample"])
    assert by_note[2]["start_before"] == pytest.approx(1.1)
    assert by_note[2]["start_after"] == pytest.approx(1.0)


def test_partial_amount_is_passed_to_live_and_previewed(inst, clip):
    preview = ok(quantize(inst, grid="1/8", amount=0.5))
    moved = dict((m["note"], m) for m in preview["sample"])
    assert moved[2]["start_estimated_after"] == pytest.approx(1.05)
    ok(quantize(inst, grid="1/8", amount=0.5, dry_run=False))
    assert clip.quantize_calls == [(2, 0.5)]
    assert starts(clip)[1] == pytest.approx(1.05)


def test_amount_defaults_to_one_when_omitted(inst, clip):
    ok(quantize(inst, dry_run=False))
    assert clip.quantize_calls == [(1, 1.0)]


@pytest.mark.parametrize("amount", [0, 0.0, 1, 1.0, 0.25])
def test_amount_inside_the_range_is_accepted(inst, amount):
    assert ok(quantize(inst, amount=amount))["amount"] == float(amount)


@pytest.mark.parametrize("amount", [-0.1, 1.1, 2, "1", None, True, float("nan"), float("inf")])
def test_amount_outside_zero_to_one_is_refused(inst, clip, amount):
    err(quantize(inst, amount=amount, dry_run=False))
    assert clip.quantize_calls == []


@pytest.mark.parametrize("grid", ["1/2", "1/64", "quarter", "", "0.25", None, 0.25])
def test_unknown_grids_are_refused(inst, clip, grid):
    err(quantize(inst, grid=grid, dry_run=False))
    assert clip.quantize_calls == []


def test_amount_zero_is_a_noop_that_does_not_call_live(inst, clip):
    result = ok(quantize(inst, amount=0.0, dry_run=False))
    assert result["moved_count"] == 0
    assert clip.quantize_calls == []


def test_quantize_of_an_empty_clip_does_not_call_live(script_module):
    empty = FakeClip([])
    inst = make_inst(script_module, FakeSong(empty))
    assert ok(quantize(inst, dry_run=False))["moved_count"] == 0
    assert empty.quantize_calls == []


def test_quantize_refuses_audio_clips_and_empty_slots(script_module, inst):
    other = make_inst(script_module, FakeSong(FakeClip(midi=False)))
    assert "not a MIDI clip" in err(quantize(other))
    assert "No clip in slot" in err(quantize(inst, clip_index=1))


def test_quantize_is_scheduled_on_the_main_thread(inst):
    quantize(inst)
    assert inst.scheduled == [(0, "main_thread_task")]


# ------------------------------------------------------ server tool wrappers

class FakeConnection(object):
    def __init__(self):
        self.responses = []
        self.raise_exc = None
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, dict(params or {})))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.responses.pop(0) if self.responses else {}


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    fake = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    return fake


def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def _tool(name):
    return next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == name)


def test_get_clip_info_tool_sends_the_command_and_returns_json(conn):
    conn.responses = [{"name": "Clip", "note_count": 4}]
    out = call(server.get_clip_info, None, 2, 3)
    assert conn.sent == [("get_clip_info", {"track_index": 2, "clip_index": 3})]
    assert json.loads(out)["note_count"] == 4


def test_get_clip_info_tool_is_read_only_and_keeps_user_prompt():
    tool = _tool("get_clip_info")
    assert tool.annotations.readOnlyHint is True
    assert "user_prompt" in tool.inputSchema["properties"]


def test_get_clip_info_tool_reports_errors(conn):
    conn.raise_exc = Exception("No clip in slot")
    assert call(server.get_clip_info, None, 0, 0).startswith("Error getting clip info:")


def test_get_clip_info_tool_returns_the_capability_message_for_an_old_script(
        conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.get_clip_info, None, 0, 0) == "missing get_clip_info"
    assert conn.sent == []


def test_set_clip_loop_tool_sends_the_command(conn):
    conn.responses = [{"before": {}, "after": {"loop_start": 0.0, "loop_end": 2.0}}]
    out = call(server.set_clip_loop, None, 1, 2, 0.0, 2.0, looping=True)
    assert out.startswith("Loop set.")
    assert conn.sent == [("set_clip_loop", {
        "track_index": 1, "clip_index": 2, "loop_start": 0.0, "loop_end": 2.0,
        "looping": True})]


def test_set_clip_loop_tool_omits_looping_when_not_given(conn):
    call(server.set_clip_loop, None, 1, 2, 0.0, 2.0)
    assert "looping" not in conn.sent[0][1]


def test_set_clip_loop_tool_keeps_user_prompt_and_is_a_modifying_tool():
    assert "user_prompt" in _tool("set_clip_loop").inputSchema["properties"]
    assert "set_clip_loop" in MODIFYING_TOOLS


def test_set_clip_loop_tool_reports_script_errors(conn):
    conn.raise_exc = Exception("loop_start (3) must be before loop_end (1)")
    assert call(server.set_clip_loop, None, 0, 0, 3.0, 1.0).startswith(
        "Error setting clip loop:")


def test_remove_tool_previews_by_default_and_sends_dry_run_true(conn):
    conn.responses = [{"matched_count": 2, "sample": []}]
    out = call(server.remove_notes_from_clip, None, 0, 1, 0.0, 2.5, 36, 8)
    assert out.startswith("NOT REMOVED (preview only)")
    assert "confirm=true" in out
    assert conn.sent == [("remove_notes_from_clip", {
        "track_index": 0, "clip_index": 1, "from_time": 0.0, "time_span": 2.5,
        "from_pitch": 36, "pitch_span": 8, "dry_run": True})]


def test_remove_tool_with_confirm_sends_dry_run_false(conn):
    conn.responses = [{"removed": True, "removed_count": 2}]
    out = call(server.remove_notes_from_clip, None, 0, 1, 0.0, 2.5, 36, 8, confirm=True)
    assert out.startswith("Removed notes.")
    assert [c[1]["dry_run"] for c in conn.sent] == [False]


def test_remove_tool_is_destructive_requires_the_window_and_defaults_confirm_false():
    tool = _tool("remove_notes_from_clip")
    assert tool.annotations.destructiveHint is True
    schema = tool.inputSchema
    for name in ("track_index", "clip_index", "from_time", "time_span",
                 "from_pitch", "pitch_span"):
        assert name in schema["required"]
    assert "confirm" not in schema["required"]
    assert schema["properties"]["confirm"]["default"] is False
    assert "user_prompt" in schema["properties"]
    assert "remove_notes_from_clip" in MODIFYING_TOOLS


def test_remove_tool_reports_script_errors(conn):
    conn.raise_exc = Exception("Clip is not a MIDI clip")
    out = call(server.remove_notes_from_clip, None, 0, 1, 0.0, 2.5, 36, 8, confirm=True)
    assert out.startswith("Error removing notes from clip:")


def test_apply_tool_previews_by_default_and_sends_dry_run_true(conn):
    conn.responses = [{"changed_count": 1, "changes": []}]
    notes = [{"note_id": 1, "pitch": 40}]
    out = call(server.apply_note_modifications, None, 0, 1, notes)
    assert out.startswith("NOT APPLIED (preview only)")
    assert "confirm=true" in out
    assert conn.sent == [("apply_note_modifications", {
        "track_index": 0, "clip_index": 1, "notes": notes, "dry_run": True})]


def test_apply_tool_with_confirm_sends_dry_run_false(conn):
    conn.responses = [{"applied": True, "verified": True}]
    out = call(server.apply_note_modifications, None, 0, 1,
               [{"note_id": 1, "pitch": 40}], confirm=True)
    assert out.startswith("Applied note modifications.")
    assert [c[1]["dry_run"] for c in conn.sent] == [False]


def test_apply_tool_is_destructive_and_defaults_confirm_false():
    tool = _tool("apply_note_modifications")
    assert tool.annotations.destructiveHint is True
    schema = tool.inputSchema
    for name in ("track_index", "clip_index", "notes"):
        assert name in schema["required"]
    assert "confirm" not in schema["required"]
    assert schema["properties"]["confirm"]["default"] is False
    assert "user_prompt" in schema["properties"]
    assert "apply_note_modifications" in MODIFYING_TOOLS


def test_apply_tool_reports_script_errors(conn):
    conn.raise_exc = Exception("Unknown note_id(s) 99 in this clip")
    out = call(server.apply_note_modifications, None, 0, 1,
               [{"note_id": 99, "pitch": 40}], confirm=True)
    assert out.startswith("Error applying note modifications:")


def test_quantize_tool_previews_by_default_and_sends_dry_run_true(conn):
    conn.responses = [{"estimated_moved_count": 2}]
    out = call(server.quantize_clip, None, 0, 1, "1/16")
    assert out.startswith("NOT QUANTIZED (preview only)")
    assert "confirm=true" in out
    assert conn.sent == [("quantize_clip", {
        "track_index": 0, "clip_index": 1, "grid": "1/16", "amount": 1.0,
        "dry_run": True})]


def test_quantize_tool_with_confirm_sends_dry_run_false(conn):
    conn.responses = [{"applied": True, "moved_count": 2}]
    out = call(server.quantize_clip, None, 0, 1, "1/8T", amount=0.5, confirm=True)
    assert out.startswith("Quantized clip.")
    assert conn.sent[0][1]["dry_run"] is False
    assert conn.sent[0][1]["amount"] == 0.5


def test_quantize_tool_is_destructive_and_defaults_confirm_false():
    tool = _tool("quantize_clip")
    assert tool.annotations.destructiveHint is True
    schema = tool.inputSchema
    for name in ("track_index", "clip_index", "grid"):
        assert name in schema["required"]
    assert "amount" not in schema["required"]
    assert schema["properties"]["amount"]["default"] == 1.0
    assert schema["properties"]["confirm"]["default"] is False
    assert "user_prompt" in schema["properties"]
    assert "quantize_clip" in MODIFYING_TOOLS


def test_quantize_tool_reports_script_errors(conn):
    conn.raise_exc = Exception("Unknown grid '1/2'")
    assert call(server.quantize_clip, None, 0, 1, "1/2", confirm=True).startswith(
        "Error quantizing clip:")
