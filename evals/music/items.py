"""The eval items. Answer keys are computed by theory.py, never typed in by hand.

Topics follow the theory references in tubone24/midi-mcp-server (progressions, harmony,
modes and scales, voice leading, rhythm) and the deterministic checks in
voho/midi-composer-mcp, both MIT-licensed, plus what is particular to Ableton Live.
"""
from . import theory

NOTES_FORMAT = ('{"notes": [{"pitch": <MIDI number>, "start_time": <beats from clip start>, '
                '"duration": <beats>, "velocity": <1-127>}, ...]}')


def _item(id, category, prompt, grader, fmt, **params):
    return {"id": id, "category": category, "grader": grader, "params": params,
            "prompt": prompt + "\n\nEnd your reply with one ```json block in exactly this shape:\n" + fmt}


def chord_spelling():
    for symbol in ["Bb7#9", "F#m7b5", "Ebmaj7#11", "C#dim7", "Ab7b9", "Dm(maj7)",
                   "E9", "Bbm9", "Gbmaj9", "B7sus4", "Cm6", "F#aug"]:
        yield _item("chord_spelling/" + symbol, "chord_spelling",
                    "Which notes make up the chord %s? Spell each note correctly for the chord "
                    "(one note per chord degree; use # and b)." % symbol,
                    "note_names", '{"notes": ["<note>", ...]}', expected=theory.chord_notes(symbol))


def scales_modes():
    for tonic, name in [("E", "phrygian dominant"), ("Bb", "lydian"), ("F#", "harmonic minor"),
                        ("Db", "mixolydian"), ("C#", "locrian"), ("G", "melodic minor"),
                        ("Ab", "dorian"), ("B", "phrygian"), ("F", "lydian dominant"),
                        ("Eb", "natural minor"), ("C#", "major pentatonic"), ("Gb", "major")]:
        label = name + (" (ascending)" if name == "melodic minor" else "")
        yield _item("scales_modes/%s %s" % (tonic, name), "scales_modes",
                    "List the notes of %s %s, starting on %s, spelled with one letter per scale degree."
                    % (tonic, label, tonic),
                    "note_names", '{"notes": ["<note>", ...]}', expected=theory.scale_notes(tonic, name))


def roman_numerals():
    for tonic, mode, numerals in [
            ("Ab", "major", ["vi", "ii", "V7", "I"]),
            ("C", "minor", ["i", "iv", "V7", "i"]),
            ("C", "major", ["I", "bVII", "bVI", "V"]),
            ("D", "major", ["I", "V/V", "V", "I"]),
            ("E", "minor", ["i", "VI", "III", "VII"]),
            ("F", "major", ["I", "iii", "IV", "iv"]),
            ("G", "major", ["ii7", "V7", "Imaj7"]),
            ("Bb", "major", ["I", "N6", "V7", "I"]),
            ("Eb", "major", ["I", "V7/vi", "vi", "IV"]),
            ("A", "minor", ["iø7".replace("iø", "iiø"), "V7", "i"]),
            ("B", "major", ["I", "vi", "IV", "V"]),
            ("F#", "minor", ["i", "VI", "VII", "i"])]:
        expected = [theory.chord_notes(theory.roman_chord(n, tonic, mode)) for n in numerals]
        yield _item("roman_numerals/%s %s %s" % (tonic, mode, "-".join(numerals)), "roman_numerals",
                    "In %s %s, write out the chords %s. Give the notes of each chord (minor-key V "
                    "and vii take the raised leading tone; N6 is the Neapolitan sixth)."
                    % (tonic, mode, " – ".join(numerals)),
                    "chord_list", '{"chords": [["<note>", ...], ...]}  (one inner list per chord, in order)',
                    expected=expected, numerals=numerals)


INTERVALS = [("minor sixth", "above", "E", 8, 6), ("augmented fourth", "above", "Bb", 6, 4),
             ("major seventh", "above", "Gb", 11, 7), ("diminished fifth", "above", "B", 6, 5),
             ("minor third", "below", "D", 3, 3), ("perfect fourth", "above", "F#", 5, 4),
             ("major sixth", "above", "Ab", 9, 6), ("minor seventh", "above", "C#", 10, 7),
             ("augmented second", "above", "Eb", 3, 2)]


