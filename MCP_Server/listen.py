"""Measure an audio file with ffmpeg: loudness, peak, RMS, silence, and per-bar level and band balance.

Runs where the MCP server runs (on the Push 3: ffmpeg 5.0.3, Python 3.10 without numpy). Every number
comes from ffmpeg's ebur128, astats and silencedetect filters, in one ffmpeg call:

- the whole file goes through ebur128 (integrated loudness, loudness range, true peak), astats (peak,
  RMS) and silencedetect;
- copies of it, full band and split into low (<250 Hz), mid (250 Hz-4 kHz) and high (>4 kHz) with
  two-pole filters applied twice (24 dB/octave), are cut into chunks one bar long (from the tempo and
  time signature; rounding to whole samples drifts less than half a sample a bar) and measured by astats
  per chunk. That assumes the file starts on a bar, as a Session take does. A first `ffmpeg -i` reads
  the sample rate the chunk length needs.

Measured on the Push (2026-10-29): a stereo 6 s file takes well under a second; a spectrogram
(showspectrumpic) takes about as long as the audio, so it is only drawn when asked for.
"""

import math
import os
import re
import shutil
import subprocess
import tempfile

BANDS = (
    ("low", "lowpass=f=250,lowpass=f=250"),
    ("mid", "highpass=f=250,highpass=f=250,lowpass=f=4000,lowpass=f=4000"),
    ("high", "highpass=f=4000,highpass=f=4000"),
)
# quieter than this reads as silence in the table
FLOOR_DB = -90.0
MAX_ROWS = 32


class ListenError(Exception):
    pass


def find_ffmpeg():
    return os.environ.get("ABLETON_MCP_FFMPEG") or shutil.which("ffmpeg")


def bar_seconds(tempo, numerator, denominator):
    """Length of one bar in seconds: numerator notes of 1/denominator, at tempo quarter notes a minute."""
    return numerator * (4.0 / denominator) * 60.0 / tempo


def filtergraph(chunk_samples, silence_db=-50.0, silence_seconds=0.5):
    chunk = ("asetnsamples=n=%d:p=0,astats=metadata=1:reset=1:measure_perchannel=none:measure_overall=%s,"
             "ametadata=mode=print:file=%s.txt,anullsink")
    parts = ["[0:a]asplit=%d[whole][full]%s" % (2 + len(BANDS), "".join("[%s]" % n for n, _ in BANDS)),
             "[whole]ebur128@whole=peak=true:framelog=verbose,astats@whole=measure_perchannel=none,"
             "silencedetect@whole=n=%gdB:d=%g[out]" % (silence_db, silence_seconds),
             "[full]" + chunk % (chunk_samples, "Peak_level+RMS_level", "full")]
    for name, band in BANDS:
        parts.append("[%s]%s,%s" % (name, band, chunk % (chunk_samples, "RMS_level", name)))
    return ";".join(parts)


def _number(text):
    value = float(text)
    return float("-inf") if math.isnan(value) else value


def parse_log(log):
    """The whole-file numbers from ffmpeg's log (stderr). ffmpeg sets the graph up twice and ebur128
    prints an empty summary the first time, so the last summary is the one that counts."""
    info = {}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", log)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #0:0\S*: Audio: ([^,(\s]+)[^,]*, (\d+) Hz, ([^,\n]+)", log)
    if m:
        info["codec"], info["sample_rate"], info["channels"] = m.group(1), int(m.group(2)), m.group(3).strip()
    summary = log.rfind("Summary:")
    if summary >= 0:
        tail = log[summary:]
        for key, pattern in (("integrated_lufs", r"I:\s+(\S+) LUFS"), ("loudness_range_lu", r"LRA:\s+(\S+) LU"),
                             ("true_peak_db", r"Peak:\s+(\S+) dBFS")):
            m = re.search(pattern, tail)
            if m:
                info[key] = _number(m.group(1))
    for key, label in (("peak_db", "Peak level dB"), ("rms_db", "RMS level dB")):
        found = re.findall(r"\[astats@whole @ [^\]]+\] %s: (\S+)" % label, log)
        if found:
            info[key] = _number(found[-1])
    silences, start = [], None
    for kind, value in re.findall(r"silence_(start|end): (-?[\d.]+)", log):
        if kind == "start":
            start = max(0.0, float(value))
        elif start is not None:
            silences.append((start, float(value)))
            start = None
    if start is not None:
        silences.append((start, info.get("duration", start)))
    info["silences"] = silences
    return info


