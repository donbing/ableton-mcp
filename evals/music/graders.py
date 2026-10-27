"""Graders: each takes (params, answer) and returns {"passed", "checks", "detail"}.

A grader never asks a model's opinion. `checks` names every rule so the report can
say which rule failed, not only that something did. An answer that can't be read
at all fails the "readable" check, so format trouble isn't mistaken for bad music.
"""
import json
import re

from . import theory

EPS = 1e-6


def extract_answer(text):
    """The last ```json block in the reply, else the last {...} that parses."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)
    for candidate in reversed(blocks):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    for m in reversed(list(re.finditer(r"\{", text or ""))):
        try:
            return json.loads(text[m.start():text.rindex("}") + 1])
        except ValueError:
            continue
    return None


def _result(checks, detail=""):
    return {"passed": all(checks.values()), "checks": checks, "detail": detail}


def _unreadable(why):
    return {"passed": False, "checks": {"readable": False}, "detail": why}


def _note_list(answer, key="notes"):
    notes = answer.get(key) if isinstance(answer, dict) else None
    if not isinstance(notes, list) or not notes:
        return None
    out = []
    for n in notes:
        try:
            out.append({"pitch": int(n["pitch"]), "start_time": float(n["start_time"]),
                        "duration": float(n["duration"]), "velocity": float(n.get("velocity", 100))})
        except (KeyError, TypeError, ValueError):
            return None
    return out


def _valid(notes):
    return all(0 <= n["pitch"] <= 127 and n["start_time"] >= -EPS and n["duration"] > 0
               and 1 <= n["velocity"] <= 127 for n in notes)


# --- names: chords, scales, intervals -------------------------------------------------

def _names(answer, key):
    names = answer.get(key) if isinstance(answer, dict) else None
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or not names:
        return None
    try:
        return [theory.canonical(n) for n in names]
    except ValueError:
        return None


def note_names(params, answer):
    """Expected notes as names. Pitch classes must match; spelling is reported separately."""
    got = _names(answer, params.get("key", "notes"))
    if got is None:
        return _unreadable("no list of note names under %r" % params.get("key", "notes"))
    want = params["expected"]
    checks = {
        "readable": True,
        "pitch_classes": theory.pcs(got) == theory.pcs(want),
        "no_extra_notes": len(set(got)) == len(set(want)) or not params.get("exact_count", True),
    }
    spelled = sorted(set(got)) == sorted(set(want))
    res = _result(checks, "want %s, got %s" % (want, got))
    res["spelled"] = spelled
    return res


def chord_list(params, answer):
    """A list of chords, each a list of note names."""
    chords = answer.get("chords") if isinstance(answer, dict) else None
    if not isinstance(chords, list) or len(chords) != len(params["expected"]):
        return _unreadable("need %d chords" % len(params["expected"]))
    try:
        got = [[theory.canonical(n) for n in c] for c in chords]
    except (ValueError, TypeError):
        return _unreadable("unreadable note name")
    per = [theory.pcs(g) == theory.pcs(w) for g, w in zip(got, params["expected"])]
    checks = {"readable": True}
    for i, ok in enumerate(per):
        checks["chord_%d_%s" % (i + 1, params["numerals"][i])] = ok
    res = _result(checks, "want %s, got %s" % (params["expected"], got))
    res["spelled"] = all(sorted(set(g)) == sorted(set(w)) for g, w in zip(got, params["expected"]))
    return res


def number(params, answer):
    try:
        value = float(answer["value"])
    except (KeyError, TypeError, ValueError):
        return _unreadable("no numeric 'value'")
    ok = abs(value - params["expected"]) <= params.get("tolerance", 1e-3)
    return _result({"readable": True, "correct": ok}, "want %s, got %s" % (params["expected"], value))


def chord_name(params, answer):
    """Name the chord from MIDI pitches. Root must match unless the chord is symmetric."""
    symbol = answer.get("symbol") if isinstance(answer, dict) else None
    if not isinstance(symbol, str):
        return _unreadable("no 'symbol'")
    try:
        got = theory.chord_notes(symbol)
    except ValueError as e:
        return _unreadable(str(e))
    want = theory.chord_notes(params["expected"])
    root, want_root = theory.pc(theory.chord_root(symbol)), theory.pc(theory.chord_root(params["expected"]))
    checks = {"readable": True, "pitch_classes": theory.pcs(got) == theory.pcs(want)}
    if not params.get("symmetric"):
        checks["root"] = root == want_root
    return _result(checks, "want %s, got %s" % (params["expected"], symbol))


# --- notes for a clip -----------------------------------------------------------------

def progression(params, answer):
    """Chords written as clip notes, one chord per span of `beats_per_chord`."""
    notes = _note_list(answer)
    if notes is None:
        return _unreadable("no valid 'notes' list")
    span = params["beats_per_chord"]
    lo, hi = params["range"]
    checks = {"readable": True, "valid_notes": _valid(notes),
              "in_range": all(lo <= n["pitch"] <= hi for n in notes)}
    chords_ok, bass_ok, inside_ok, rhythm_ok = [], [], [], []
    for i, symbol in enumerate(params["chords"]):
        start, end = i * span, (i + 1) * span
        here = [n for n in notes if start - EPS <= n["start_time"] < end - EPS]
        want = set(theory.pcs(theory.chord_notes(symbol)))
        got = {n["pitch"] % 12 for n in here}
        if params["rhythm"] == "block":
            chords_ok.append(got == want)
            rhythm_ok.append(bool(here) and all(abs(n["start_time"] - start) < EPS for n in here))
        else:  # eighths: one chord tone on every eighth, all chord tones used
            steps = sorted(n["start_time"] for n in here)
            chords_ok.append(got <= want and got >= want)
            rhythm_ok.append(steps == [start + k * 0.5 for k in range(int(span * 2))])
        root = theory.pc(theory.chord_root(symbol))
        bass_ok.append(bool(here) and min(n["pitch"] for n in here) % 12 == root)
        inside_ok.append(all(n["start_time"] + n["duration"] <= end + EPS for n in here))
    checks["chord_tones"] = all(chords_ok)
    checks["rhythm"] = all(rhythm_ok)
    if params.get("bass_root", True):
        checks["bass_is_root"] = all(bass_ok)
    checks["no_overhang"] = all(inside_ok)
    checks["nothing_after_end"] = all(n["start_time"] < len(params["chords"]) * span - EPS for n in notes)
    return _result(checks, "per chord tones %s rhythm %s bass %s" % (chords_ok, rhythm_ok, bass_ok))


SATB = {"soprano": (60, 81), "alto": (55, 74), "tenor": (48, 69), "bass": (40, 62)}
VOICES = ["soprano", "alto", "tenor", "bass"]


def satb(params, answer):
    """Four-part harmony: chord tones, root in bass, ranges, spacing, no parallels."""
    try:
        parts = {v: [int(p) for p in answer[v]] for v in VOICES}
    except (KeyError, TypeError, ValueError):
        return _unreadable("need soprano/alto/tenor/bass lists of MIDI numbers")
    n = len(params["chords"])
    if any(len(parts[v]) != n for v in VOICES):
        return _unreadable("each voice needs %d notes" % n)
    checks = {"readable": True}
    tones, bass, problems = [], [], []
    for i, symbol in enumerate(params["chords"]):
        chord = theory.chord_notes(symbol)
        want = set(theory.pcs(chord))
        got = {parts[v][i] % 12 for v in VOICES}
        required = {theory.pc(chord[0]), theory.pc(chord[1])}  # root and third
        if len(chord) >= 4:
            required.add(theory.pc(chord[3]))  # the seventh
        tones.append(got <= want and required <= got)
        bass.append(parts["bass"][i] % 12 == theory.pc(chord[0]))
    checks["chord_tones"] = all(tones)
    checks["bass_is_root"] = all(bass)
    checks["ranges"] = all(SATB[v][0] <= p <= SATB[v][1] for v in VOICES for p in parts[v])
    checks["no_crossing"] = all(parts["soprano"][i] >= parts["alto"][i] >= parts["tenor"][i] >= parts["bass"][i]
                                for i in range(n))
    checks["spacing"] = all(parts["soprano"][i] - parts["alto"][i] <= 12 and parts["alto"][i] - parts["tenor"][i] <= 12
                            for i in range(n))
    parallel = []
    for a in range(4):
        for b in range(a + 1, 4):
            hi, lo = parts[VOICES[a]], parts[VOICES[b]]
            for i in range(n - 1):
                before, after = (hi[i] - lo[i]) % 12, (hi[i + 1] - lo[i + 1]) % 12
                moved = hi[i] != hi[i + 1] and lo[i] != lo[i + 1]
                if moved and before == after and before in (0, 7):
                    parallel.append("%s/%s %s->%s" % (VOICES[a], VOICES[b], i + 1, i + 2))
    checks["no_parallel_5ths_8ves"] = not parallel
    problems += parallel
    return _result(checks, "; ".join(problems) or "tones %s bass %s" % (tones, bass))


def melody(params, answer):
    """A monophonic line: in the scale, chord tones on beats 1 and 3, range, ends on the tonic."""
    notes = _note_list(answer)
    if notes is None:
        return _unreadable("no valid 'notes' list")
    notes.sort(key=lambda n: n["start_time"])
    bars = len(params["chords"])
    total = bars * 4
    scale = set(theory.pcs(theory.scale_notes(params["tonic"], params["scale"])))
    checks = {"readable": True, "valid_notes": _valid(notes)}
    checks["in_scale"] = all(n["pitch"] % 12 in scale for n in notes)
    checks["no_overlaps_or_gaps"] = (abs(notes[0]["start_time"]) < EPS and all(
        abs(a["start_time"] + a["duration"] - b["start_time"]) < EPS for a, b in zip(notes, notes[1:]))
        and abs(notes[-1]["start_time"] + notes[-1]["duration"] - total) < EPS)
    checks["on_grid"] = all(abs(n["start_time"] * 2 - round(n["start_time"] * 2)) < EPS
                            and abs(n["duration"] * 2 - round(n["duration"] * 2)) < EPS for n in notes)
    strong = []
    for bar, symbol in enumerate(params["chords"]):
        tones = set(theory.pcs(theory.chord_notes(symbol)))
        for beat in (0, 2):
            t = bar * 4 + beat
            sounding = [n for n in notes if n["start_time"] - EPS <= t < n["start_time"] + n["duration"] - EPS]
            strong.append(bool(sounding) and sounding[0]["pitch"] % 12 in tones)
    checks["chord_tones_on_1_and_3"] = all(strong)
    pitches = [n["pitch"] for n in notes]
    checks["range"] = max(pitches) - min(pitches) <= params["max_range"]
    checks["ends_on_tonic"] = pitches[-1] % 12 == theory.pc(params["tonic"])
    return _result(checks, "strong beats %s" % strong)


DRUMS = {"kick": {35, 36}, "snare": {38, 40}, "clap": {39}, "rim": {37},
         "closed_hat": {42, 44}, "open_hat": {46}}


def _hits(notes, kinds, bar):
    pitches = set().union(*(DRUMS[k] for k in kinds))
    return sorted(round((n["start_time"] - bar * 4) * 4) / 4 for n in notes
                  if n["pitch"] in pitches and bar * 4 - EPS <= n["start_time"] < bar * 4 + 4 - EPS)


def drums(params, answer):
    """Genre-defining placements. Positions are beats from the bar start (0 = beat 1).

    Every rule must hold in bar 1, the main pattern; rules marked every_bar (the backbeat)
    in every bar. Later bars may otherwise vary, as a drummer's turnaround or fill does.
    """
    notes = _note_list(answer)
    if notes is None:
        return _unreadable("no valid 'notes' list")
    checks = {"readable": True, "valid_notes": _valid(notes)}
    for rule in params["rules"]:
        kinds, ok = rule["kinds"], True
        for bar in range(params["bars"] if rule.get("every_bar") else 1):
            hits = set(_hits(notes, kinds, bar))
            if "at" in rule and not set(rule["at"]) <= hits:
                ok = False
            if "not_at" in rule and set(rule["not_at"]) & hits:
                ok = False
            if "min_count" in rule and len(_hits(notes, kinds, bar)) < rule["min_count"]:
                ok = False
        checks[rule["name"]] = ok
    return _result(checks, "; ".join("bar1 %s %s" % (r["name"], _hits(notes, r["kinds"], 0)) for r in params["rules"]))


GRADERS = {f.__name__: f for f in (note_names, chord_list, number, chord_name, progression, satb, melody, drums)}


def grade(item, reply_text):
    answer = extract_answer(reply_text)
    if answer is None:
        return _unreadable("no JSON answer found")
    try:
        return GRADERS[item["grader"]](item["params"], answer)
    except Exception as e:  # a grader crash is a format problem in the answer, report it as such
        return _unreadable("grader error: %r" % (e,))
