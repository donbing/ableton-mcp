"""A compact text notation for MIDI notes, so a part costs a line per idea instead of a JSON object
per note. parse() turns text into the note dicts add_notes_to_clip takes; format_notes() turns notes
back into text, so reading a clip is cheap too.

Every line stands alone: nothing set on one line carries to the next. Two kinds of line:

  Events   POSITION[,POSITION...] PITCH [PITCH...] [LENGTH] [vVEL|vA-B] [pPROB] [rREL] [m] [*N[:K]]
           1.1 C3 E3 G3 1/1 v90        a chord at bar 1 beat 1, a whole note long
           1.3.3 G4 1/8. p0.8          bar 1, beat 3, third sixteenth; dotted eighth; plays 80%
           1.1+1/12 E4 1/12            a position plus an offset (here an eighth-note triplet)

  Steps    PITCH [PITCH...] PATTERN [PATTERN...] [STEP] [vVEL|vA-B] [pPROB] [rREL] [m] [@BAR] [*N[:K]]
           C1 x...x...x...x... *8      kick on every beat for 8 bars
           F#1 x.x.x.x.x.x.x.x. v70-90 eighth hats with random velocity
           x = hit, X = accent (velocity 127), o = ghost (half velocity), . or - = rest, | is ignored

Positions are Live's own bar.beat.sixteenth, counted from 1; a beat is the time signature's
denominator (an eighth in 6/8), as Live shows it. Pitches are names in Live's octave numbering
(C3 = MIDI 60, C1 = 36, the first Drum Rack pad), MIDI numbers, or scale degrees in the clip's scale:
^1 is the root in octave 3, ^5 the fifth degree, ^8 the root an octave up, ^b3 / ^#4 a semitone off the
scale, ^1:1 the root in octave 1 (so in A minor, ^1:1 ^3 ^5 is A1 C4 E4). LENGTH and STEP are note values
(1/4, 1/8. dotted, 1/8t triplet, 3/4) or beats (0.5b); events default to 1/4, steps to 1/16.
rN sets the release velocity, m mutes. vA-B is Live's own random velocity: velocity A with a deviation of B-A (B below A deviates down). *N repeats a line N
times, one bar apart (events) or back to back (steps); *N:K spaces the repeats K bars apart.
"""
import math
import re

LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
EPS = 1e-6

_NOTE = re.compile(r"^([A-G])(#|b)?(-?\d)$")
_DEGREE = re.compile(r"^\^(#|b)?(\d+)(?::(-?\d))?$")
_POSITION = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\+(\S+))?$")
_VALUE = re.compile(r"^(\d+)/(\d+)(\.|t)?$")
_BEATS = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)b$")
_VELOCITY = re.compile(r"^v(\d+)(?:-(\d+))?$")  # v122-140 is legal: Live clamps the played range
_PROBABILITY = re.compile(r"^p(0?\.\d+|1(?:\.0+)?|0)$")
_RELEASE = re.compile(r"^r(\d+)$")
_REPEAT = re.compile(r"^\*(\d+)(?::(\d+(?:\.\d+)?))?$")
_START = re.compile(r"^@(\d+)$")
_PATTERN = re.compile(r"^[xXo.\-|]{2,}$")
_COMMENT = re.compile(r"(?:^|\s)#")  # a comment starts a line or follows a space, so F#1 is a note

# Note values the formatter writes back by name, longest first.
_NAMED_VALUES = [("1/1", 4.0), ("1/2.", 3.0), ("1/2", 2.0), ("1/4.", 1.5), ("1/2t", 4.0 / 3), ("1/4", 1.0),
                 ("1/8.", 0.75), ("1/4t", 2.0 / 3), ("1/8", 0.5), ("1/16.", 0.375), ("1/8t", 1.0 / 3),
                 ("1/16", 0.25), ("1/16t", 1.0 / 6), ("1/32", 0.125)]


class NotationError(ValueError):
    pass