def intervals():
    for name, way, root, semis, degree in INTERVALS:
        if way == "above":
            want = theory.note_at(root, semis, degree)
        else:  # the note below is the one whose interval above reaches `root`
            letter = theory.LETTERS[(theory.LETTERS.index(root[0]) - degree + 1) % 7]
            want = theory.spell(letter, (theory.pc(root) - semis - theory.LETTER_PC[letter] + 6) % 12 - 6)
        yield _item("intervals/%s %s %s" % (name, way, root), "intervals",
                    "What note is a %s %s %s? Spell it as the interval requires." % (name, way, root),
                    "note_names", '{"notes": ["<note>"]}', expected=[want])


def live_conventions():
    cases = [
        ("live_c3", "In Ableton Live's note naming, what MIDI note number is the note Live shows as C3?", 60),
        ("live_a2", "In Ableton Live's note naming, what MIDI note number is A2?", 57),
        ("live_f#4", "In Ableton Live's note naming, what MIDI note number is F#4?", 78),
        ("live_a3_440", "What MIDI note number is concert A (440 Hz), and is it the note Ableton Live labels A3? Give the MIDI number.", 69),
        ("drum_rack_pad", "In Ableton Live, what MIDI note number does the bottom-left pad of a default Drum Rack play?", 36),
        ("pos_bar2_beat3", "In a 4/4 MIDI clip in Live, what start_time (in beats from the clip start) is beat 3 of bar 2?", 6.0),
        ("pos_16th", "In a 4/4 clip in Live, what start_time (in beats) is the 4th sixteenth note of beat 2 in bar 3?", 9.75),
        ("bar_6_8", "In Live, how long is one bar of 6/8, in beats (Live's beat is a quarter note)?", 3.0),
        ("bar_7_8", "In Live, how long is one bar of 7/8, in beats (quarter notes)?", 3.5),
        ("triplet8", "What is the duration of one eighth-note triplet, in beats (quarter notes)?", 1 / 3.0),
        ("dotted8", "What is the duration of a dotted eighth note, in beats (quarter notes)?", 0.75),
        ("gm_closed_hat", "In the General MIDI drum map, what note number is the closed hi-hat?", 42),
        ("gm_crash", "In the General MIDI drum map, what note number is Crash Cymbal 1?", 49),
        ("seconds_to_beats", "At 128 BPM, how many beats long is a 30-second section?", 64.0),
        ("arr_bar5", "In Live's Arrangement in 4/4, what is the position in beats of the start of bar 5?", 16.0),
        ("transpose", "A clip is in A minor. By how many semitones should it be transposed to land in F# minor, "
                      "taking the smaller move? Give a signed number (negative = down).", -3),
    ]
    for id, prompt, value in cases:
        yield _item("live_conventions/" + id, "live_conventions", prompt, "number",
                    '{"value": <number>}', expected=value, tolerance=0.01)


def chord_id():
    for pitches, symbol, symmetric in [
            ([62, 65, 69, 72], "Dm7", False), ([55, 59, 62, 65], "G7", False),
            ([64, 67, 72], "C/E", False), ([61, 64, 67, 70], "C#dim7", True),
            ([58, 62, 65, 69], "Bbmaj7", False), ([57, 60, 64, 67], "Am7", False),
            ([50, 54, 57, 60, 64], "D9", False), ([59, 62, 65, 69], "Bm7b5", False),
            ([53, 56, 60, 64], "Fm(maj7)", False), ([48, 55, 64, 70, 74], "C9", False),
            ([56, 60, 63, 67], "Abmaj7", False), ([52, 56, 60], "Eaug", True)]:
        yield _item("chord_id/" + symbol, "chord_id",
                    "A MIDI clip plays these notes together (MIDI numbers, lowest first): %s. "
                    "Name the chord with a standard chord symbol (use a slash only for an inversion)." % pitches,
                    "chord_name", '{"symbol": "<chord symbol>"}', expected=symbol, symmetric=symmetric)


