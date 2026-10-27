"""The small amount of music theory the graders need, written out so it can be audited.

Answer keys come from these tables; tests/test_music_evals.py checks them against
music21 and against answers worked out by hand, so a wrong key can't pass silently.
"""
import re

LETTERS = "CDEFGAB"
LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTAL = {"": 0, "#": 1, "##": 2, "x": 2, "b": -1, "bb": -2,
              "♯": 1, "♭": -1, "\U0001d12a": 2, "\U0001d12b": -2}

_NOTE_RE = re.compile(r"^\s*([A-Ga-g])(##|bb|#|b|x|♯|♭|\U0001d12a|\U0001d12b)?\s*(-?\d+)?\s*$")


def parse_note(name):
    """'Eb' -> ('E', -1, None); 'F#3' -> ('F', 1, 3). Raises ValueError on anything else."""
    m = _NOTE_RE.match(str(name))
    if not m:
        raise ValueError("not a note name: %r" % (name,))
    letter, acc, octave = m.group(1).upper(), m.group(2) or "", m.group(3)
    return letter, ACCIDENTAL[acc], int(octave) if octave is not None else None


def pc(name):
    letter, alter, _ = parse_note(name)
    return (LETTER_PC[letter] + alter) % 12


def spell(letter, alter):
    return letter + {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}[alter]


def canonical(name):
    """One spelling per written note, so 'E♭' and 'Eb' compare equal."""
    letter, alter, _ = parse_note(name)
    return spell(letter, alter)


def live_midi(name):
    """Ableton Live names MIDI 60 'C3' (not 'C4' as in scientific pitch)."""
    letter, alter, octave = parse_note(name)
    if octave is None:
        raise ValueError("needs an octave: %r" % (name,))
    return (octave + 2) * 12 + LETTER_PC[letter] + alter


def note_at(root, semitones, degree):
    """The note `semitones` above `root`, written on the letter `degree` steps up (1 = unison).

    note_at('Bb', 4, 3) -> 'D'; note_at('E', 8, 6) -> 'C'; note_at('C', 6, 4) -> 'F#'.
    """
    letter, alter, _ = parse_note(root)
    target_letter = LETTERS[(LETTERS.index(letter) + degree - 1) % 7]
    natural = (LETTER_PC[target_letter] - LETTER_PC[letter] - alter) % 12
    diff = (semitones - natural + 6) % 12 - 6
    if diff not in (-2, -1, 0, 1, 2):
        raise ValueError("can't spell %s + %d on degree %d" % (root, semitones, degree))
    return spell(target_letter, diff)


# Chord qualities as (semitones, degree) pairs from the root; degree picks the letter.
CHORDS = {
    "": [(0, 1), (4, 3), (7, 5)],
    "m": [(0, 1), (3, 3), (7, 5)],
    "dim": [(0, 1), (3, 3), (6, 5)],
    "aug": [(0, 1), (4, 3), (8, 5)],
    "sus2": [(0, 1), (2, 2), (7, 5)],
    "sus4": [(0, 1), (5, 4), (7, 5)],
    "6": [(0, 1), (4, 3), (7, 5), (9, 6)],
    "m6": [(0, 1), (3, 3), (7, 5), (9, 6)],
    "7": [(0, 1), (4, 3), (7, 5), (10, 7)],
    "maj7": [(0, 1), (4, 3), (7, 5), (11, 7)],
    "m7": [(0, 1), (3, 3), (7, 5), (10, 7)],
    "m7b5": [(0, 1), (3, 3), (6, 5), (10, 7)],
    "dim7": [(0, 1), (3, 3), (6, 5), (9, 7)],
    "mMaj7": [(0, 1), (3, 3), (7, 5), (11, 7)],
    "7sus4": [(0, 1), (5, 4), (7, 5), (10, 7)],
    "9": [(0, 1), (4, 3), (7, 5), (10, 7), (14, 9)],
    "maj9": [(0, 1), (4, 3), (7, 5), (11, 7), (14, 9)],
    "m9": [(0, 1), (3, 3), (7, 5), (10, 7), (14, 9)],
    "7b9": [(0, 1), (4, 3), (7, 5), (10, 7), (13, 9)],
    "7#9": [(0, 1), (4, 3), (7, 5), (10, 7), (15, 9)],
    "7#11": [(0, 1), (4, 3), (7, 5), (10, 7), (18, 11)],
    "maj7#11": [(0, 1), (4, 3), (7, 5), (11, 7), (18, 11)],
    "13": [(0, 1), (4, 3), (7, 5), (10, 7), (14, 9), (21, 13)],
    "add9": [(0, 1), (4, 3), (7, 5), (14, 9)],
}

