"""listen and analyze_audio_clip: measure what Live plays with ffmpeg, on the machine the server runs on.

- Parsers run on ffmpeg 5.0.3 output captured on the Push 3 (2026-10-29, tests/data/listen): a 6 s
  stereo WAV at 120 bpm 4/4, bar 1 a 100 Hz sine, bar 2 a 6 kHz sine, bar 3 silence.
- analyze_file runs with subprocess mocked (it replays those files), and once with the real ffmpeg on
  a WAV synthesised with `wave` when ffmpeg is installed (skipped otherwise).
- The listen flow runs the real Remote Script handlers on a fake Song (as in test_batch_1_10_21) with
  ffmpeg mocked. The fake slot follows what Live 12.4.6 did on the Push (2026-10-28): fired on an
  armed track it waits for the launch quantization, then records, and with a record length it ends by
  itself and the new clip plays.
"""
import math
import struct
import sys
import types
import wave
from pathlib import Path

import pytest

import MCP_Server.listen as L
import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION
from tests.test_batch_1_10_19 import FakeLive
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call

DATA = Path(__file__).resolve().parent / "data" / "listen"


def captured(name):
    return (DATA / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- parsers

def test_the_last_summary_and_the_whole_file_stats_are_read():
    info = L.parse_log(captured("ffmpeg_log.txt"))
    # ffmpeg prints an empty ebur128 summary first (-70 LUFS); the real one comes last
    assert info["integrated_lufs"] == -4.6 and info["loudness_range_lu"] == 2.7 and info["true_peak_db"] == -6.0
    assert info["peak_db"] == pytest.approx(-6.02, abs=0.01) and info["rms_db"] == pytest.approx(-10.79, abs=0.01)
    assert info["duration"] == 6.0 and info["sample_rate"] == 48000
    assert info["channels"] == "stereo" and info["codec"] == "pcm_s16le"
    assert info["silences"] == [(4.0, 6.0)]


def test_the_probe_alone_gives_the_sample_rate():
    info = L.parse_log(captured("probe.txt"))
    assert info["sample_rate"] == 48000 and "integrated_lufs" not in info and info["silences"] == []


def test_silence_running_to_the_end_ends_with_the_file():
    log = "  Duration: 00:00:08.00, bitrate: 1\n[silencedetect @ 0x1] silence_start: -0.01\n" \
          "[silencedetect @ 0x1] silence_end: 1.5 | silence_duration: 1.5\n[silencedetect @ 0x1] silence_start: 6.2\n"
    assert L.parse_log(log)["silences"] == [(0.0, 1.5), (6.2, 8.0)]


def test_chunk_files_parse_into_one_dict_per_bar():
    frames = L.parse_frames(captured("full.txt"))
    assert [f["t"] for f in frames] == [0.0, 2.0, 4.0]
    assert frames[0]["RMS_level"] == pytest.approx(-9.03, abs=0.01) and frames[2]["Peak_level"] == -math.inf


def captured_frames():
    return {name: L.parse_frames(captured(name + ".txt")) for name in ("full", "low", "mid", "high")}


def test_bars_show_where_the_energy_is():
    rows = L.bar_rows(captured_frames(), 2.0, 6.0)
    assert [r["bars"] for r in rows] == [(1, 1), (2, 2), (3, 3)]
    low_bar, high_bar, silent = rows
    assert low_bar["low_db"] > low_bar["mid_db"] + 25 and low_bar["high_db"] < -50
    assert high_bar["high_db"] > high_bar["mid_db"] + 10 and high_bar["low_db"] < -35
    # the filters ring on into the silent bar; the table shows it as silent
    assert silent["rms_db"] == -math.inf and silent["low_db"] == -math.inf and silent["peak_db"] == -math.inf


def test_bars_are_grouped_by_power_not_by_averaging_decibels():
    rows = L.bar_rows(captured_frames(), 2.0, 6.0, bars_per_row=2)
    assert [r["bars"] for r in rows] == [(1, 2), (3, 3)]
    assert rows[0]["rms_db"] == pytest.approx(-9.03, abs=0.01) and rows[0]["peak_db"] == pytest.approx(-6.02, abs=0.01)
    # one loud bar and one 30 dB quieter: about 3 dB under the loud one, not halfway
    assert rows[0]["low_db"] == pytest.approx(-9.26 - 3.0, abs=0.05)


def test_long_takes_fold_into_at_most_32_rows():
    frames = {"full": [{"t": i * 2.0, "RMS_level": -20.0, "Peak_level": -6.0} for i in range(64)]}
    rows = L.bar_rows(frames, 2.0, 128.0)
    assert len(rows) == 32 and rows[0]["bars"] == (1, 2) and rows[-1]["bars"] == (63, 64)


def test_bar_lengths():
    assert L.bar_seconds(120, 4, 4) == 2.0
    assert L.bar_seconds(120, 6, 8) == 1.5
    assert L.bar_seconds(90, 3, 4) == 2.0


def test_the_report_is_a_compact_table():
    result = dict(L.parse_log(captured("ffmpeg_log.txt")), silence_db=-50.0, silence_seconds=0.5,
                  seconds_per_bar=2.0, rows=L.bar_rows(captured_frames(), 2.0, 6.0))
    text = L.format_report(result)
    assert "6.00 s, 48000 Hz, stereo, pcm_s16le" in text
    assert "Loudness -4.6 LUFS integrated, range 2.7 LU, true peak -6.0 dBTP; peak -6.0 dBFS, RMS -10.8 dBFS" in text
    assert "4.00-6.00 s (bar 3)" in text
    lines = text.splitlines()
    header = lines.index("bars       rms   peak    low    mid   high")
    assert lines[header + 3].split() == ["3", "-inf", "-inf", "-inf", "-inf", "-inf"]
    assert "ffmpeg" not in text and "lavfi" not in text


def test_a_silent_file_says_so():
    text = L.format_report({"duration": 4.0, "integrated_lufs": -70.0, "silences": [(0.0, 4.0)],
                            "silence_db": -50.0, "silence_seconds": 0.5})
    assert "-70.0 LUFS integrated (silent)" in text


# --------------------------------------------------------------------------- analyze_file, ffmpeg mocked

def test_analyze_file_runs_ffmpeg_with_no_stdin_and_no_paths_in_the_graph(tmp_path, monkeypatch):
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"RIFF")
    calls = []

    def fake_run(args, cwd, stdin, capture_output, text, errors, timeout):
        calls.append((args, stdin))
        if "-filter_complex" not in args:
            return types.SimpleNamespace(returncode=1, stderr=captured("probe.txt"))
        for name in ("full", "low", "mid", "high"):
            Path(cwd, name + ".txt").write_text(captured(name + ".txt"), encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stderr=captured("ffmpeg_log.txt"))

    monkeypatch.setattr(L.subprocess, "run", fake_run)
    result = L.analyze_file(str(wav), 2.0, ffmpeg="ffmpeg")
    assert len(calls) == 2 and all(stdin is L.subprocess.DEVNULL and "-nostdin" in a for a, stdin in calls)
    graph = calls[1][0][calls[1][0].index("-filter_complex") + 1]
    # one chunk per bar: 2 s at 48 kHz
    assert "asetnsamples=n=96000:p=0" in graph and str(tmp_path) not in graph
    assert result["integrated_lufs"] == -4.6 and [r["bars"] for r in result["rows"]] == [(1, 1), (2, 2), (3, 3)]


