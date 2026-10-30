"""tools/push_mp3.py: the MP3 of a render_song WAV, made on this computer (the Push's ffmpeg has no
MP3 encoder). The sample handling runs everywhere; the LAME encoding only where lameenc is installed."""
import array
import os
import struct
import sys
import wave

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import push_mp3 as P  # noqa: E402


def test_24_bit_samples_keep_their_top_two_bytes():
    # little-endian 24-bit: 0x123456 and -2 (0xFFFFFE)
    frames = bytes([0x56, 0x34, 0x12, 0xFE, 0xFF, 0xFF])
    assert list(P.to_16_bit(frames, 3)) == [0x1234, -1]


def test_16_bit_samples_pass_through():
    assert list(P.to_16_bit(struct.pack("<hh", 5, -7), 2)) == [5, -7]


def test_other_widths_are_refused():
    with pytest.raises(ValueError, match="only 16- and 24-bit"):
        P.to_16_bit(b"\x00" * 4, 4)


def test_the_silent_tail_is_cut_to_half_a_second():
    rate, channels = 100, 2
    loud = [10000, -10000] * 300          # 3 s of sound
    quiet = [3, -3] * 500                 # 5 s far below -60 dBFS
    samples = array.array("h", loud + quiet)
    assert P.sound_end(samples, channels, rate) == (300 + 50) * channels


def test_a_take_that_is_all_silence_is_kept_whole():
    samples = array.array("h", [0] * 40)
    assert P.sound_end(samples, 2, 10) == 40


def test_the_end_fades_to_silence():
    samples = array.array("h", [1000] * 20)
    P.fade_out(samples, 1, 10, seconds=1.0)
    # the last second ramps down from full level
    assert samples[10] == 1000 and samples[11] < 1000 and samples[-1] == 100


def write_wav(path, frames, width=3, channels=2, rate=44100):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)


def test_a_local_wav_becomes_an_mp3(tmp_path):
    pytest.importorskip("lameenc")
    wav = tmp_path / "take.wav"
    tone = b"".join(struct.pack("<i", (8_000_000 if i % 50 < 25 else -8_000_000))[:3] * 2 for i in range(44100))
    write_wav(wav, tone + b"\x00" * 6 * 44100)
    mp3 = tmp_path / "song.mp3"
    P.main([str(wav), str(mp3)])
    data = mp3.read_bytes()
    assert data[:2] == b"\xff\xfb" or data[:3] == b"ID3"


def test_a_push_path_is_quoted_whole_for_the_remote_shell(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(P.subprocess, "run", lambda cmd, stdout, check: calls.append(cmd))
    local = P.fetch("/data/Sets/Play With Me (Remix) Project/Samples/Recorded/Take 0001 [2026-10-30].wav",
                    "push3", str(tmp_path))
    assert local == os.path.join(str(tmp_path), "render.wav")
    assert calls[0][-2:] == ["push3", "cat -- '/data/Sets/Play With Me (Remix) Project/Samples/Recorded/"
                                      "Take 0001 [2026-10-30].wav'"]