# Spellings a model may reasonably use for the same quality.
QUALITY_ALIASES = {
    "maj": "", "M": "", "min": "m", "-": "m", "mi": "m",
    "°": "dim", "o": "dim", "+": "aug",
    "°7": "dim7", "o7": "dim7",
    "ø7": "m7b5", "ø": "m7b5", "m7(b5)": "m7b5", "min7b5": "m7b5", "-7b5": "m7b5",
    "M7": "maj7", "Δ7": "maj7", "Maj7": "maj7", "ma7": "maj7",
    "min7": "m7", "-7": "m7", "mi7": "m7",
    "m(maj7)": "mMaj7", "mmaj7": "mMaj7", "m(Maj7)": "mMaj7", "minMaj7": "mMaj7", "-maj7": "mMaj7",
    "dom7": "7", "7(b9)": "7b9", "7(#9)": "7#9", "maj7(#11)": "maj7#11", "M7#11": "maj7#11",
    "sus": "sus4", "add2": "add9", "min6": "m6", "-6": "m6", "M9": "maj9", "min9": "m9", "-9": "m9",
}


def chord_root(symbol):
    m = re.match(r"^\s*([A-G](?:##|bb|#|b|\u266f|\u266d)?)", symbol)
    if not m:
        raise ValueError("not a chord symbol: %r" % (symbol,))
    return canonical(m.group(1))


def chord_notes(symbol):
    """'Bb7#9' -> ['Bb', 'D', 'F', 'Ab', 'C#']. Slash bass ('C/E') is put first."""
    symbol = symbol.strip().replace("♭", "b").replace("♯", "#")
    bass = None
    if "/" in symbol and not symbol.endswith("/"):
        symbol, bass = symbol.split("/", 1)
    m = re.match(r"^([A-G](?:##|bb|#|b)?)(.*)$", symbol)
    if not m:
        raise ValueError("not a chord symbol: %r" % (symbol,))
    root, quality = m.group(1), m.group(2).strip()
    quality = QUALITY_ALIASES.get(quality, quality)
    if quality not in CHORDS:
        raise ValueError("unknown chord quality: %r" % (quality,))
    notes = [note_at(root, s, d) for s, d in CHORDS[quality]]
    if bass:
        bass = canonical(bass)
        notes = [bass] + [n for n in notes if pc(n) != pc(bass)]
    return notes


# Scales and modes as (semitones, degree) from the tonic.
def _heptatonic(steps):
    out, s = [], 0
    for i, step in enumerate([0] + steps[:-1]):
        s += step
        out.append((s, i + 1))
    return out


