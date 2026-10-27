"""The music evals' answer keys and graders (evals/music).

An eval is only evidence if its keys are right and its graders pass right answers
and fail wrong ones. Keys are checked against music21 where it is installed
(`uv run --with music21 pytest tests/test_music_evals.py`) and against answers
worked out by hand everywhere.
"""
import json

import pytest

from evals.music import graders, items, theory


def reply(answer):
    return "Some reasoning.\n\n```json\n%s\n```" % json.dumps(answer)


def notes(*specs):
    return {"notes": [{"pitch": p, "start_time": s, "duration": d, "velocity": 90} for p, s, d in specs]}


def item(id):
    return next(i for i in items.all_items() if i["id"] == id)


# --- answer keys -----------------------------------------------------------------------

@pytest.mark.parametrize("symbol, want", [
    ("Bb7#9", ["Bb", "D", "F", "Ab", "C#"]), ("Ab7b9", ["Ab", "C", "Eb", "Gb", "Bbb"]),
    ("F#m7b5", ["F#", "A", "C", "E"]), ("C#dim7", ["C#", "E", "G", "Bb"]),
    ("Dm(maj7)", ["D", "F", "A", "C#"]), ("Gbmaj9", ["Gb", "Bb", "Db", "F", "Ab"]),
    ("C/E", ["E", "C", "G"]), ("F#aug", ["F#", "A#", "C##"]),
])
def test_chord_spellings_by_hand(symbol, want):
    assert theory.chord_notes(symbol) == want


@pytest.mark.parametrize("numeral, tonic, mode, want", [
    ("V7", "C", "minor", "G7"), ("viio7", "C", "minor", "Bdim7"), ("bVII", "C", "major", "Bb"),
    ("V/V", "D", "major", "E"), ("V7/vi", "Eb", "major", "G7"), ("N6", "Bb", "major", "Cb/Eb"),
    ("iiø7", "A", "minor", "Bm7b5"), ("Imaj7", "G", "major", "Gmaj7"), ("VII", "E", "minor", "D"),
])
def test_roman_numerals_by_hand(numeral, tonic, mode, want):
    assert theory.roman_chord(numeral, tonic, mode) == want


def test_scale_spellings_by_hand():
    assert theory.scale_notes("F#", "harmonic minor") == ["F#", "G#", "A", "B", "C#", "D", "E#"]
    assert theory.scale_notes("E", "phrygian dominant") == ["E", "F", "G#", "A", "B", "C", "D"]
    assert theory.scale_notes("Db", "mixolydian") == ["Db", "Eb", "F", "Gb", "Ab", "Bb", "Cb"]


def test_live_octave_convention():
    assert theory.live_midi("C3") == 60
    assert theory.live_midi("C1") == 36
    assert theory.live_midi("C-2") == 0


def test_every_item_has_a_grader_and_a_key():
    bank = items.all_items()
    assert len({i["id"] for i in bank}) == len(bank)
    for i in bank:
        assert i["grader"] in graders.GRADERS
        assert "```json" in i["prompt"]


def test_keys_agree_with_music21():
    harmony = pytest.importorskip("music21.harmony")
    from music21 import key, roman, scale
    for i in items.chord_spelling():
        symbol = i["id"].split("/", 1)[1]
        root = theory.chord_root(symbol)
        try:
            cs = harmony.ChordSymbol(root.replace("b", "-") + symbol[len(root):])
        except Exception:
            continue  # music21 doesn't parse m(maj7) or maj9; those are checked by hand above
        assert sorted({p.pitchClass for p in cs.pitches}) == theory.pcs(i["params"]["expected"]), symbol
    for i in items.roman_numerals():
        tonic, mode, _ = i["id"].split("/", 1)[1].split(" ")
        k = key.Key(tonic.replace("b", "-") if mode == "major" else tonic.replace("b", "-").lower())
        for numeral, want in zip(i["params"]["numerals"], i["params"]["expected"]):
            got = sorted({p.pitchClass for p in roman.RomanNumeral(numeral, k).pitches})
            assert got == theory.pcs(want), (i["id"], numeral)
    classes = {"major": scale.MajorScale, "harmonic minor": scale.HarmonicMinorScale,
               "melodic minor": scale.MelodicMinorScale, "natural minor": scale.MinorScale,
               "dorian": scale.DorianScale, "phrygian": scale.PhrygianScale, "lydian": scale.LydianScale,
               "mixolydian": scale.MixolydianScale, "locrian": scale.LocrianScale}
    for i in items.scales_modes():
        tonic, name = i["id"].split("/", 1)[1].split(" ", 1)
        if name in classes:
            got = [p.name.replace("-", "b") for p in classes[name](tonic.replace("b", "-")).getPitches()[:-1]]
            assert got == i["params"]["expected"], i["id"]


# --- graders ---------------------------------------------------------------------------

def test_extracts_last_json_block():
    text = 'First try ```json\n{"value": 1}\n``` no wait ```json\n{"value": 2}\n```'
    assert graders.extract_answer(text) == {"value": 2}
    assert graders.extract_answer("no answer here") is None


def test_note_names_pass_on_pitch_class_and_report_spelling():
    i = item("chord_spelling/Bb7#9")
    right = graders.grade(i, reply({"notes": ["B♭", "D", "F", "A♭", "C#"]}))
    assert right["passed"] and right["spelled"]
    enharmonic = graders.grade(i, reply({"notes": ["Bb", "D", "F", "Ab", "Db"]}))
    assert enharmonic["passed"] and not enharmonic["spelled"]
    assert not graders.grade(i, reply({"notes": ["Bb", "D", "F", "A", "C#"]}))["passed"]