def progression_midi():
    for id, tonic, mode, numerals, rhythm, extra in [
            ("E_pop_block", "E", "major", ["I", "V", "vi", "IV"], "block",
             "Use root-position triads with the root doubled an octave below as a bass note."),
            ("Am_block", "A", "minor", ["i", "VI", "III", "VII"], "block",
             "Use triads in any voicing with the root as the lowest note."),
            ("Dm_V7_block", "D", "minor", ["i", "iv", "V7", "i"], "block",
             "Use any voicing with the root as the lowest note; include every chord tone, including the seventh."),
            ("Bb_jazz_block", "Bb", "major", ["ii7", "V7", "Imaj7", "Imaj7"], "block",
             "Use seventh-chord voicings containing every chord tone, root as the lowest note."),
            ("G_arp", "G", "major", ["I", "vi", "ii", "V"], "eighths",
             "Arpeggiate: one note on every eighth note, only chord tones, every chord tone used at least once, "
             "and the root as the lowest note in each bar."),
            ("C#m_arp", "C#", "minor", ["i", "iv", "i", "V"], "eighths",
             "Arpeggiate: one note on every eighth note, only chord tones, every chord tone used at least once, "
             "and the root as the lowest note in each bar.")]:
        chords = [theory.roman_chord(n, tonic, mode) for n in numerals]
        yield _item("progression_midi/" + id, "progression_midi",
                    "Write MIDI notes for a 4/4 clip with the progression %s in %s %s, one chord per bar "
                    "(each chord lasts the whole bar: 4 beats), %d bars in total. %s Keep all pitches between "
                    "MIDI 36 and 84 and use velocity 90. No note may last past the end of its bar."
                    % (" – ".join(numerals), tonic, mode, len(numerals), extra),
                    "progression", NOTES_FORMAT, chords=chords, beats_per_chord=4, range=(36, 84),
                    rhythm=rhythm, bass_root=True)


def voice_leading():
    for tonic, mode, numerals in [("C", "major", ["I", "IV", "V", "I"]),
                                  ("G", "major", ["I", "vi", "IV", "V", "I"]),
                                  ("A", "minor", ["i", "iv", "V", "i"]),
                                  ("F", "major", ["I", "ii", "V7", "I"]),
                                  ("D", "major", ["I", "V", "vi", "IV"]),
                                  ("E", "minor", ["i", "VI", "iv", "V", "i"])]:
        chords = [theory.roman_chord(n, tonic, mode) for n in numerals]
        yield _item("voice_leading/%s %s %s" % (tonic, mode, "-".join(numerals)), "voice_leading",
                    "Write a four-part (SATB) realisation of %s in %s %s, one chord each, all in root position. "
                    "Rules: every chord contains its root and third (and the seventh for a seventh chord) and "
                    "nothing outside the chord; the bass sings the root; ranges soprano 60-81, alto 55-74, "
                    "tenor 48-69, bass 40-62 (MIDI numbers); no voice crossing; no more than an octave between "
                    "soprano and alto or alto and tenor; no parallel or consecutive fifths or octaves between "
                    "any two voices."
                    % (" – ".join(numerals), tonic, mode),
                    "satb", '{"soprano": [<MIDI>, ...], "alto": [...], "tenor": [...], "bass": [...]}  '
                    '(one number per chord in each list)', chords=chords)


def melody():
    for id, tonic, scale, chords in [("D_dorian", "D", "dorian", ["Dm7", "G7", "Dm7", "G7"]),
                                     ("C_major", "C", "major", ["C", "F", "G", "C"]),
                                     ("A_harmonic", "A", "harmonic minor", ["Am", "Dm", "E", "Am"]),
                                     ("F_lydian", "F", "lydian", ["Fmaj7", "G", "Fmaj7", "Fmaj7"])]:
        yield _item("melody/" + id, "melody",
                    "Write a 4-bar melody in 4/4 in %s %s over the chords %s (one chord per bar). Rules: "
                    "every note in %s %s; the note sounding on beat 1 and on beat 3 of each bar is a tone of "
                    "that bar's chord; one note at a time with no rests, starting at 0 and filling exactly 16 "
                    "beats; start times and durations on the eighth-note grid; lowest to highest note no more "
                    "than 14 semitones; end on %s."
                    % (tonic, scale, " | ".join(chords), tonic, scale, tonic),
                    "melody", NOTES_FORMAT, tonic=tonic, scale=scale, chords=chords, max_range=14)


KIT = "Use these drum notes: kick 36, rimshot 37, snare 38, clap 39, closed hi-hat 42, open hi-hat 46."
BACKBEAT = ["snare", "clap", "rim"]