SCALES = {
    "major": _heptatonic([2, 2, 1, 2, 2, 2, 1]),
    "ionian": _heptatonic([2, 2, 1, 2, 2, 2, 1]),
    "dorian": _heptatonic([2, 1, 2, 2, 2, 1, 2]),
    "phrygian": _heptatonic([1, 2, 2, 2, 1, 2, 2]),
    "lydian": _heptatonic([2, 2, 2, 1, 2, 2, 1]),
    "mixolydian": _heptatonic([2, 2, 1, 2, 2, 1, 2]),
    "natural minor": _heptatonic([2, 1, 2, 2, 1, 2, 2]),
    "aeolian": _heptatonic([2, 1, 2, 2, 1, 2, 2]),
    "locrian": _heptatonic([1, 2, 2, 1, 2, 2, 2]),
    "harmonic minor": _heptatonic([2, 1, 2, 2, 1, 3, 1]),
    "melodic minor": _heptatonic([2, 1, 2, 2, 2, 2, 1]),
    "phrygian dominant": _heptatonic([1, 3, 1, 2, 1, 2, 2]),
    "lydian dominant": _heptatonic([2, 2, 2, 1, 2, 1, 2]),
    "major pentatonic": [(0, 1), (2, 2), (4, 3), (7, 5), (9, 6)],
    "minor pentatonic": [(0, 1), (3, 3), (5, 4), (7, 5), (10, 7)],
    "blues": [(0, 1), (3, 3), (5, 4), (6, 5), (7, 5), (10, 7)],
}


def scale_notes(tonic, name):
    notes = []
    for s, d in SCALES[name]:
        try:
            notes.append(note_at(tonic, s, d))
        except ValueError:
            notes.append(note_at(tonic, s, d - 1))  # blues b5 written as #4 when b5 can't be
    return notes


def pcs(names):
    return sorted({pc(n) for n in names})


# Roman numerals: which scale degree, which quality, any chromatic shift of the root.
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}


def roman_chord(numeral, tonic, mode="major"):
    """'V7' in 'C' -> 'G7'; 'bVI' in 'C' -> 'Ab'; 'V/V' in 'D' -> 'E'; 'N6' in 'Bb' -> 'Cb/Eb'.

    Uppercase = major, lowercase = minor, 'o' = diminished, 'ø' = half-diminished.
    In minor keys V and vii° take the raised leading tone, as in common practice.
    """
    if "/" in numeral and not numeral.startswith("N"):
        head, of = numeral.split("/", 1)
        local_root = chord_notes(roman_chord(of, tonic, mode))[0]
        return roman_chord(head, local_root, "major" if of.lstrip("b#")[0].isupper() else "minor")
    if numeral.startswith("N"):
        root = note_at(tonic, 1, 2)
        return root + "/" + note_at(root, 4, 3)
    m = re.match(r"^(b|#)?(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)(o|°|ø|\+)?(maj7|7)?$", numeral)
    if not m:
        raise ValueError("unsupported numeral %r" % (numeral,))
    shift, rn, dim, seventh = m.groups()
    degree = _ROMAN[rn.upper()]
    scale = "major" if mode == "major" else "natural minor"
    root = scale_notes(tonic, scale)[degree - 1]
    if mode == "minor" and degree == 7 and rn.islower():
        root = scale_notes(tonic, "harmonic minor")[6]  # vii° on the leading tone
    if shift:
        # bVI etc. are measured against the MAJOR scale, the usual popular-music reading.
        major_root = scale_notes(tonic, "major")[degree - 1]
        letter, alter, _ = parse_note(major_root)
        root = spell(letter, alter + (-1 if shift == "b" else 1))
    if dim in ("o", "°"):
        quality = "dim7" if seventh == "7" else "dim"
    elif dim == "ø":
        quality = "m7b5"
    elif dim == "+":
        quality = "aug"
    elif rn.isupper():
        quality = {"7": "7", "maj7": "maj7"}.get(seventh, "")
        if mode == "major" and seventh == "7" and degree in (1, 4) and not shift:
            quality = "maj7"  # I7 / IV7 in a major key are diatonic major sevenths
    else:
        quality = {"7": "m7", "maj7": "mMaj7"}.get(seventh, "m")
    return root + quality


# Time in Live is counted in beats (quarter notes) from the clip start.
def bar_beat(bar, beat=1, sixteenth=1, beats_per_bar=4):
    """1-based musical position -> Live start_time in beats."""
    return (bar - 1) * beats_per_bar + (beat - 1) + (sixteenth - 1) * 0.25