def parse_frames(text):
    """ametadata's print output: one dict per chunk, {"t": start in seconds, "Peak_level": dB, ...}."""
    frames = []
    for line in text.splitlines():
        if line.startswith("frame:"):
            m = re.search(r"pts_time:(\S+)", line)
            frames.append({"t": float(m.group(1)) if m else 0.0})
        elif "=" in line and frames:
            key, _, value = line.partition("=")
            try:
                frames[-1][key.rsplit(".", 1)[-1]] = _number(value)
            except ValueError:
                pass
    return frames


def _power_db(powers):
    if not powers:
        return None
    mean = sum(powers) / len(powers)
    return 10.0 * math.log10(mean) if mean > 0 else float("-inf")


def bar_rows(frames, seconds_per_bar, duration, bars_per_row=None):
    """Fold the one-bar chunks into rows of bars_per_row bars (default: enough bars a row for at most 32
    rows). frames maps "full", "low", "mid", "high" to parse_frames output."""
    bars = max(1, int(math.ceil(duration / seconds_per_bar - 0.01)))
    if bars_per_row is None:
        bars_per_row = max(1, int(math.ceil(bars / float(MAX_ROWS))))
    count = int(math.ceil(bars / float(bars_per_row)))
    rows = []
    for r in range(count):
        first = r * bars_per_row + 1
        rows.append({"bars": (first, min(bars, first + bars_per_row - 1)), "_p": {}, "peak_db": None})
    for stream, chunks in frames.items():
        for chunk in chunks:
            r = min(count - 1, int((chunk["t"] + seconds_per_bar / 2.0) / seconds_per_bar) // bars_per_row)
            rms = chunk.get("RMS_level")
            if rms is not None:
                rows[r]["_p"].setdefault(stream, []).append(10.0 ** (rms / 10.0) if rms > -math.inf else 0.0)
            peak = chunk.get("Peak_level")
            if stream == "full" and peak is not None:
                rows[r]["peak_db"] = peak if rows[r]["peak_db"] is None else max(rows[r]["peak_db"], peak)
    for row in rows:
        powers = row.pop("_p")
        row["rms_db"] = _power_db(powers.get("full"))
        for name, _ in BANDS:
            # in a silent bar the filters only ring out from the bar before
            silent = row["rms_db"] is not None and row["rms_db"] <= FLOOR_DB
            row[name + "_db"] = float("-inf") if silent else _power_db(powers.get(name))
    return rows


def _run(args, cwd, timeout, allow_fail=False):
    try:
        proc = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ListenError("ffmpeg took longer than %d s" % timeout)
    if proc.returncode != 0 and not allow_fail:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        raise ListenError("ffmpeg failed (exit %d): %s" % (proc.returncode, tail))
    return proc.stderr


def analyze_file(path, seconds_per_bar=None, bars_per_row=None, silence_db=-50.0, silence_seconds=0.5,
                 ffmpeg=None, timeout=120):
    """Measure one audio file. With seconds_per_bar, also per-bar rows (the file must start on a bar)."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise ListenError("ffmpeg was not found on this machine (set ABLETON_MCP_FFMPEG to its path)")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise ListenError("No audio file at %s" % path)
    with tempfile.TemporaryDirectory(prefix="ableton-mcp-listen-") as tmp:
        # with no output ffmpeg exits 1 after printing the input's streams
        probe = parse_log(_run([ffmpeg, "-nostdin", "-hide_banner", "-i", path], tmp, timeout, allow_fail=True))
        if "sample_rate" not in probe:
            raise ListenError("ffmpeg found no audio stream in %s" % path)
        # without bars, one-second chunks (unused) keep the graph the same
        chunk = int(round((seconds_per_bar or 1.0) * probe["sample_rate"]))
        # the chunk files are written relative to cwd, so the graph holds no paths to escape
        log = _run([ffmpeg, "-nostdin", "-nostats", "-hide_banner", "-i", path,
                    "-filter_complex", filtergraph(chunk, silence_db, silence_seconds),
                    "-map", "[out]", "-f", "null", "-"], tmp, timeout)
        frames = {}
        for name in ["full"] + [n for n, _ in BANDS]:
            with open(os.path.join(tmp, name + ".txt"), encoding="utf-8", errors="replace") as f:
                frames[name] = parse_frames(f.read())
    result = parse_log(log)
    result.update(path=path, silence_db=silence_db, silence_seconds=silence_seconds)
    if seconds_per_bar:
        result["seconds_per_bar"] = seconds_per_bar
        result["rows"] = bar_rows(frames, seconds_per_bar, result.get("duration", 0.0), bars_per_row)
    return result


def spectrogram_png(path, width=800, height=300, ffmpeg=None, timeout=120):
    """A mono spectrogram (log frequency axis, legend) as PNG bytes."""
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise ListenError("ffmpeg was not found on this machine (set ABLETON_MCP_FFMPEG to its path)")
    with tempfile.TemporaryDirectory(prefix="ableton-mcp-spectrum-") as tmp:
        _run([ffmpeg, "-nostdin", "-nostats", "-hide_banner", "-loglevel", "error", "-i", os.path.abspath(path),
              "-lavfi", "aformat=channel_layouts=mono,showspectrumpic=s=%dx%d:legend=1:fscale=log" % (width, height),
              "-y", "spectrum.png"], tmp, timeout)
        with open(os.path.join(tmp, "spectrum.png"), "rb") as f:
            return f.read()


def _db(value):
    if value is None:
        return "?"
    if value <= FLOOR_DB:
        return "-inf"
    return "%.1f" % value


def _bar_of(seconds, seconds_per_bar):
    return int(seconds // seconds_per_bar) + 1


def format_report(result):
    """A compact text report: whole-file numbers, silent stretches and the per-bar table."""
    lines = []
    duration = result.get("duration")
    fmt = ", ".join(str(x) for x in (result.get("sample_rate") and "%d Hz" % result["sample_rate"],
                                     result.get("channels"), result.get("codec")) if x)
    lines.append("%s%s" % ("%.2f s" % duration if duration is not None else "?", ", " + fmt if fmt else ""))
    lufs = result.get("integrated_lufs")
    silent = lufs is not None and lufs <= -70.0
    lines.append("Loudness %s LUFS integrated%s, range %s LU, true peak %s dBTP; peak %s dBFS, RMS %s dBFS"
                 % (_db(lufs), " (silent)" if silent else "", _db(result.get("loudness_range_lu")),
                    _db(result.get("true_peak_db")), _db(result.get("peak_db")), _db(result.get("rms_db"))))
    spb = result.get("seconds_per_bar")
    silences = result.get("silences") or []
    if silences:
        parts = []
        for start, end in silences:
            where = ""
            if spb:
                b0, b1 = _bar_of(start, spb), _bar_of(max(start, end - 1e-6), spb)
                where = " (bar %d)" % b0 if b0 == b1 else " (bars %d-%d)" % (b0, b1)
            parts.append("%.2f-%.2f s%s" % (start, end, where))
        lines.append("Silent (below %g dB for %g s or more): %s"
                     % (result.get("silence_db", -50), result.get("silence_seconds", 0.5), "; ".join(parts)))
    else:
        lines.append("No silent stretch (below %g dB for %g s or more)"
                     % (result.get("silence_db", -50), result.get("silence_seconds", 0.5)))
    rows = result.get("rows")
    if rows:
        lines.append("")
        lines.append("Per bar (%.3f s a bar), dBFS. rms/peak: full band; low <250 Hz, mid 250 Hz-4 kHz, "
                     "high >4 kHz: RMS of each band" % spb)
        lines.append("%-7s %6s %6s %6s %6s %6s" % ("bars", "rms", "peak", "low", "mid", "high"))
        for row in rows:
            first, last = row["bars"]
            label = str(first) if first == last else "%d-%d" % (first, last)
            lines.append("%-7s %6s %6s %6s %6s %6s" % (label, _db(row["rms_db"]), _db(row["peak_db"]),
                                                       _db(row["low_db"]), _db(row["mid_db"]), _db(row["high_db"])))
    return "\n".join(lines)