def pitch_of(token):
    """'C3' -> 60 (Live's numbering), 'Bb2' -> 58, '36' -> 36; None if the token is not a pitch."""
    m = _NOTE.match(token)
    if m:
        value = (int(m.group(3)) + 2) * 12 + LETTER[m.group(1)] + {"#": 1, "b": -1, None: 0}[m.group(2)]
    elif token.isdigit():
        value = int(token)
    else:
        return None
    if not 0 <= value <= 127:
        raise NotationError("pitch %s is outside MIDI 0-127" % token)
    return value


class Scale(object):
    """A key for scale degrees: root 0-11 (0 = C) and the scale's intervals from the root, as Live
    reports them (Minor -> 0 2 3 5 7 8 10)."""
    def __init__(self, root_note, intervals, name=""):
        self.root = int(root_note) % 12
        self.intervals = sorted(int(i) % 12 for i in intervals) or [0]
        self.name = name

    def pitch(self, token):
        """'^5' -> the fifth degree in octave 3; None if the token is not a degree."""
        m = _DEGREE.match(token)
        if not m:
            return None
        degree = int(m.group(2))
        if degree < 1:
            raise NotationError("%s: degrees count from ^1 (the root)" % token)
        octave = int(m.group(3)) if m.group(3) is not None else 3
        step, up = (degree - 1) % len(self.intervals), (degree - 1) // len(self.intervals)
        value = ((octave + 2) * 12 + self.root + self.intervals[step] + 12 * up
                 + {"#": 1, "b": -1, None: 0}[m.group(1)])
        if not 0 <= value <= 127:
            raise NotationError("%s is outside MIDI 0-127" % token)
        return value


def _pitch(token, scale):
    """A pitch token: a name, a MIDI number or (with a scale) a degree; None if it is none of these."""
    pitch = pitch_of(token)
    if pitch is not None or not token.startswith("^"):
        return pitch
    if scale is None:
        raise NotationError("%s is a scale degree, but there is no scale to read it in" % token)
    return scale.pitch(token)