def test_ffmpeg_runs_niced_on_one_thread_with_a_timeout_from_the_length(tmp_path, monkeypatch):
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"RIFF")
    calls = []

    def fake_run(args, cwd, stdin, capture_output, text, errors, timeout):
        calls.append((args, timeout))
        if "-filter_complex" not in args and "-lavfi" not in args:
            return types.SimpleNamespace(returncode=1, stderr=captured("probe.txt"))
        for name in ("full", "low", "mid", "high", "spectrum"):
            Path(cwd, name + (".png" if name == "spectrum" else ".txt")).write_text(
                captured(name + ".txt") if name != "spectrum" else "png", encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stderr=captured("ffmpeg_log.txt"))

    monkeypatch.setattr(L.subprocess, "run", fake_run)
    monkeypatch.setattr(L.shutil, "which", lambda name: "/usr/bin/nice" if name == "nice" else None)
    L.analyze_file(str(wav), 2.0, ffmpeg="ffmpeg")
    L.spectrogram_png(str(wav), ffmpeg="ffmpeg", duration=6.0)
    for args, _ in calls:
        assert args[:4] == ["/usr/bin/nice", "-n", "10", "ffmpeg"]
    for args, _ in calls[1:]:
        for option in ("-threads", "-filter_threads", "-filter_complex_threads"):
            assert args[args.index(option) + 1] == "1" and args.index(option) < args.index("-i")
    # the probe reads 6 s: 2 x 6 + 10
    assert [t for _, t in calls] == [30, 22.0, 22.0]

    # where nice is missing, ffmpeg runs as it is
    calls.clear()
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    L.analyze_file(str(wav), 2.0, ffmpeg="ffmpeg")
    assert all(args[0] == "ffmpeg" for args, _ in calls) and "-threads" in calls[1][0]


def test_the_timeout_grows_with_the_audio():
    assert L.timeout_for(6.0) == 22.0 and L.timeout_for(110.0) == 230.0 and L.timeout_for(None) == 10.0


def test_analyze_file_errors_are_plain(tmp_path, monkeypatch):
    with pytest.raises(L.ListenError, match="No audio file"):
        L.analyze_file(str(tmp_path / "missing.wav"), ffmpeg="ffmpeg")
    monkeypatch.setattr(L, "find_ffmpeg", lambda: None)
    with pytest.raises(L.ListenError, match="ffmpeg was not found"):
        L.analyze_file(str(tmp_path / "x.wav"))
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(L.subprocess, "run", lambda *a, **k: types.SimpleNamespace(
        returncode=1, stderr="x.wav: Invalid data found when processing input\n"))
    with pytest.raises(L.ListenError, match="no audio stream"):
        L.analyze_file(str(wav), ffmpeg="ffmpeg")


# --------------------------------------------------------------------------- the real ffmpeg