def drums():
    for id, ask, rules in [
            ("house", "a classic four-on-the-floor house beat (124 BPM) with kick, clap and off-beat open hi-hats",
             [{"name": "kick_every_beat", "kinds": ["kick"], "at": [0, 1, 2, 3]},
              {"name": "clap_on_2_and_4", "kinds": BACKBEAT, "every_bar": True, "at": [1, 3], "not_at": [0, 2]},
              {"name": "open_hat_offbeats", "kinds": ["open_hat"], "at": [0.5, 1.5, 2.5, 3.5]}]),
            ("rock", "a basic rock beat (120 BPM) with straight eighth-note closed hi-hats",
             [{"name": "kick_on_1_and_3", "kinds": ["kick"], "at": [0, 2]},
              {"name": "snare_on_2_and_4", "kinds": BACKBEAT, "every_bar": True, "at": [1, 3], "not_at": [0, 2]},
              {"name": "eighth_hats", "kinds": ["closed_hat"], "at": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5]}]),
            ("trap", "a trap beat at 140 BPM with a half-time feel and busy closed hi-hats",
             [{"name": "snare_on_3_only", "kinds": BACKBEAT, "every_bar": True, "at": [2], "not_at": [1, 3]},
              {"name": "kick_on_1", "kinds": ["kick"], "at": [0]},
              {"name": "busy_hats", "kinds": ["closed_hat"], "min_count": 8}]),
            ("dnb", "a classic two-step drum & bass beat at 174 BPM",
             [{"name": "snare_on_2_and_4", "kinds": BACKBEAT, "every_bar": True, "at": [1, 3], "not_at": [0, 2]},
              {"name": "kick_on_1_and_and_of_3", "kinds": ["kick"], "at": [0, 2.5], "not_at": [1, 3]}]),
            ("dembow", "a reggaeton dembow beat at 95 BPM",
             [{"name": "kick_every_beat", "kinds": ["kick"], "at": [0, 1, 2, 3]},
              {"name": "dembow_snare", "kinds": BACKBEAT, "at": [0.75, 1.5, 2.75, 3.5]}]),
            ("one_drop", "a reggae one-drop beat at 75 BPM",
             [{"name": "drop_on_3", "kinds": ["kick"], "at": [2], "not_at": [0]},
              {"name": "rim_or_snare_on_3", "kinds": BACKBEAT, "at": [2]}])]:
        yield _item("drums/" + id, "drums",
                    "Write 2 bars of %s for a Drum Rack clip in 4/4 (8 beats). %s" % (ask, KIT),
                    "drums", NOTES_FORMAT, rules=rules, bars=2)


# What add_notes_to_clip's description teaches about its notation parameter (MCP_Server/server.py).
NOTATION_SPEC = """One idea per line; nothing carries from one line to the next.
Events: POSITION PITCHES [LENGTH] [vVEL] [pPROB], e.g. "1.1 C3 E3 G3 1/1 v90" (Live's bar.beat.sixteenth,
counted from 1; several positions as 1.1,1.3). Steps: PITCH PATTERN, e.g. "C1 x...x...x...x... *4"
(x hit, X accent, o ghost, . rest; 1/16 steps unless a note value is given; *4 repeats it 4 times,
@5 starts it at bar 5). Pitches in Live's naming (C3 = 60, C1 = 36) or MIDI numbers; lengths 1/4,
1/8. (dotted), 1/8t (triplet) or beats (0.5b); events default to 1/4. v80-100 is a random velocity
range, p0.5 a probability, m mutes, *N:K repeats N times K bars apart, # starts a comment."""

NOTATION_GRADERS = ("progression", "melody", "drums")


def as_notation(item):
    """The same item, answered in add_notes_to_clip's text notation instead of a JSON note list."""
    if item["grader"] not in NOTATION_GRADERS:
        return None
    head = item["prompt"].split("\n\nEnd your reply with one ```json block")[0]
    return dict(item, answer_format="notation",
                prompt=head + "\n\nEnd your reply with one ```notation block holding the notes in this "
                              "notation (4/4):\n" + NOTATION_SPEC)


CATEGORIES = [chord_spelling, scales_modes, roman_numerals, intervals, live_conventions,
              chord_id, progression_midi, voice_leading, melody, drums]


def all_items():
    return [item for category in CATEGORIES for item in category()]
