"""The text notation for notes (MCP_Server/notation.py) and the note tools that take and return it.

The notation saves tokens only if it is exact: these check that text means what the docs say,
that every mistake is reported with its line and writes nothing, and that any clip survives a
read back as text and a write of that text unchanged.
"""
import json
import random

import pytest

import MCP_Server.server as server
from MCP_Server.notation import NotationError, format_notes, parse, pitch_of
from tests.test_scenes import call, conn  # noqa: F401


def played(note):
    """The velocities Live can play for a note: it clamps velocity plus deviation to 1-127."""
    ends = (note["velocity"], note["velocity"] + note.get("velocity_deviation", 0))
    return max(1, min(ends)), min(127, max(ends))


def by_time(notes):
    return sorted(notes, key=lambda n: (n["start_time"], n["pitch"], n["duration"], n["mute"]))


# ----------------------------------------------------------------------- the notation

def test_pitches_use_lives_octave_numbering():
    assert pitch_of("C3") == 60 and pitch_of("C1") == 36 and pitch_of("C-2") == 0 and pitch_of("G8") == 127
    assert pitch_of("Bb2") == 58 and pitch_of("F#1") == 42 and pitch_of("36") == 36 and pitch_of("v90") is None


def test_an_event_line_is_a_chord_at_a_position():
    notes = parse("1.1 C3 E3 G3 1/1 v90")
    assert [n["pitch"] for n in notes] == [60, 64, 67]
    assert all(n["start_time"] == 0 and n["duration"] == 4.0 and n["velocity"] == 90 for n in notes)


def test_positions_lengths_and_options():
    [a] = parse("2.3.2 G4 1/8. p0.8 r90 m")
    assert (a["start_time"], a["duration"], a["probability"], a["release_velocity"], a["mute"]) == (
        6.25, 0.75, 0.8, 90, True)
    [b] = parse("1.1+1/8t E4 1/8t v80-100")
    assert b["start_time"] == pytest.approx(1 / 3.0, abs=1e-6) and b["duration"] == pytest.approx(1 / 3.0, abs=1e-6)
    assert b["velocity"] == 80 and b["velocity_deviation"] == 20
    [c] = parse("1.1 C3 v100-80")
    assert c["velocity_deviation"] == -20 and c["duration"] == 1.0  # events default to a quarter note
    assert [n["start_time"] for n in parse("1.1,1.3,2.1 C1 1/16")] == [0, 2, 4]
    assert parse("36 1.3,2.3 1/16 v108") == parse("1.3,2.3 36 1/16 v108")  # a position is a position anywhere
    assert "one position" in str(pytest.raises(NotationError, parse, "1.1 C3 1.3").value)
    assert parse("1.1 C3 0.5b")[0]["duration"] == 0.5 and parse("1.1 C3 3/4")[0]["duration"] == 3.0


def test_bars_follow_the_time_signature():
    assert parse("2.1 C3", 3, 4)[0]["start_time"] == 3.0
    assert parse("1.6.2 C3", 6, 8)[0]["start_time"] == 2.75  # 6/8: the beat is an eighth note
    assert "beats run 1-6" in str(pytest.raises(NotationError, parse, "1.7 C3", 6, 8).value)


def test_a_step_line_is_a_drum_pattern():
    kick = parse("C1 x...x...x...x... *2")
    assert [n["start_time"] for n in kick] == [0, 1, 2, 3, 4, 5, 6, 7] and kick[0]["duration"] == 0.25
    hats = parse("F#1 x.X.o.x. 1/16 v80")
    assert [(n["start_time"], n["velocity"]) for n in hats] == [(0, 80), (0.5, 127), (1.0, 40), (1.5, 80)]
    assert [n["start_time"] for n in parse("D1 ....|x...|....|x... @3")] == [9.0, 11.0]
    assert [n["start_time"] for n in parse("C1 x... *3:2")] == [0, 8, 16]
    assert [n["pitch"] for n in parse("C1 D1 x.")] == [36, 38]
    assert [n["start_time"] for n in parse("C1 x.x. 1/8t")] == pytest.approx([0, 2 / 3.0])


def test_lines_are_independent_and_comments_are_skipped():
    notes = parse("# a groove\n1.1 C3 v50  # soft\n\n1.2 D3\nF#1 x.  # F#1 is a note, not a comment")
    assert [(n["pitch"], n["velocity"]) for n in notes] == [(42, 100), (60, 50), (62, 100)]


def test_every_bad_line_is_named_and_nothing_is_returned():
    with pytest.raises(NotationError) as e:
        parse("1.1 C3\n1.5 D3\nC3 E3\n1.1 H3\n1.1 C3 v0\nC1 x... *0\n1.1 C3 1/4 1/8\n1.1 C3 r200")
    message = str(e.value)
    for line in range(2, 9):
        assert "line %d:" % line in message
    assert "line 1:" not in message
    assert "no notes" in str(pytest.raises(NotationError, parse, "# only a comment").value)
    assert "outside MIDI" in str(pytest.raises(NotationError, parse, "1.1 200").value)