def name_of(pitch):
    return "%s%d" % (NAMES[pitch % 12], pitch // 12 - 2)


def length_of(token):
    """'1/8' -> 0.5 beats, '1/8.' -> 0.75, '1/8t' -> 1/3, '3/4' -> 3.0, '0.5b' -> 0.5; None otherwise."""
    m = _VALUE.match(token)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if num == 0 or den == 0:
            raise NotationError("%s is not a note value" % token)
        beats = 4.0 * num / den
        return beats * {".": 1.5, "t": 2.0 / 3, None: 1.0}[m.group(3)]
    m = _BEATS.match(token)
    if m:
        beats = float(m.group(1))
        if beats <= 0:
            raise NotationError("%s is not a length" % token)
        return beats
    return None


class Meter(object):
    def __init__(self, numerator=4, denominator=4):
        if numerator < 1 or denominator not in (1, 2, 4, 8, 16, 32):
            raise NotationError("time signature %s/%s is not one Live has" % (numerator, denominator))
        self.numerator, self.denominator = numerator, denominator
        self.beat = 4.0 / denominator
        self.bar = numerator * self.beat

    def position(self, token):
        """'2.3.2' -> beats from the clip start; None if the token is not a position."""
        m = _POSITION.match(token)
        if not m:
            return None
        bar, beat, sixteenth = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
        if bar < 1 or not 1 <= beat <= self.numerator:
            raise NotationError("%s: bars count from 1 and beats run 1-%d in %d/%d"
                                % (token, self.numerator, self.numerator, self.denominator))
        per_beat = max(1, int(round(self.beat / 0.25)))
        if not 1 <= sixteenth <= per_beat:
            raise NotationError("%s: a beat here holds %d sixteenths" % (token, per_beat))
        time = (bar - 1) * self.bar + (beat - 1) * self.beat + (sixteenth - 1) * 0.25
        if m.group(4):
            offset = length_of(m.group(4))
            if offset is None:
                raise NotationError("%s: the offset after + must be a note value or beats" % token)
            time += offset
        return time

    def format_position(self, time):
        bar = int((time + EPS) // self.bar)
        rest = time - bar * self.bar
        beat = int((rest + EPS) // self.beat)
        rest -= beat * self.beat
        text = "%d.%d" % (bar + 1, beat + 1)
        sixteenths = rest / 0.25
        if abs(sixteenths - round(sixteenths)) < EPS:
            return text + (".%d" % (round(sixteenths) + 1) if round(sixteenths) else "")
        return text + "+" + format_length(rest)  # off the sixteenth grid: the beat plus an offset


def format_length(beats):
    for name, value in _NAMED_VALUES:
        if abs(beats - value) < EPS:
            return name
    return ("%.6f" % beats).rstrip("0").rstrip(".") + "b"


def _options(tokens, line_no, allow):
    """Pull the shared option tokens (velocity, probability, mute, repeat, start) off a line."""
    out = {"velocity": 100, "deviation": 0, "probability": None, "release": None, "mute": False, "repeat": 1,
           "every": None, "start": 1}
    rest = []
    for token in tokens:
        m = _VELOCITY.match(token)
        if m:
            low, high = int(m.group(1)), int(m.group(2) or m.group(1))
            if not 1 <= low <= 127 or abs(high - low) > 127:
                raise NotationError("line %d: velocity %s must be 1-127, deviating at most 127"
                                    % (line_no, token))
            out["velocity"], out["deviation"] = low, high - low
            continue
        m = _PROBABILITY.match(token)
        if m:
            out["probability"] = float(m.group(1))
            continue
        m = _RELEASE.match(token)
        if m:
            out["release"] = int(m.group(1))
            if not 0 <= out["release"] <= 127:
                raise NotationError("line %d: release velocity %s must be 0-127" % (line_no, token))
            continue
        m = _REPEAT.match(token)
        if m:
            out["repeat"] = int(m.group(1))
            out["every"] = float(m.group(2)) if m.group(2) else None
            if out["repeat"] < 1 or (out["every"] is not None and out["every"] <= 0):
                raise NotationError("line %d: %s must repeat at least once, a positive number of bars apart"
                                    % (line_no, token))
            continue
        if token == "m":
            out["mute"] = True
            continue
        if "start" in allow:
            m = _START.match(token)
            if m:
                out["start"] = int(m.group(1))
                if out["start"] < 1:
                    raise NotationError("line %d: bars count from 1" % line_no)
                continue
        rest.append(token)
    return out, rest


def _note(pitch, start, duration, velocity, opts):
    note = {"pitch": pitch, "start_time": round(start, 6), "duration": round(duration, 6),
            "velocity": velocity, "mute": opts["mute"]}
    if opts["deviation"]:
        note["velocity_deviation"] = opts["deviation"]
    if opts["probability"] is not None:
        note["probability"] = opts["probability"]
    if opts["release"] is not None:
        note["release_velocity"] = opts["release"]
    return note


def _is_positions(token):
    return all(_POSITION.match(t) for t in token.split(","))


def _event_line(tokens, meter, line_no, scale=None):
    opts, rest = _options(tokens, line_no, ())
    # The position usually comes first, but it cannot be mistaken for anything else, so "36 1.3 1/16"
    # (pitch first, as on a step line) means the same as "1.3 36 1/16".
    where = [i for i, t in enumerate(rest) if _is_positions(t)]
    if len(where) != 1:
        raise NotationError("line %d: give one position (1.1, or several as 1.1,1.3)" % line_no)
    positions = [meter.position(t) for t in rest.pop(where[0]).split(",")]
    pitches, length = [], None
    for token in rest:
        pitch = _pitch(token, scale)
        if pitch is not None:
            pitches.append(pitch)
            continue
        value = length_of(token)
        if value is not None and length is None:
            length = value
            continue
        raise NotationError("line %d: did not understand %r" % (line_no, token))
    if not pitches:
        raise NotationError("line %d: no pitch (C3, F#1, 36 ...)" % line_no)
    length = 1.0 if length is None else length
    every = (opts["every"] or 1) * meter.bar
    return [_note(p, pos + r * every, length, opts["velocity"], opts)
            for r in range(opts["repeat"]) for pos in positions for p in pitches]


def _step_line(tokens, meter, line_no, scale=None):
    opts, rest = _options(tokens, line_no, ("start",))
    pitches, steps, step = [], "", None
    for token in rest:
        if _PATTERN.match(token):
            steps += token.replace("|", "")
            continue
        pitch = _pitch(token, scale) if not steps else None
        if pitch is not None:
            pitches.append(pitch)
            continue
        value = length_of(token)
        if value is not None and step is None:
            step = value
            continue
        raise NotationError("line %d: did not understand %r" % (line_no, token))
    if not pitches:
        raise NotationError("line %d: a step pattern needs a pitch first (C1 x...x...)" % line_no)
    step = 0.25 if step is None else step
    span = len(steps) * step
    every = opts["every"] * meter.bar if opts["every"] else span
    origin = (opts["start"] - 1) * meter.bar
    accent = {"x": opts["velocity"], "X": 127, "o": max(1, opts["velocity"] // 2)}
    notes = []
    for r in range(opts["repeat"]):
        for i, ch in enumerate(steps):
            if ch in accent:
                for p in pitches:
                    notes.append(_note(p, origin + r * every + i * step, step, accent[ch], opts))
    return notes


def parse(text, numerator=4, denominator=4, scale=None):
    """Text -> note dicts, sorted by time then pitch. All lines are checked; any error raises
    NotationError naming every bad line, and nothing is returned. scale (a Scale) is what ^degrees
    are read in."""
    meter = Meter(numerator, denominator)
    notes, errors = [], []
    for line_no, raw in enumerate(str(text).splitlines(), 1):
        line = _COMMENT.split(raw, 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        try:
            if any(_PATTERN.match(t) for t in tokens):
                notes += _step_line(tokens, meter, line_no, scale)
            elif any(_is_positions(t) for t in tokens):
                notes += _event_line(tokens, meter, line_no, scale)
            else:
                raise NotationError("line %d: start with a position (1.1) or give a step pattern (C1 x...)"
                                    % line_no)
        except NotationError as e:
            message = str(e)
            errors.append(message if message.startswith("line ") else "line %d: %s" % (line_no, message))
    if errors:
        raise NotationError("; ".join(errors))
    if not notes:
        raise NotationError("no notes in the notation")
    notes.sort(key=lambda n: (n["start_time"], n["pitch"]))
    return notes


def format_notes(notes, numerator=4, denominator=4):
    """Note dicts -> event lines. Notes sharing a start, length and velocity become one chord; chords
    that recur unchanged share one line with a list of positions. Lines are ordered by first position."""
    meter = Meter(numerator, denominator)
    chords = {}
    for n in notes:
        key = (round(float(n["start_time"]), 6), round(float(n["duration"]), 6), int(round(float(n["velocity"]))),
               int(n.get("velocity_deviation") or 0),
               None if n.get("probability") is None or float(n["probability"]) >= 1 - EPS else float(n["probability"]),
               None if n.get("release_velocity") in (None, 64) else int(n["release_velocity"]), bool(n.get("mute")))
        chords.setdefault(key, []).append(int(n["pitch"]))
    events = {}
    for (start, duration, velocity, deviation, probability, release, mute), pitches in chords.items():
        events.setdefault((tuple(sorted(pitches)), duration, velocity, deviation, probability, release, mute),
                          []).append(start)
    lines = []
    for (pitches, duration, velocity, deviation, probability, release, mute), starts in sorted(
            events.items(), key=lambda item: (min(item[1]), item[0][0])):
        parts = [",".join(meter.format_position(t) for t in sorted(starts))] + [name_of(p) for p in pitches]
        parts.append(format_length(duration))
        # a range reaching below 0 plays as one ending at 0: Live clamps what it plays to 1-127
        parts.append("v%d" % velocity if not deviation else "v%d-%d" % (velocity, max(0, velocity + deviation)))
        if probability is not None and probability < 1 - EPS:
            parts.append("p%g" % probability)
        if release is not None:
            parts.append("r%d" % release)
        if mute:
            parts.append("m")
        lines.append(" ".join(parts))
    return "\n".join(lines)