def test_unreadable_answers_are_flagged_as_such():
    res = graders.grade(item("chord_spelling/Bb7#9"), "It's Bb D F Ab C#.")
    assert res["checks"] == {"readable": False}


def test_chord_list():
    i = item("roman_numerals/D major I-V/V-V-I")
    good = {"chords": [["D", "F#", "A"], ["E", "G#", "B"], ["A", "C#", "E"], ["D", "F#", "A"]]}
    assert graders.grade(i, reply(good))["passed"]
    good["chords"][1] = ["E", "G", "B"]
    res = graders.grade(i, reply(good))
    assert not res["passed"] and res["checks"]["chord_2_V/V"] is False


def test_number():
    assert graders.grade(item("live_conventions/live_c3"), reply({"value": 60}))["passed"]
    assert not graders.grade(item("live_conventions/live_c3"), reply({"value": 48}))["passed"]
    assert graders.grade(item("live_conventions/triplet8"), reply({"value": 0.333}))["passed"]


def test_chord_name_root_and_symmetric():
    assert graders.grade(item("chord_id/C/E"), reply({"symbol": "C/E"}))["passed"]
    assert graders.grade(item("chord_id/C/E"), reply({"symbol": "C"}))["passed"]
    assert not graders.grade(item("chord_id/Am7"), reply({"symbol": "C6"}))["passed"]  # same notes, wrong root
    assert graders.grade(item("chord_id/C#dim7"), reply({"symbol": "Edim7"}))["passed"]


def test_progression_block():
    i = item("progression_midi/E_pop_block")  # E B C#m A
    specs = []
    for bar, (root, triad) in enumerate([(40, [52, 56, 59]), (47, [59, 63, 66]), (49, [61, 64, 68]), (45, [57, 61, 64])]):
        specs += [(p, bar * 4.0, 4.0) for p in [root] + triad]
    assert graders.grade(i, reply(notes(*specs)))["passed"]
    specs[1] = (53, 0.0, 4.0)  # G# -> A in the first chord
    res = graders.grade(i, reply(notes(*specs)))
    assert not res["passed"] and not res["checks"]["chord_tones"]
    long_note = [(40, 0.0, 6.0)] + specs[1:]
    assert not graders.grade(i, reply(notes(*long_note)))["checks"]["no_overhang"]


def test_progression_arpeggio():
    i = item("progression_midi/G_arp")  # G Em Am D
    shapes = [[43, 47, 50, 55], [40, 43, 47, 52], [45, 48, 52, 57], [50, 54, 57, 62]]
    specs = [(shape[k % 4], bar * 4 + k * 0.5, 0.5) for bar, shape in enumerate(shapes) for k in range(8)]
    assert graders.grade(i, reply(notes(*specs)))["passed"]
    assert not graders.grade(i, reply(notes(*specs[:-1])))["checks"]["rhythm"]


def test_satb():
    i = item("voice_leading/C major I-IV-V-I")
    good = {"soprano": [72, 72, 71, 72], "alto": [67, 69, 67, 67], "tenor": [64, 65, 62, 64], "bass": [48, 53, 55, 48]}
    assert graders.grade(i, reply(good))["passed"], graders.grade(i, reply(good))
    parallel = {"soprano": [67, 72, 74, 72], "alto": [64, 65, 67, 67], "tenor": [60, 60, 59, 64], "bass": [48, 53, 55, 48]}
    res = graders.grade(i, reply(parallel))  # soprano/bass G-C over C-F: fifths in parallel
    assert not res["checks"]["no_parallel_5ths_8ves"]


def test_melody():
    i = item("melody/C_major")  # C | F | G | C, max range 14
    line = [(72, 0, 1), (74, 1, 1), (76, 2, 2), (77, 4, 1), (76, 5, 1), (72, 6, 2),
            (71, 8, 1), (72, 9, 1), (74, 10, 2), (76, 12, 2), (72, 14, 2)]
    assert graders.grade(i, reply(notes(*line)))["passed"]
    gap = line[:-1] + [(72, 14.5, 1.5)]
    assert not graders.grade(i, reply(notes(*gap)))["checks"]["no_overlaps_or_gaps"]
    off = line[:3] + [(74, 4, 1)] + line[4:]  # D on beat 1 over F
    assert not graders.grade(i, reply(notes(*off)))["checks"]["chord_tones_on_1_and_3"]


def test_drums():
    i = item("drums/house")
    bar = [(36, b, 0.25) for b in range(4)] + [(39, 1, 0.25), (39, 3, 0.25)] + [(46, b + 0.5, 0.25) for b in range(4)]
    two = bar + [(p, s + 4, d) for p, s, d in bar]
    assert graders.grade(i, reply(notes(*two)))["passed"]
    assert not graders.grade(i, reply(notes(*bar)))["passed"]  # second bar missing
    trap = item("drums/trap")
    backbeat = [(38, 1, 0.25), (38, 3, 0.25), (36, 0, 0.25)] + [(42, k * 0.5, 0.25) for k in range(8)]
    assert not graders.grade(trap, reply(notes(*(backbeat + [(p, s + 4, d) for p, s, d in backbeat]))))["passed"]
