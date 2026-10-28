"""A clip's own key and scale (Live 12.4.15 gave Clip root_note, scale_name, scale_mode and
scale_intervals, captured on Push 3 standalone) and scale degrees in the notation."""
import json

import pytest

import MCP_Server.server as server
from MCP_Server.notation import NotationError, Scale, name_of, parse
from tests.test_batch_1_10_16 import SCALES, ScaleSong, err, ok, run
from tests.test_notes_edit import FakeClip, FakeSong, make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class ScaleClip(FakeClip):
    """A MIDI clip with Live 12.4.15's scale properties, which behave like Song's."""
    def __init__(self, **kwargs):
        FakeClip.__init__(self, **kwargs)
        self.root_note, self._scale, self.scale_mode = 0, "Major", False

    scale_name = ScaleSong.scale_name
    scale_intervals = ScaleSong.scale_intervals


def song_with(clip):
    song = FakeSong(clip)
    song.root_note, song._scale, song.scale_mode = 0, "Major", True
    return song


# ----------------------------------------------------------------- the Remote Script

def test_get_clip_info_reports_the_clips_own_scale(script_module):
    clip = ScaleClip()
    clip.root_note, clip.scale_name = 9, "Minor"
    info = ok(run(make_inst(script_module, song_with(clip)), "get_clip_info", track_index=0, clip_index=0))
    assert info["scale"]["root_name"] == "A" and info["scale"]["scale_name"] == "Minor"
    assert info["scale"]["scale_notes"] == ["A", "B", "C", "D", "E", "F", "G"]


def test_a_live_before_12_4_15_has_no_clip_scale(script_module):
    info = ok(run(make_inst(script_module, song_with(FakeClip())), "get_clip_info", track_index=0, clip_index=0))
    assert "scale" not in info
    message = err(run(make_inst(script_module, song_with(FakeClip())), "set_clip_scale",
                      track_index=0, clip_index=0, root_note="A"))
    assert "12.4.15" in message


def test_set_clip_scale_changes_the_clip_and_not_the_set(script_module):
    clip = ScaleClip()
    song = song_with(clip)
    r = ok(run(make_inst(script_module, song), "set_clip_scale", track_index=0, clip_index=0,
               root_note="Bb", scale_name="Dorian", scale_mode=True))
    assert (clip.root_note, clip.scale_name, clip.scale_mode) == (10, "Dorian", True)
    assert (song.root_note, song._scale) == (0, "Major")
    assert r["before"]["scale_name"] == "Major" and r["after"]["root_name"] == "A#"
    assert r["clip_name"] == "Clip" and r["track_index"] == 0


def test_set_clip_scale_refuses_bad_input_and_changes_nothing(script_module):
    clip = ScaleClip()
    inst = make_inst(script_module, song_with(clip))
    assert "Unknown root note" in err(run(inst, "set_clip_scale", track_index=0, clip_index=0, root_note="H"))
    message = err(run(inst, "set_clip_scale", track_index=0, clip_index=0, scale_name="Klezmer"))
    assert "put back to 'Major'" in message and clip.scale_name == "Major"
    assert "Give root_note" in err(run(inst, "set_clip_scale", track_index=0, clip_index=0))
    assert "not a MIDI clip" in err(run(make_inst(script_module, song_with(ScaleClip(midi=False))),
                                        "set_clip_scale", track_index=0, clip_index=0, root_note="A"))


def test_set_clip_scale_is_in_the_capabilities(script_module):
    assert "set_clip_scale" in script_module.SCRIPT_CAPABILITIES


# ------------------------------------------------------------------- the notation

A_MINOR = Scale(9, SCALES["Minor"], "Minor")


def names(text, scale=A_MINOR):
    return [name_of(n["pitch"]) for n in parse(text, scale=scale)]


def test_degrees_count_from_the_root_in_octave_3():
    assert names("1.1 ^1 ^2 ^3 ^4 ^5 ^6 ^7") == ["A3", "B3", "C4", "D4", "E4", "F4", "G4"]
    assert names("1.1 ^1 ^8 ^15") == ["A3", "A4", "A5"]


def test_an_octave_and_accidentals():
    assert names("1.1 ^1:1 ^3 ^5 1/1") == ["A1", "C4", "E4"]
    assert names("1.1 ^#3 ^b7:2") == ["F#3", "C#4"]


def test_degrees_work_on_step_lines_and_mix_with_names():
    assert names("^1:1 x...x...") == ["A1", "A1"]
    assert names("1.1 ^1 C3") == ["C3", "A3"]


def test_a_degree_needs_a_scale_and_a_real_degree():
    with pytest.raises(NotationError, match="no scale"):
        parse("1.1 ^3")
    with pytest.raises(NotationError, match="count from"):
        parse("1.1 ^0", scale=A_MINOR)
    with pytest.raises(NotationError, match="0-127"):
        parse("1.1 ^1:8", scale=A_MINOR)


# ------------------------------------------------------------------------ the tools

@pytest.fixture
def live(conn):
    answers = {"get_session_info": {"signature_numerator": 4, "signature_denominator": 4},
               "get_clip_info": {"scale": {"root_note": 9, "root_name": "A", "scale_name": "Minor",
                                           "scale_mode": True, "scale_intervals": SCALES["Minor"],
                                           "scale_notes": ["A", "B", "C", "D", "E", "F", "G"]}},
               "get_song_scale": {"root_note": 0, "scale_name": "Major", "scale_intervals": SCALES["Major"]},
               "get_clip_notes": {"clip_name": "Bass", "notes": []},
               "add_notes_to_clip": {"note_count": 3}}

    def send(command_type, params=None):
        conn.sent.append((command_type, params or {}))
        return answers.get(command_type, {})
    conn.send_command = send
    conn.answers = answers
    return conn


def test_degrees_are_read_in_the_clips_scale(live):
    call(server.add_notes_to_clip, None, 1, 2, notation="1.1 ^1 ^3 ^5")
    assert ("get_clip_info", {"track_index": 1, "clip_index": 2}) in live.sent
    assert [n["pitch"] for n in live.sent[-1][1]["notes"]] == [69, 72, 76]


def test_without_a_clip_scale_degrees_use_the_sets(live):
    live.answers["get_clip_info"] = {"name": "Bass"}
    call(server.add_notes_to_clip, None, 0, 0, notation="1.1 ^1 ^3 ^5")
    assert [n["pitch"] for n in live.sent[-1][1]["notes"]] == [60, 64, 67]


def test_notation_without_degrees_does_not_read_the_scale(live):
    call(server.add_notes_to_clip, None, 0, 0, notation="1.1 C3")
    assert [c for c, _ in live.sent] == ["get_session_info", "add_notes_to_clip"]


def test_set_clip_scale_tool_sends_the_values(live):
    call(server.set_clip_scale, None, 0, 3, root_note="9", scale_name="Minor", clip_start_time=8.0)
    assert live.sent[-1] == ("set_clip_scale", {"track_index": 0, "clip_index": 3, "clip_start_time": 8.0,
                                                "root_note": 9, "scale_name": "Minor"})


def test_text_notes_name_the_clips_scale(live):
    out = call(server.get_clip_notes, None, 0, 0, format="text")
    assert "# clip scale: A Minor (A B C D E F G)" in out.splitlines()
    assert json.loads(call(server.get_clip_notes, None, 0, 0))["clip_name"] == "Bass"
