"""The note tools also work on MIDI clips in the Arrangement (clip_start_time).

Measured on Live 12.4 Lite (2026-10-24): add_new_notes, get_notes_extended,
apply_note_modifications and remove_notes_extended all work on an Arrangement MIDI
clip, so the tools take the clip's start beat instead of a Session slot.
"""
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import FakeClip, FakeNote, make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class ArrClip(FakeClip):
    def __init__(self, start, end, notes=(), name=""):
        FakeClip.__init__(self, list(notes), length=end - start, name=name)
        self.start_time, self.end_time = float(start), float(end)
        self.is_arrangement_clip = True


class Track(object):
    def __init__(self, name, clips, foldable=False):
        self.name, self.is_foldable = name, foldable
        self.clip_slots = [types.SimpleNamespace(has_clip=False)]     # nothing in the Session
        self.arrangement_clips = clips


class Song(object):
    def __init__(self, *tracks):
        self.tracks = list(tracks)


@pytest.fixture
def arr():
    return ArrClip(16, 24, [FakeNote(1, 60, 0.0, 1.0), FakeNote(2, 64, 2.0, 1.0)], name="Riff")


@pytest.fixture
def inst(script_module, arr):
    return make_inst(script_module, Song(Track("Keys", [arr, ArrClip(32, 40)])))


def run(inst, command, **params):
    params.setdefault("track_index", 0)
    params.setdefault("clip_index", 0)
    params.setdefault("clip_start_time", 16.0)
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_notes_of_an_arrangement_clip_can_be_read(inst):
    result = ok(run(inst, "get_clip_notes"))
    assert result["clip_name"] == "Riff" and [n["pitch"] for n in result["notes"]] == [60, 64]


def test_notes_can_be_added_to_an_arrangement_clip(inst, arr):
    result = ok(run(inst, "add_notes_to_clip", notes=[{"pitch": 67, "start_time": 4, "duration": 1},
                                                      {"pitch": 71, "start_time": 9}]))
    assert result["note_count"] == 1 and [r["index"] for r in result["rejected"]] == [1]
    assert sorted(n.pitch for n in arr.notes) == [60, 64, 67]


def test_notes_can_be_edited_in_place_removed_quantized_and_replaced(inst, arr):
    ok(run(inst, "apply_note_modifications", notes=[{"note_id": 1, "pitch": 62}], dry_run=False))
    assert sorted(n.pitch for n in arr.notes) == [62, 64]
    assert ok(run(inst, "remove_notes_from_clip", from_time=0, time_span=1, from_pitch=0,
                  pitch_span=128, dry_run=False))["removed"] is True
    assert [n.pitch for n in arr.notes] == [64]
    result = ok(run(inst, "replace_clip_notes", expected_clip_name="Riff", confirm=True,
                    notes=[{"pitch": 50, "start_time": 0, "duration": 1}]))
    assert result["applied"] is True and [n.pitch for n in arr.notes] == [50]
    ok(run(inst, "clear_notes_from_clip"))
    assert arr.notes == []


def test_the_right_clip_is_found_by_its_start_and_a_wrong_start_lists_the_real_ones(inst):
    assert ok(run(inst, "get_clip_notes", clip_start_time=32.0))["note_count"] == 0
    message = err(run(inst, "get_clip_notes", clip_start_time=20.0))
    assert "No Arrangement clip starts at beat 20.0" in message and "16.0, 32.0" in message


def test_without_clip_start_time_the_session_slot_is_used_as_before(inst):
    message = err(inst._process_command({"type": "get_clip_notes",
                                         "params": {"track_index": 0, "clip_index": 0}}))
    assert "No clip in slot" in message


def test_a_group_track_is_refused(script_module, arr):
    i = make_inst(script_module, Song(Track("Group", [arr], foldable=True)))
    assert "group track" in err(run(i, "get_clip_notes"))


def test_tools_forward_clip_start_time(conn):
    conn.response = {"notes": [], "note_count": 0}
    call(server.get_clip_notes, None, 0, 0, clip_start_time=16.0)
    assert conn.sent[-1][1]["clip_start_time"] == 16.0
    call(server.add_notes_to_clip, None, 0, 0, [{"pitch": 60}], clip_start_time=16.0)
    assert conn.sent[-1][1]["clip_start_time"] == 16.0
    call(server.get_clip_notes, None, 0, 0)
    assert "clip_start_time" not in conn.sent[-1][1]


@pytest.mark.parametrize("tool,args,kwargs", [
    (server.remove_notes_from_clip, (None, 0, 0, 0.0, 1.0, 0, 128), {}),
    (server.apply_note_modifications, (None, 0, 0, [{"note_id": 1, "pitch": 62}]), {}),
    (server.quantize_clip, (None, 0, 0, "1/8"), {}),
    (server.replace_clip_notes, (None, 0, 0, "Riff", [{"pitch": 60}]), {}),
    (server.clear_notes_from_clip, (None, 0, 0), {}),
    (server.get_clip_info, (None, 0, 0), {}),
])
def test_every_note_tool_forwards_clip_start_time(conn, tool, args, kwargs):
    conn.response = {"applied": False}
    call(tool, *args, clip_start_time=16.0, **kwargs)
    assert conn.sent[-1][1]["clip_start_time"] == 16.0
    call(tool, *args, **kwargs)
    assert "clip_start_time" not in conn.sent[-1][1]
