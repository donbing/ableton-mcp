"""replace_clip_notes (adapted from upstream #119) and set_color (from #99)."""
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import FakeNote, NoteVector, make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Clip(object):
    is_midi_clip, is_audio_clip = True, False

    def __init__(self, length=4.0, name="Riff"):
        self.length, self.name, self.color_index = length, name, 3
        self.notes = [FakeNote(1, 36, 0.0, 1.0, 100.0, probability=0.5), FakeNote(2, 40, 2.0, 1.0, 90.0)]
        self.fail_next_write = False

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return NoteVector(n.copy() for n in self.notes if from_time <= n.start_time < from_time + time_span)

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.notes = [n for n in self.notes if not (from_time <= n.start_time < from_time + time_span)]

    def set_notes(self, notes):
        if self.fail_next_write:
            self.fail_next_write = False
            raise RuntimeError("Live refused")
        for pitch, start, duration, velocity, mute in notes:
            self.notes.append(FakeNote(len(self.notes) + 1, pitch, start, duration, velocity, mute))


class Track(object):
    def __init__(self, clip):
        self.name, self.color_index = "Keys", 5
        self.clip_slots = [types.SimpleNamespace(has_clip=True, clip=clip)]


class Song(object):
    def __init__(self, clip):
        self.tracks = [Track(clip)]
        self.return_tracks = [types.SimpleNamespace(name="A-Reverb", color_index=9)]
        self.scenes = [types.SimpleNamespace(name="Verse", color_index=1)]


@pytest.fixture
def clip():
    return Clip()


@pytest.fixture
def inst(script_module, clip):
    return make_inst(script_module, Song(clip))


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


NEW = [{"pitch": 60, "start_time": 0, "duration": 1}, {"pitch": 64, "start_time": 1, "duration": 1},
       {"pitch": 67, "start_time": 2, "duration": 2}]
R = dict(track_index=0, clip_index=0, expected_clip_name="Riff")


def test_replace_previews_by_default(inst, clip):
    result = ok(run(inst, "replace_clip_notes", notes=NEW, **R))
    assert result["applied"] is False and result["existing_note_count"] == 2 and result["new_note_count"] == 3
    assert [n.pitch for n in clip.notes] == [36, 40]


def test_replace_swaps_every_note(inst, clip):
    result = ok(run(inst, "replace_clip_notes", notes=NEW, confirm=True, **R))
    assert result["applied"] is True and result["verified"] is True and result["clip_note_count"] == 3
    assert sorted(n.pitch for n in clip.notes) == [60, 64, 67]


def test_a_new_note_outside_the_clip_is_an_error_and_the_old_notes_stay(inst, clip):
    bad = NEW + [{"pitch": 72, "start_time": 9}]
    message = err(run(inst, "replace_clip_notes", notes=bad, confirm=True, **R))
    assert "would never play" in message and "Nothing was changed" in message
    assert [n.pitch for n in clip.notes] == [36, 40]


def test_a_malformed_note_changes_nothing(inst, clip):
    assert "unknown field" in err(run(inst, "replace_clip_notes", confirm=True,
                                      notes=[{"pitch": 60, "foo": 1}], **R))
    assert len(clip.notes) == 2


def test_a_failed_write_puts_the_old_notes_back(inst, clip):
    clip.fail_next_write = True
    message = err(run(inst, "replace_clip_notes", notes=NEW, confirm=True, **R))
    assert "the 2 old notes were put back WITHOUT their probability" in message
    assert sorted(n.pitch for n in clip.notes) == [36, 40]
    assert all(n.probability == 1.0 for n in clip.notes)   # this fake has no add_new_notes


def test_a_failed_write_and_a_failed_restore_say_so_and_point_to_undo(inst, clip, monkeypatch):
    monkeypatch.setattr(type(clip), "set_notes", lambda self, notes: (_ for _ in ()).throw(RuntimeError("no")))
    message = err(run(inst, "replace_clip_notes", notes=NEW, confirm=True, **R))
    assert "RESTORING THE OLD NOTES ALSO FAILED" in message and "undo" in message


def test_replace_needs_the_clip_name_and_a_real_boolean(inst, clip):
    assert "not 'Other'" in err(run(inst, "replace_clip_notes", notes=NEW, confirm=True,
                                    track_index=0, clip_index=0, expected_clip_name="Other"))
    assert "expected_clip_name is required" in err(run(inst, "replace_clip_notes", notes=NEW,
                                                       track_index=0, clip_index=0, confirm=True))
    assert "confirm must be" in err(run(inst, "replace_clip_notes", notes=NEW, confirm="yes", **R))
    assert len(clip.notes) == 2


def test_set_color_on_a_track_a_clip_and_a_scene(inst, clip):
    t = ok(run(inst, "set_color", kind="track", color_index=20, track_index=0))
    assert (t["previous_color_index"], t["color_index"], t["name"]) == (5, 20, "Keys")
    c = ok(run(inst, "set_color", kind="clip", color_index=11, track_index=0, clip_index=0))
    assert (c["previous_color_index"], clip.color_index) == (3, 11)
    s = ok(run(inst, "set_color", kind="scene", color_index=0, scene_index=0))
    assert s["name"] == "Verse" and s["color_index"] == 0
    r = ok(run(inst, "set_color", kind="track", color_index=4, track_index=0, track_type="return"))
    assert r["name"] == "A-Reverb"


def test_an_uncoloured_scene_reads_none_before(inst):
    inst._song.scenes[0].color_index = None
    result = ok(run(inst, "set_color", kind="scene", color_index=33, scene_index=0))
    assert result["previous_color_index"] is None and result["color_index"] == 33


@pytest.mark.parametrize("kwargs,needle", [
    (dict(kind="track", color_index=70, track_index=0), "0-69"),
    (dict(kind="track", color_index=-1, track_index=0), "0-69"),
    (dict(kind="track", color_index=True, track_index=0), "0-69"),
    (dict(kind="song", color_index=1), "kind must be"),
    (dict(kind="scene", color_index=1, scene_index=5), "scene index out of range"),
    (dict(kind="track", color_index=1, track_index=0, expected_name="Other"), "not 'Other'"),
])
def test_bad_colours_are_refused(inst, kwargs, needle):
    assert needle in err(run(inst, "set_color", **kwargs))


def test_tools(conn):
    conn.response = {"applied": False}
    assert call(server.replace_clip_notes, None, 0, 0, "Riff", NEW).startswith("NOT REPLACED")
    assert conn.sent[-1][1]["confirm"] is False
    assert "expected_clip_name is required" in call(server.replace_clip_notes, None, 0, 0, None, NEW, confirm=True)
    call(server.set_color, None, "clip", 5, track_index=0, clip_index=1)
    assert conn.sent[-1] == ("set_color", {"kind": "clip", "color_index": 5, "track_type": "track",
                                           "track_index": 0, "clip_index": 1})
    assert {"replace_clip_notes", "set_color"} <= MODIFYING_TOOLS