def synth_wav(path, rate=48000, bar=96000):
    """Bar 1 a 100 Hz sine, bar 2 a 6 kHz sine, bar 3 silence: 120 bpm 4/4, stereo, 16 bit."""
    frames = bytearray()
    for i in range(3 * bar):
        b = i // bar
        v = 0 if b == 2 else int(0.5 * 32767 * math.sin(2 * math.pi * (100.0 if b == 0 else 6000.0) * i / rate))
        frames += struct.pack("<hh", v, v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


@pytest.mark.skipif(not L.find_ffmpeg(), reason="ffmpeg is not installed")
def test_the_real_ffmpeg_splits_bands_per_bar_and_finds_the_silence(tmp_path):
    wav = tmp_path / "bands.wav"
    synth_wav(wav)
    result = L.analyze_file(str(wav), 2.0)
    low_bar, high_bar, silent = result["rows"]
    assert low_bar["low_db"] > -10 and low_bar["low_db"] > low_bar["mid_db"] + 25 and low_bar["high_db"] < -60
    assert high_bar["high_db"] > -11 and high_bar["high_db"] > high_bar["mid_db"] + 10 and high_bar["low_db"] < -35
    assert silent["rms_db"] == -math.inf
    assert len(result["silences"]) == 1 and result["silences"][0] == pytest.approx((4.0, 6.0), abs=0.05)
    assert result["peak_db"] == pytest.approx(-6.0, abs=0.1) and result["rms_db"] == pytest.approx(-10.8, abs=0.1)
    assert L.spectrogram_png(str(wav), 200, 100).startswith(b"\x89PNG")


# --------------------------------------------------------------------------- the listen flow

@pytest.fixture(autouse=True)
def live(monkeypatch):
    fake = FakeLive()
    monkeypatch.setitem(sys.modules, "Live", fake)
    return fake


class Param(object):
    def __init__(self, value):
        self.value, self.min, self.max = value, 0.0, 1.0

    def str_for_value(self, value):
        return "%.1f" % value


class Clip(object):
    def __init__(self, name, audio=True):
        self.name, self.is_audio_clip = name, audio
        self.is_recording, self.is_playing, self.length = False, False, 0.0
        self.file_path = None


class Slot(object):
    """Fired empty on an armed track: waits `wait` polls (the launch quantization), then records; with a
    record length it ends `takes` polls later and the new clip plays."""

    def __init__(self, song, clip=None, takes_length=True):
        self.song, self.clip, self.takes_length = song, clip, takes_length
        self.is_triggered, self.record_length, self.left = False, None, 0
        self.fired, self.stopped = [], 0

    @property
    def has_clip(self):
        return self.clip is not None

    @property
    def is_recording(self):
        return self.clip is not None and self.clip.is_recording

    def fire(self, **kwargs):
        if kwargs and not self.takes_length:
            raise TypeError("fire() got an unexpected keyword argument")
        self.fired.append(kwargs)
        self.song.is_playing = True
        if self.is_recording:
            self.finish()
        elif self.clip is None:
            self.is_triggered, self.record_length, self.left = True, kwargs.get("record_length"), self.song.wait

    def stop(self):
        self.stopped += 1
        if self.is_triggered:
            self.is_triggered = False
        elif self.is_recording:
            self.finish()
        elif self.clip is not None:
            self.clip.is_playing = False

    def delete_clip(self):
        self.clip = None

    def finish(self):
        self.clip.is_recording, self.clip.is_playing = False, True
        self.clip.length = self.song.taken_beats
        self.clip.file_path = "/data/Music/Ableton/Sets/Test Project/Samples/Recorded/0001 Listen.wav"

    def tick(self):
        if self.is_triggered and self.song.is_playing:
            self.left -= 1
            if self.left <= 0:
                self.is_triggered, self.clip = False, Clip("1-Listen")
                self.clip.is_recording, self.left = True, self.song.takes
        elif self.is_recording and self.record_length is not None:
            self.left -= 1
            if self.left <= 0:
                self.finish()


def routing(name):
    return types.SimpleNamespace(display_name=name)


class Track(object):
    def __init__(self, song, name, midi=False, armed=False, input_type="Resampling", monitoring=2, slots=3):
        self.song, self.name = song, name
        self.has_midi_input, self.has_audio_input = midi, not midi
        self.can_be_armed, self._arm = True, armed
        self.mute = self.solo = False
        self.devices, self.arrangement_clips, self.group_track, self.color_index = [], [], None, 0
        self.mixer_device = types.SimpleNamespace(volume=Param(0.85), panning=Param(0.0))
        self.clip_slots = [Slot(song) for _ in range(slots)]
        self.input_routing_type, self.input_routing_channel = routing(input_type), routing("Post FX")
        self.available_input_routing_types = [routing(n) for n in ("Ext. In", "Resampling", "No Input")]
        self.available_input_routing_channels = [routing("Post FX")]
        self.current_monitoring_state = monitoring

    @property
    def arm(self):
        return self._arm

    @arm.setter
    def arm(self, value):
        if value and self.song.exclusive_arm:
            for t in self.song.tracks:
                t._arm = False
        self._arm = value


class Song(object):
    def __init__(self):
        self.tracks = [Track(self, "Drums", midi=True, input_type="All Ins"),
                       Track(self, "Vox", input_type="Ext. In", monitoring=1),
                       Track(self, "Listen")]
        self.tracks[0].clip_slots[0].clip = Clip("Beat", audio=False)
        self.return_tracks, self.cue_points = [], []
        self.scenes = [Scene(self, "Scene %d" % (i + 1)) for i in range(3)]
        self.current_song_time, self.fired_scenes = 130.0, []
        self.master_track = types.SimpleNamespace(name="Main", devices=[],
                                                  mixer_device=types.SimpleNamespace(volume=Param(0.85),
                                                                                     panning=Param(0.0)))
        self.tempo, self.signature_numerator, self.signature_denominator = 120.0, 4, 4
        # 4 is "bar"; the rest only for set_transport_options' read
        self.clip_trigger_quantization, self.midi_recording_quantization = 4, 0
        self.punch_in = self.punch_out = self.arrangement_overdub = self.loop = False
        self.count_in_duration = 0
        self.is_playing, self.exclusive_arm = True, False
        # polls before the take starts and until it ends
        self.wait, self.takes, self.taken_beats = 2, 3, 8.0

    def tick(self):
        for t in self.tracks:
            for s in t.clip_slots:
                s.tick()

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False


class Scene(object):
    def __init__(self, song, name):
        self.song, self.name, self.tempo = song, name, -1.0

    def fire(self):
        self.song.fired_scenes.append(self.name)
        self.song.is_playing = True


POLLS = ("get_slot_state", "get_track_info")


class LiveConnection(object):
    """The server's connection, answered by the real Remote Script. Each get_slot_state (or, on an older
    script, get_track_info) is one poll."""

    def __init__(self, inst, song):
        self.inst, self.song, self.sent = inst, song, []

    def send_command(self, command, params=None):
        self.sent.append((command, params or {}))
        if command in POLLS:
            self.song.tick()
        reply = self.inst._process_command({"type": command, "params": params or {}})
        if reply["status"] == "error":
            raise Exception(reply["message"])
        return reply["result"]

    def commands(self):
        return [c for c, _ in self.sent]


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def conn(script_module, song, monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    inst = make_inst(script_module, song)
    monkeypatch.setattr(script_module.time, "sleep", lambda s: None)
    fake = LiveConnection(inst, song)
    clock = [1000.0]
    monkeypatch.setattr(server, "_listen_now", lambda: clock[0])
    monkeypatch.setattr(server, "_listen_sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(td, "get_telemetry", lambda: types.SimpleNamespace(record_event=lambda *a, **k: None),
                        raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    # the real check, against what this Remote Script reports in the handshake
    monkeypatch.setattr(sh, "_script_info", {"script_version": EXPECTED_REMOTE_SCRIPT_VERSION,
                                             "capabilities": list(script_module.SCRIPT_CAPABILITIES)})
    return fake


class Seen(list):
    drawn = None


@pytest.fixture
def measured(monkeypatch):
    seen, drawn = Seen(), []

    def analyze_file(path, seconds_per_bar=None, bars_per_row=None, silence_db=-50.0):
        seen.append((path, seconds_per_bar, bars_per_row, silence_db))
        return dict(L.parse_log(captured("ffmpeg_log.txt")), path=path, silence_db=silence_db, silence_seconds=0.5,
                    seconds_per_bar=seconds_per_bar, rows=L.bar_rows(captured_frames(), 2.0, 6.0))

    monkeypatch.setattr(L, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(L, "analyze_file", analyze_file)
    monkeypatch.setattr(L, "spectrogram_png",
                        lambda path, duration=None, start=None, max_hz=None: drawn.append((duration, start, max_hz))
                        or b"\x89PNG fake")
    seen.drawn = drawn
    return seen


LISTEN = dict(scratch_track_index=2, expected_name="Listen")
CHANGES = {"set_track_arm", "record_into_slot", "stop_clip", "delete_clip"}


def test_listen_records_measures_and_cleans_up(conn, song, measured):
    out = call(server.listen, None, bars=2, **LISTEN)
    slot = song.tracks[2].clip_slots[0]
    assert slot.fired == [{"record_length": 8.0}]
    # the take was stopped once it played, then deleted; the arm is back off
    assert slot.stopped == 1 and slot.clip is None and song.tracks[2].arm is False
    assert measured == [(
        "/data/Music/Ableton/Sets/Test Project/Samples/Recorded/0001 Listen.wav", 2.0, None, -50.0)]
    assert out.startswith("Listened on 'Listen' (track 2) at 120.0 bpm 4/4: armed it for the take; "
                          "recorded 2 bars into slot 0")
    assert "stopped the new clip" in out and "disarmed it again" in out and "deleted the take's clip" in out
    assert "Loudness -4.6 LUFS integrated" in out and "bars       rms   peak    low    mid   high" in out
    assert "Note:" not in out


def test_keep_leaves_the_stopped_take_and_an_armed_track_stays_armed(conn, song, measured):
    song.tracks[2]._arm = True
    out = call(server.listen, None, bars=1, clip_index=1, keep=True, **LISTEN)
    slot = song.tracks[2].clip_slots[1]
    assert slot.fired == [{"record_length": 4.0}] and slot.clip is not None and slot.clip.is_playing is False
    assert song.tracks[2].arm is True and "set_track_arm" not in conn.commands()
    assert "kept the take in slot 1" in out


def test_exclusive_arm_is_undone(conn, song, measured):
    song.exclusive_arm, song.tracks[1]._arm = True, True
    out = call(server.listen, None, **LISTEN)
    assert song.tracks[1].arm is True and song.tracks[2].arm is False
    assert "re-armed track(s) 1, which Exclusive Arm had disarmed" in out


@pytest.mark.parametrize("change, expected", [
    (lambda s: None, "not 'Lisen'"),
    (lambda s: setattr(s.tracks[2], "input_routing_type", routing("Ext. In")), "records from 'Ext. In'"),
    (lambda s: setattr(s.tracks[2], "input_routing_type", routing("No Input")), "records from 'No Input'"),
    (lambda s: setattr(s.tracks[2], "current_monitoring_state", 1), "monitoring on 'Listen' is 'auto'"),
    (lambda s: setattr(s, "is_playing", False), "Live is not playing"),
    (lambda s: [setattr(slot, "clip", Clip("x")) for slot in s.tracks[2].clip_slots], "no empty slot"),
])
def test_listen_refuses_and_changes_nothing(conn, song, measured, change, expected):
    change(song)
    name = "Lisen" if "Lisen" in expected else "Listen"
    out = call(server.listen, None, scratch_track_index=2, expected_name=name)
    assert out.startswith("Error") and expected in out
    assert not CHANGES & set(conn.commands()) and measured == []
    if "records from" in out or "monitoring" in out:
        assert "set_track_routing(track_index=2, expected_name='Listen', direction='input', " \
               "routing_type='Resampling') and set_track_monitoring(track_index=2, state='off')" in out


def test_listen_refuses_bad_arguments(conn, song, measured):
    assert "listen needs an audio track" in call(server.listen, None, scratch_track_index=0, expected_name="Drums")
    assert "out of range" in call(server.listen, None, scratch_track_index=7, expected_name="X")
    assert "bars must be" in call(server.listen, None, bars=0, **LISTEN)
    assert "bars must be" in call(server.listen, None, bars=33, **LISTEN)
    song.tracks[2].clip_slots[1].clip = Clip("Old")
    assert "holds a clip" in call(server.listen, None, clip_index=1, **LISTEN)
    assert "slot 9 out of range" in call(server.listen, None, clip_index=9, **LISTEN)
    assert not CHANGES & set(conn.commands())


def test_listen_needs_ffmpeg(conn, monkeypatch):
    monkeypatch.setattr(L, "find_ffmpeg", lambda: None)
    assert "ffmpeg was not found" in call(server.listen, None, **LISTEN) and conn.sent == []


def test_a_take_that_never_starts_is_cancelled_within_its_bound(conn, song, measured):
    song.wait = 10 ** 6
    out = call(server.listen, None, bars=2, **LISTEN)
    slot = song.tracks[2].clip_slots[0]
    assert out.startswith("Error: no take was recorded") and "had not finished after" in out
    assert slot.is_triggered is False and slot.clip is None and song.tracks[2].arm is False
    assert measured == [] and "delete_clip" not in conn.commands()
    # (1 bar of launch wait + 2 bars) at 2 s a bar + 3 s margin, polled every 0.5 s with the one-slot read
    assert 17 <= conn.commands().count("get_slot_state") <= 21
    # only the slot listing before the take reads the whole track
    assert conn.commands().count("get_track_info") == 1


def test_an_older_remote_script_is_polled_with_get_track_info(conn, song, measured, monkeypatch):
    import MCP_Server.script_handshake as sh

    caps = [c for c in sh._script_info["capabilities"] if c != "get_slot_state"]
    monkeypatch.setattr(sh, "_script_info", {"script_version": "1.10.24", "capabilities": caps})
    out = call(server.listen, None, **LISTEN)
    assert out.startswith("Listened") and "get_slot_state" not in conn.commands()
    assert conn.commands().count("get_track_info") > 1


def test_get_slot_state_reads_one_slot(conn, song):
    song.tracks[0].clip_slots[0].clip.is_playing = True
    state = conn.send_command("get_slot_state", {"track_index": 0, "clip_index": 0})
    assert state == {"track_index": 0, "clip_index": 0, "has_clip": True, "is_triggered": False,
                     "is_recording": False, "clip": {"is_recording": False, "is_playing": True, "length": 0.0}}
    assert conn.send_command("get_slot_state", {"track_index": 2, "clip_index": 1})["clip"] is None
    with pytest.raises(Exception, match="out of range"):
        conn.send_command("get_slot_state", {"track_index": 2, "clip_index": 3})
    with pytest.raises(Exception, match="out of range"):
        conn.send_command("get_slot_state", {"track_index": 9, "clip_index": 0})


@pytest.mark.parametrize("name, attr", [("quarter", "q_quarter"), ("sixteenth", "q_sixtenth"), ("none", "q_no_q")])
def test_a_launch_quantization_off_the_bar_is_refused(conn, song, measured, live, name, attr):
    song.clip_trigger_quantization = getattr(live.Song.Quantization, attr)
    out = call(server.listen, None, **LISTEN)
    assert out.startswith("Error: the launch quantization is '%s'" % name) and "shifted" in out
    assert "set_transport_options(clip_trigger_quantization='bar')" in out
    assert not CHANGES & set(conn.commands()) and measured == []


@pytest.mark.parametrize("attr", ["q_bar", "q_2_bars", "q_4_bars", "q_8_bars"])
def test_whole_bar_launch_quantizations_record(conn, song, measured, live, attr):
    song.clip_trigger_quantization = getattr(live.Song.Quantization, attr)
    assert call(server.listen, None, **LISTEN).startswith("Listened")


@pytest.mark.parametrize("tempo, attr, fit", [(120.0, "q_bar", 29), (120.0, "q_4_bars", 26), (70.0, "q_bar", 16)])
def test_a_pass_is_capped_at_a_minute_with_the_launch_wait(conn, song, measured, live, tempo, attr, fit):
    song.tempo, song.clip_trigger_quantization = tempo, getattr(live.Song.Quantization, attr)
    out = call(server.listen, None, bars=fit + 1, **LISTEN)
    assert out.startswith("Error: %d bars at %s bpm 4/4" % (fit + 1, tempo)) and "over the 60 s" in out
    assert "at most %d bars fit" % fit in out
    assert not CHANGES & set(conn.commands()) and measured == []
    assert call(server.listen, None, bars=fit, **LISTEN).startswith("Listened")


def test_not_one_bar_fits_says_so(conn, song, measured, live):
    # 30 bpm is 8 s a bar: 8 bars of launch wait alone are 64 s
    song.tempo, song.clip_trigger_quantization = 30.0, live.Song.Quantization.q_8_bars
    out = call(server.listen, None, bars=1, **LISTEN)
    assert "Not one bar fits" in out and not CHANGES & set(conn.commands())


def test_a_spectrogram_is_refused_for_takes_over_30_s(conn, song, measured):
    out = call(server.listen, None, bars=16, spectrogram=True, **LISTEN)
    assert out.startswith("Error: 16 bars at 120.0 bpm 4/4 is 32 s") and "at most 15 bars with spectrogram" in out
    assert not CHANGES & set(conn.commands()) and measured == []
    assert call(server.listen, None, bars=16, **LISTEN).startswith("Listened")
    assert isinstance(call(server.listen, None, bars=15, spectrogram=True, **LISTEN), list)


def test_a_long_file_gets_no_spectrogram(monkeypatch):
    drawn = []
    monkeypatch.setattr(L, "spectrogram_png",
                        lambda path, duration=None, start=None, max_hz=None: drawn.append(duration) or b"png")
    out = server._with_spectrogram("text", "/x.wav", True, 95.0)
    assert out == ("text\nNo spectrogram: the file is 95 s long, and it is only drawn up to 30 s; draw part of "
                   "it with spectrogram_bars.") and drawn == []
    assert server._with_spectrogram("text", "/x.wav", True, 30.2)[1].data == b"png" and drawn == [30.2]


def test_a_live_without_record_length_is_stopped_after_the_bars(conn, song, measured):
    for slot in song.tracks[2].clip_slots:
        slot.takes_length = False
    out = call(server.listen, None, bars=1, **LISTEN)
    assert out.startswith("Listened") and "Note:" not in out
    assert song.tracks[2].clip_slots[0].fired == [{}] and song.tracks[2].clip_slots[0].clip is None


def test_a_failed_measurement_still_deletes_the_take(conn, song, measured, monkeypatch):
    def broken(*a, **k):
        raise L.ListenError("ffmpeg failed (exit 1): boom")

    monkeypatch.setattr(L, "analyze_file", broken)
    out = call(server.listen, None, **LISTEN)
    assert out == "Error in listen: ffmpeg failed (exit 1): boom"
    assert song.tracks[2].clip_slots[0].clip is None and song.tracks[2].arm is False


def test_the_spectrogram_comes_back_as_an_image_only_when_asked(conn, song, measured):
    out = call(server.listen, None, spectrogram=True, **LISTEN)
    assert isinstance(out, list) and out[0].startswith("Listened") and out[1].data == b"\x89PNG fake"
    assert isinstance(call(server.listen, None, **LISTEN), str)


def test_analyze_audio_clip_reads_the_clips_file_at_the_set_tempo(conn, song, measured):
    clip = Clip("Hihat Clap House")
    clip.file_path = "/data/Music/Ableton/Core Library/Samples/Loops/Hihat Clap House 120 bpm.wav"
    song.tracks[2].clip_slots[1].clip = clip
    song.tempo = 90.0
    out = call(server.analyze_audio_clip, None, 2, 1, bars_per_row=2)
    assert measured == [(clip.file_path, 8.0 / 3, 2, -50.0)]
    assert out.startswith("Clip 'Hihat Clap House' (track 2, slot 1), file ") and "bars at 90.0 bpm 4/4" in out
    assert not CHANGES & set(conn.commands())
    assert "not an audio clip" in call(server.analyze_audio_clip, None, 0, 0)
    with_image = call(server.analyze_audio_clip, None, 2, 1, spectrogram=True)
    assert isinstance(with_image, list) and with_image[1].data == b"\x89PNG fake"


def test_listen_is_a_modifying_tool_and_analyze_is_read_only():
    assert "listen" in MODIFYING_TOOLS and "analyze_audio_clip" not in MODIFYING_TOOLS


# ---------------------------------------------------------------- one part at a time (source)

def offer_drums(song):
    """The scratch track can also listen to Drums, whose channels include a Post Mixer tap."""
    listen = song.tracks[2]
    listen.available_input_routing_types.append(routing("Drums"))
    listen.available_input_routing_channels = [routing("Post FX"), routing("Post Mixer")]


def routings_sent(conn):
    return [{k: p[k] for k in ("routing_type", "routing_channel") if k in p}
            for c, p in conn.sent if c == "set_track_routing"]


def test_source_listens_to_one_track_and_puts_the_input_back(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, source="Drums", **LISTEN)
    assert routings_sent(conn) == [{"routing_type": "Drums"}, {"routing_channel": "Post Mixer"},
                                   {"routing_type": "Resampling", "routing_channel": "Post FX"}]
    # the take was fired while the input pointed at Drums
    fired = [c for c, _ in conn.sent].index("record_into_slot")
    assert fired > [c for c, _ in conn.sent].index("set_track_routing")
    listen = song.tracks[2]
    assert listen.input_routing_type.display_name == "Resampling" and listen.arm is False
    assert out.startswith("Listened on 'Listen' (track 2) at 120.0 bpm 4/4: took its input from 'Drums' "
                          "(Post Mixer); armed it for the take; recorded 2 bars")
    assert "put its input back to 'Resampling'" in out and "Note:" not in out


def test_source_works_from_a_scratch_track_on_ext_in_and_puts_ext_in_back(conn, song, measured):
    offer_drums(song)
    song.tracks[2].input_routing_type = routing("Ext. In")
    out = call(server.listen, None, source="Drums", **LISTEN)
    assert out.startswith("Listened") and song.tracks[2].input_routing_type.display_name == "Ext. In"


@pytest.mark.parametrize("source", ["Ext. In", "No Input", "Bass", "Listen"])
def test_a_source_that_is_not_lives_own_sound_is_refused(conn, song, measured, source):
    offer_drums(song)
    out = call(server.listen, None, source=source, **LISTEN)
    assert out.startswith("Error: 'Listen' cannot take its input from '%s'" % source)
    assert "It can listen to: Resampling, Drums." in out
    assert "set_track_routing" not in conn.commands() and not CHANGES & set(conn.commands())


def test_the_input_is_put_back_when_no_take_comes(conn, song, measured):
    offer_drums(song)
    song.wait = 10 ** 6
    out = call(server.listen, None, source="Drums", **LISTEN)
    assert out.startswith("Error: no take was recorded") and "put its input back to 'Resampling'" in out
    assert song.tracks[2].input_routing_type.display_name == "Resampling"


def test_monitoring_must_still_be_off_with_a_source(conn, song, measured):
    offer_drums(song)
    song.tracks[2].current_monitoring_state = 0
    out = call(server.listen, None, source="Drums", **LISTEN)
    assert "monitoring on 'Listen' is 'in'" in out and "set_track_routing" not in conn.commands()


# ---------------------------------------------------------------- spectrogram windows

def test_spectrogram_bars_draws_only_those_bars(conn, song, measured):
    # 120 bpm 4/4: 2 s a bar, so bars 2-3 start 2 s in and last 4 s (the fake take is 6 s long);
    # a spectrogram of all 16 bars would be refused
    out = call(server.listen, None, bars=16, spectrogram_bars="2-3", **LISTEN)
    assert isinstance(out, list) and measured.drawn == [(4.0, 2.0, None)]
    assert isinstance(call(server.listen, None, bars=16, spectrogram_bars="3", spectrogram_max_hz=2000,
                           **LISTEN), list)
    assert measured.drawn[-1] == (2.0, 4.0, 2000)


def test_spectrogram_max_hz_alone_draws_the_whole_take_up_to_it(conn, song, measured):
    out = call(server.listen, None, spectrogram_max_hz=4000, **LISTEN)
    assert isinstance(out, list) and measured.drawn == [(6.0, None, 4000)]


@pytest.mark.parametrize("kwargs, expected", [
    (dict(bars=16, spectrogram_bars="1-16"), "spectrogram_bars 16 bars at 120.0 bpm 4/4 is 32 s"),
    (dict(bars=4, spectrogram_bars="3-5"), "runs past the 4 bars recorded"),
    (dict(bars=4, spectrogram_bars="0-2"), "whole bars from 1"),
    (dict(bars=4, spectrogram_bars="4-2"), "runs backwards"),
    (dict(bars=4, spectrogram_bars="two"), "must look like '5-8' or '5'"),
    (dict(bars=4, spectrogram_max_hz=100), "spectrogram_max_hz must be 200-20000"),
])
def test_bad_spectrogram_windows_are_refused_before_recording(conn, song, measured, kwargs, expected):
    out = call(server.listen, None, **dict(LISTEN, **kwargs))
    assert out.startswith("Error") and expected in out and "Nothing was recorded" in out
    assert not CHANGES & set(conn.commands()) and measured == []


def test_a_window_past_the_end_of_a_file_is_not_drawn(monkeypatch):
    monkeypatch.setattr(L, "spectrogram_png", lambda *a, **k: b"png")
    out = server._with_spectrogram("text", "/x.wav", False, 10.0, window=(12.0, 4.0))
    assert out == "text\nNo spectrogram: the bars asked for start at 12.0 s, and the file is 10.0 s long."


def test_analyze_audio_clip_draws_a_window_of_a_long_file(conn, song, measured):
    clip = Clip("Take")
    clip.file_path = "/data/Music/Ableton/Sets/Test Project/Samples/Recorded/0002 Take.wav"
    song.tracks[2].clip_slots[1].clip = clip
    out = call(server.analyze_audio_clip, None, 2, 1, spectrogram_bars="2-3")
    assert isinstance(out, list) and measured.drawn == [(4.0, 2.0, None)]
    assert "must look like" in call(server.analyze_audio_clip, None, 2, 1, spectrogram_bars="x")


def test_ffmpeg_seeks_to_the_window_and_resamples_for_max_hz(tmp_path, monkeypatch):
    sent = []

    def fake_run(args, cwd, timeout, allow_fail=False):
        sent.append(args)
        Path(cwd, "spectrum.png").write_bytes(b"png")
        return ""

    monkeypatch.setattr(L, "_run", fake_run)
    assert L.spectrogram_png("/x.wav", ffmpeg="ffmpeg", duration=8.0, start=24.0, max_hz=2000) == b"png"
    args = sent[0]
    assert args[args.index("-ss") + 1] == "24.000" and args[args.index("-t") + 1] == "8.000"
    assert args.index("-ss") < args.index("-i")
    # resampled, not showspectrumpic's start/stop, which ran 12 times slower on the Push
    assert args[args.index("-lavfi") + 1] == ("aformat=channel_layouts=mono,aresample=4000,"
                                              "showspectrumpic=s=800x300:legend=1:fscale=log")
    L.spectrogram_png("/x.wav", ffmpeg="ffmpeg", duration=8.0)
    assert "-ss" not in sent[1] and "-t" not in sent[1]
    # bar 1 starts at 0 s, which still needs the window's length
    L.spectrogram_png("/x.wav", ffmpeg="ffmpeg", duration=4.0, start=0.0)
    assert sent[2][sent[2].index("-ss") + 1] == "0.000" and "-t" in sent[2]


def test_a_failed_spectrogram_keeps_the_measurement(conn, song, measured, monkeypatch):
    def slow(*a, **k):
        raise L.ListenError("ffmpeg took longer than 28 s")

    monkeypatch.setattr(L, "spectrogram_png", slow)
    out = call(server.listen, None, spectrogram=True, **LISTEN)
    assert isinstance(out, str) and out.startswith("Listened") and "Loudness -4.6 LUFS" in out
    assert out.endswith("No spectrogram: ffmpeg took longer than 28 s.")


# ------------------------------------------------- the whole mix before the Main fader (quiet)

def offer_main(song):
    """Live offers Main as an input, with a pre-fader (Post FX) and a post-fader (Post Mixer) tap."""
    listen = song.tracks[2]
    listen.available_input_routing_types.append(routing("Main"))
    listen.available_input_routing_channels = [routing("Pre FX"), routing("Post FX"), routing("Post Mixer")]


def master_volumes(conn):
    return [p.get("value") for c, p in conn.sent if c == "set_track_volume" and p.get("track_type") == "master"]


def test_the_whole_mix_is_taken_before_the_main_fader(conn, song, measured):
    offer_main(song)
    out = call(server.listen, None, **LISTEN)
    assert routings_sent(conn)[0] == {"routing_type": "Main"}
    fired = conn.commands().index("record_into_slot")
    assert fired > conn.commands().index("set_track_routing")
    listen = song.tracks[2]
    assert listen.input_routing_type.display_name == "Resampling" and listen.input_routing_channel.display_name \
        == "Post FX"
    assert out.startswith("Listened on 'Listen' (track 2) at 120.0 bpm 4/4: took its input from 'Main' (Post FX);")
    assert "put its input back to 'Resampling'" in out and master_volumes(conn) == []


def test_main_as_a_source_is_tapped_before_its_fader(conn, song, measured):
    offer_main(song)
    song.tracks[2].input_routing_type = routing("Ext. In")
    out = call(server.listen, None, source="Main", **LISTEN)
    assert "took its input from 'Main' (Post FX)" in out
    assert song.tracks[2].input_routing_type.display_name == "Ext. In"


def test_without_a_main_input_the_mix_is_still_taken_from_resampling(conn, song, measured):
    out = call(server.listen, None, **LISTEN)
    assert "set_track_routing" not in conn.commands() and out.startswith("Listened")


def test_quiet_turns_main_down_for_the_take_and_puts_it_back(conn, song, measured):
    offer_main(song)
    song.master_track.mixer_device.volume.value = 0.7
    out = call(server.listen, None, quiet=True, **LISTEN)
    assert master_volumes(conn) == [0.0, 0.7] and song.master_track.mixer_device.volume.value == pytest.approx(0.7)
    commands = conn.commands()
    down = commands.index("set_track_volume")
    up = len(commands) - 1 - commands[::-1].index("set_track_volume")
    assert down < commands.index("record_into_slot") < up
    assert "turned Main all the way down" in out and "put Main back to" in out


def test_quiet_with_main_already_down_changes_nothing_there(conn, song, measured):
    offer_main(song)
    song.master_track.mixer_device.volume.value = 0.0
    out = call(server.listen, None, quiet=True, **LISTEN)
    assert master_volumes(conn) == [] and out.startswith("Listened") and "Main all the way down" not in out


def test_quiet_puts_main_back_when_no_take_comes(conn, song, measured):
    offer_main(song)
    song.wait = 10 ** 6
    out = call(server.listen, None, quiet=True, **LISTEN)
    assert out.startswith("Error: no take was recorded") and "put Main back to" in out
    assert song.master_track.mixer_device.volume.value == pytest.approx(0.85)


def test_quiet_is_refused_when_the_take_would_come_after_the_fader(conn, song, measured):
    out = call(server.listen, None, quiet=True, **LISTEN)
    assert out.startswith("Error: 'Listen' records Resampling, which comes after the Main fader")
    assert not CHANGES & set(conn.commands()) and master_volumes(conn) == []


def test_quiet_with_a_source_needs_no_main_input(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, source="Drums", quiet=True, **LISTEN)
    assert out.startswith("Listened") and master_volumes(conn) == [0.0, 0.85]


# ---------------------------------------------------------------- at a beat, with a scene, several parts

def sent(conn, command):
    return [p for c, p in conn.sent if c == command]


def test_at_beat_plays_from_one_bar_before_and_puts_a_stopped_live_back(conn, song, measured):
    song.is_playing = False
    out = call(server.listen, None, at_beat=16.0, **LISTEN)
    commands = conn.commands()
    # Play from bar 4 (the take fires on the next bar line, bar 5), then the take
    assert sent(conn, "start_playback") == [{"at_beat": 12.0}]
    assert commands.index("start_playback") < commands.index("record_into_slot") < commands.index("stop_playback")
    assert song.is_playing is False and song.current_song_time == 130.0
    assert out.startswith("Each take is bars 5-6 of the Arrangement (from beat 16). Live was stopped before, so it "
                          "was stopped again and the playhead put back to beat 130.")
    assert "Listened on 'Listen'" in out and measured


def test_at_beat_while_playing_plays_on(conn, song, measured):
    out = call(server.listen, None, at_beat=16.0, **LISTEN)
    assert "stop_playback" not in conn.commands() and song.is_playing is True
    assert "Live was playing before, so it plays on from there." in out


def test_at_beat_off_the_launch_grid_is_refused(conn, song, measured):
    out = call(server.listen, None, at_beat=18.0, **LISTEN)
    assert out.startswith("Error: a take starts on the launch grid (every 4 beats here), and at_beat 18 is between "
                          "16 (bar 5) and 20 (bar 6).")
    assert not CHANGES & set(conn.commands()) and "start_playback" not in conn.commands()


def test_at_beat_on_a_two_bar_grid(conn, song, measured):
    song.clip_trigger_quantization = 3
    assert "every 8 beats" in call(server.listen, None, at_beat=4.0, **LISTEN)
    call(server.listen, None, at_beat=16.0, **LISTEN)
    assert sent(conn, "start_playback") == [{"at_beat": 8.0}]


def test_at_beat_0_starts_live_with_the_take(conn, song, measured):
    out = call(server.listen, None, at_beat=0.0, **LISTEN)
    commands = conn.commands()
    assert "start_playback" not in commands
    assert commands.index("stop_playback") < commands.index("record_into_slot")
    assert {"time": 0.0} in sent(conn, "set_current_song_time") and out.startswith("Each take is bars 1-2")


def test_a_scene_is_fired_with_the_take(conn, song, measured):
    song.is_playing = False
    out = call(server.listen, None, scene=1, **LISTEN)
    commands = conn.commands()
    assert song.fired_scenes == ["Scene 2"]
    assert commands.index("start_playback") < commands.index("fire_scene") < commands.index("record_into_slot")
    assert song.is_playing is False
    assert out.startswith("Scene 1 was fired with each take, so the takes start with it. Live was stopped before")
    assert "play their Session clips until back_to_arrangement" in out


def test_several_sources_take_one_pass_each_from_the_same_beat(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, at_beat=16.0, sources=["Drums", "mix"], **LISTEN)
    assert sent(conn, "start_playback") == [{"at_beat": 12.0}, {"at_beat": 12.0}]
    assert conn.commands().count("record_into_slot") == 2 and len(measured) == 2
    assert "== Drums ==\nListened on 'Listen' (track 2) at 120.0 bpm 4/4: took its input from 'Drums'" in out
    assert "== the whole mix ==\nListened on 'Listen'" in out
    assert song.tracks[2].input_routing_type.display_name == "Resampling"
    assert all(slot.clip is None for slot in song.tracks[2].clip_slots)


def test_several_sources_without_a_cue_listen_to_what_plays(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, sources=["Drums", "mix"], **LISTEN)
    assert "start_playback" not in conn.commands() and out.startswith("== Drums ==")


def test_several_kept_takes_go_into_the_next_empty_slots(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, sources=["Drums", "mix"], keep=True, **LISTEN)
    assert "kept the take in slot 0" in out and "kept the take in slot 1" in out


def test_a_failed_pass_stops_the_rest(conn, song, measured):
    offer_drums(song)
    song.wait = 10 ** 6
    out = call(server.listen, None, at_beat=16.0, sources=["Drums", "mix"], **LISTEN)
    assert conn.commands().count("record_into_slot") == 1 and "Error: no take was recorded" in out
    assert out.endswith("Stopped after that pass; the parts after it were not recorded.")


def test_every_source_is_checked_before_anything_is_recorded(conn, song, measured):
    offer_drums(song)
    out = call(server.listen, None, sources=["Drums", "Bass"], **LISTEN)
    assert out.startswith("Error: 'Listen' cannot take its input from 'Bass'")
    assert not CHANGES & set(conn.commands())


@pytest.mark.parametrize("kwargs, expected", [
    (dict(at_beat=16.0, scene=0), "give at_beat (the Arrangement) or scene (the Session), not both"),
    (dict(at_beat=-4.0), "at_beat must be 0 or later"),
    (dict(scene=-1), "scene must be a scene index"),
    (dict(source="Drums", sources=["mix"]), "give source (one part) or sources (several), not both"),
    (dict(sources=[]), "sources takes 1 to 4 parts"),
    (dict(sources=["mix"] * 5), "sources takes 1 to 4 parts"),
    (dict(sources=["mix", "mix"], clip_index=1), "leave clip_index out"),
])
def test_bad_cues_and_sources_are_refused(conn, song, measured, kwargs, expected):
    song.is_playing = False
    out = call(server.listen, None, **dict(LISTEN, **kwargs))
    assert out.startswith("Error") and expected in out
    assert not CHANGES & set(conn.commands()) and "start_playback" not in conn.commands()


def test_at_beat_needs_the_1_10_26_remote_script(conn, song, measured, monkeypatch):
    import MCP_Server.script_handshake as sh
    caps = [c for c in sh._script_info["capabilities"] if c != "start_playback_at_beat"]
    monkeypatch.setattr(sh, "_script_info", {"script_version": "1.10.25", "capabilities": caps})
    assert "needs the Remote Script 1.10.26" in call(server.listen, None, at_beat=16.0, **LISTEN)