def test_text_reads_back_compactly():
    text = format_notes(parse("C1 x...x...x...x... *2\n1.1 C3 E3 G3 1/1 v90\n1.3.3 G4 1/8. p0.8"))
    assert text.splitlines() == ["1.1,1.2,1.3,1.4,2.1,2.2,2.3,2.4 C1 1/16 v100", "1.1 C3 E3 G3 1/1 v90",
                                 "1.3.3 G4 1/8. v100 p0.8"]


def test_any_clip_survives_a_round_trip():
    rng = random.Random(7)
    for numerator, denominator in ((4, 4), (3, 4), (6, 8), (7, 8)):
        notes = []
        for _ in range(60):
            note = {"pitch": rng.randrange(128), "velocity": rng.randrange(1, 128), "mute": rng.random() < 0.1,
                    "start_time": round(rng.randrange(64) * rng.choice([0.25, 1 / 3.0, 0.125]), 6),
                    "duration": round(rng.choice([0.25, 0.5, 1 / 3.0, 0.75, 1.0, 2.5, 0.1]), 6)}
            if rng.random() < 0.3:
                note["velocity_deviation"] = rng.randrange(-20, 21) or 5
            if rng.random() < 0.3:
                note["probability"] = rng.choice([0.25, 0.5, 0.0])
            if rng.random() < 0.2:
                note["release_velocity"] = rng.randrange(128)
            notes.append(note)
        again = parse(format_notes(notes, numerator, denominator), numerator, denominator)
        for got, want in zip(by_time(again), by_time(notes)):
            assert got["pitch"] == want["pitch"] and got["mute"] == want["mute"]
            assert got["start_time"] == pytest.approx(want["start_time"], abs=1e-5)
            assert got["duration"] == pytest.approx(want["duration"], abs=1e-5)
            assert played(got) == played(want)
            assert got.get("probability") == want.get("probability")
            assert got.get("release_velocity", 64) == want.get("release_velocity", 64)
        assert len(again) == len(notes)


# --------------------------------------------------------------------------- the tools

@pytest.fixture
def live(conn):
    """The fake connection answers per command: a 3/4 Set, and a clip read."""
    answers = {"get_session_info": {"signature_numerator": 3, "signature_denominator": 4},
               "get_clip_notes": {"clip_name": "Riff", "length": 6.0, "note_count": 2,
                                  "notes": [{"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 90,
                                             "mute": False, "probability": 1.0, "velocity_deviation": 0.0,
                                             "release_velocity": 64.0},
                                            {"pitch": 60, "start_time": 3.0, "duration": 1.0, "velocity": 90,
                                             "mute": False}]},
               "add_notes_to_clip": {"note_count": 4}}

    def send(command_type, params=None):
        conn.sent.append((command_type, params or {}))
        return answers.get(command_type, {})
    conn.send_command = send
    return conn


def test_add_notes_takes_notation_in_the_sets_time_signature(live):
    out = call(server.add_notes_to_clip, None, 1, 2, notation="2.1 C3 E3\nC1 x..x..")
    command, params = live.sent[-1]
    assert command == "add_notes_to_clip" and params["track_index"] == 1 and params["clip_index"] == 2
    assert [(n["pitch"], n["start_time"]) for n in params["notes"]] == [(36, 0), (36, 0.75), (60, 3.0), (64, 3.0)]
    assert "Added 4 notes" in out


def test_a_bad_notation_writes_nothing(live):
    out = call(server.add_notes_to_clip, None, 0, 0, notation="1.1 C3\n1.9 D3")
    assert out.startswith("Error in the notation, nothing was written") and "line 2" in out
    assert [c for c, _ in live.sent] == ["get_session_info"]


def test_notes_or_notation_not_both_and_not_neither(live):
    assert "not both" in call(server.add_notes_to_clip, None, 0, 0, [{"pitch": 60}], notation="1.1 C3")
    assert "give notes" in call(server.add_notes_to_clip, None, 0, 0)
    assert live.sent == []


def test_a_json_list_still_works_as_before(live):
    notes = [{"pitch": 60, "start_time": 0, "duration": 1, "velocity": 100}]
    call(server.add_notes_to_clip, None, 0, 0, notes)
    assert live.sent == [("add_notes_to_clip", {"track_index": 0, "clip_index": 0, "notes": notes})]


def test_replace_takes_notation_and_keeps_its_preview(live):
    out = call(server.replace_clip_notes, None, 0, 0, "Riff", notation="1.1 C3 1/2")
    command, params = live.sent[-1]
    assert command == "replace_clip_notes" and params["confirm"] is False and params["expected_clip_name"] == "Riff"
    assert params["notes"] == [{"pitch": 60, "start_time": 0.0, "duration": 2.0, "velocity": 100, "mute": False}]
    assert out.startswith("NOT REPLACED")


def test_get_clip_notes_as_text(live):
    out = call(server.get_clip_notes, None, 0, 0, format="text")
    assert out.splitlines() == ["# clip_name: Riff", "# length: 6.0", "# 2 notes, positions in 3/4",
                                "1.1,2.1 C3 1/4 v90"]
    assert json.loads(call(server.get_clip_notes, None, 0, 0))["note_count"] == 2
    assert "format must be" in call(server.get_clip_notes, None, 0, 0, format="xml")
