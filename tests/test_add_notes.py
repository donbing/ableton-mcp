"""add_notes_to_clip: validation, the notes Live would hide, and what is reported.

Upstream issue #138: the old reply counted the notes SENT, a note starting after
the clip's end was kept silently out of earshot, and unknown fields such as
probability were ignored. Now the reply counts what the clip holds afterwards.
"""
import sys
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import FakeNote, NoteVector, make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Clip(object):
    def __init__(self, length=4.0, with_new_api=False):
        self.length = length
        self.notes = []
        self.legacy_calls = []
        self.new_calls = []
        if with_new_api:
            self.add_new_notes = self._add_new_notes

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return NoteVector(n for n in self.notes if from_time <= n.start_time < from_time + time_span)

    def set_notes(self, notes):
        self.legacy_calls.append(notes)
        for pitch, start, duration, velocity, mute in notes:
            self.notes.append(FakeNote(len(self.notes) + 1, pitch, start, duration, velocity, mute))

    def _add_new_notes(self, specs):
        self.new_calls.append(specs)
        for s in specs:
            self.notes.append(FakeNote(len(self.notes) + 1, s.pitch, s.start_time, s.duration,
                                       s.velocity, s.mute, s.probability,
                                       s.velocity_deviation, s.release_velocity))


class Slot(object):
    def __init__(self, clip):
        self.clip = clip
        self.has_clip = clip is not None


class Song(object):
    def __init__(self, clip):
        self.tracks = [types.SimpleNamespace(clip_slots=[Slot(clip)])]


def run(script_module, clip, notes):
    inst = make_inst(script_module, Song(clip))
    return inst._process_command({"type": "add_notes_to_clip",
                                  "params": {"track_index": 0, "clip_index": 0, "notes": notes}})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_the_count_comes_from_the_clip_and_a_note_after_the_end_is_refused(script_module):
    clip = Clip(4.0)
    result = ok(run(script_module, clip, [
        {"pitch": 49, "start_time": 3.5, "duration": 2},
        {"pitch": 51, "start_time": 6.0, "duration": 1},
        {"pitch": 53, "start_time": 0, "duration": 1}]))
    assert result["note_count"] == 2 and result["sent"] == 3 and result["clip_note_count"] == 2
    assert [r["index"] for r in result["rejected"]] == [1]
    assert "never play" in result["rejected"][0]["reason"]
    assert sorted(n.pitch for n in clip.notes) == [49, 53]


def test_a_note_exactly_at_the_end_or_before_zero_is_refused(script_module):
    clip = Clip(4.0)
    result = ok(run(script_module, clip, [{"pitch": 60, "start_time": 4.0}, {"pitch": 61, "start_time": -0.5},
                                          {"pitch": 62, "start_time": 3.999}]))
    assert [r["index"] for r in result["rejected"]] == [0, 1] and result["note_count"] == 1


def test_an_unknown_field_is_an_error_and_nothing_is_added(script_module):
    clip = Clip()
    message = err(run(script_module, clip, [{"pitch": 60}, {"pitch": 61, "probabilty": 0.5}]))
    assert "unknown field(s) probabilty" in message and clip.notes == []


@pytest.mark.parametrize("note,needle", [
    ({"pitch": 200}, "pitch"), ({"pitch": 60, "velocity": 0}, "velocity"),
    ({"pitch": 60, "duration": 0}, "duration"), ({"pitch": 60, "mute": "no"}, "mute"),
    ({"pitch": 60, "probability": 1.5}, "probability"), ("x", "must be an object"),
])
def test_bad_notes_are_errors(script_module, note, needle):
    clip = Clip()
    assert needle in err(run(script_module, clip, [note]))
    assert clip.notes == []


def test_extended_fields_need_the_new_api_and_use_it_when_there(script_module, monkeypatch):
    clip = Clip(with_new_api=False)
    assert "cannot set probability" in err(run(script_module, clip, [{"pitch": 60, "probability": 0.5}]))
    assert clip.notes == []

    class Spec(object):
        def __init__(self, pitch, start_time, duration, velocity, mute, probability=1.0,
                     velocity_deviation=0.0, release_velocity=64.0):
            self.__dict__.update(locals())

    live = types.ModuleType("Live")
    live.Clip = types.SimpleNamespace(MidiNoteSpecification=Spec)
    monkeypatch.setitem(sys.modules, "Live", live)
    clip = Clip(with_new_api=True)
    result = ok(run(script_module, clip, [{"pitch": 60, "start_time": 0, "probability": 0.5,
                                           "velocity_deviation": 10, "release_velocity": 30}]))
    assert result["note_count"] == 1 and clip.legacy_calls == []
    n = clip.notes[0]
    assert (n.probability, n.velocity_deviation, n.release_velocity) == (0.5, 10.0, 30.0)


def test_plain_notes_use_the_old_api_when_the_new_one_is_missing(script_module, monkeypatch):
    clip = Clip(with_new_api=False)
    ok(run(script_module, clip, [{"pitch": 60}]))
    assert len(clip.legacy_calls) == 1


def test_tool_message_lists_what_was_not_added(conn):
    conn.response = {"note_count": 2, "sent": 3, "rejected": [
        {"index": 1, "pitch": 51, "start_time": 6.0, "reason": "starts at or after the end of the clip"}]}
    out = call(server.add_notes_to_clip, None, 0, 0, [{}, {}, {}])
    assert out.startswith("Added 2 notes to clip at track 0, slot 0")
    assert "NOT added (1 of 3): note 1 (pitch 51, start 6.0)" in out


def test_tool_message_is_unchanged_when_all_went_in(conn):
    conn.response = {"note_count": 1, "sent": 1, "rejected": []}
    assert call(server.add_notes_to_clip, None, 3, 7, [{}]) == "Added 1 notes to clip at track 3, slot 7"
