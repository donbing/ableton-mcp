# /// script
# requires-python = ">=3.10"
# dependencies = ["lameenc>=1.7"]
# ///
"""Turn a WAV that render_song left on the Push into an MP3 on this computer.

render_song records the song to a WAV on the Push and prints its path (`File: ...`). The Push's
ffmpeg has no MP3 encoder, so the MP3 is made here: the WAV is copied over SSH, the silence after the
reverb tail is cut, the last 1.5 s fade out, and LAME encodes it (24-bit takes go to 16-bit by keeping
their top two bytes). Run on 2026-10-29 for "Play With Me": 2:52 at 320 kbps.

    pip install lameenc
    python tools/push_mp3.py "/data/Music/Ableton/Sets/<Set> Project/Samples/Recorded/<take>.wav" \
        "~/Music/<Song>.mp3"

The first argument can also be a WAV on this computer.
"""

import argparse
import array
import os
import shlex
import subprocess
import sys
import tempfile
import wave

FADE_SECONDS = 1.5
# a tail quieter than this for its whole length is cut (the take runs a few bars past the song)
SILENCE_DB = -60.0
TAIL_KEEP_SECONDS = 0.5


def to_16_bit(frames, width):
    """PCM bytes of `width` bytes a sample as 16-bit samples (array 'h')."""
    if width == 2:
        out = array.array("h")
        out.frombytes(frames)
        return out
    if width == 3:
        pcm = bytearray(len(frames) // 3 * 2)
        pcm[0::2] = frames[1::3]
        pcm[1::2] = frames[2::3]
        out = array.array("h")
        out.frombytes(bytes(pcm))
        return out
    raise ValueError("only 16- and 24-bit WAVs, not %d-bit" % (8 * width))


def sound_end(samples, channels, rate, silence_db=SILENCE_DB, keep=TAIL_KEEP_SECONDS):
    """Sample count to keep: up to the last sample above silence_db, plus `keep` seconds."""
    limit = 32768 * 10 ** (silence_db / 20)
    last = len(samples) - 1
    while last >= 0 and abs(samples[last]) <= limit:
        last -= 1
    if last < 0:
        return len(samples)
    end = (last // channels + 1 + int(keep * rate)) * channels
    return min(end, len(samples))


def fade_out(samples, channels, rate, seconds=FADE_SECONDS):
    """Fade the last `seconds` to silence, in place."""
    n = len(samples)
    length = min(int(seconds * rate) * channels, n)
    start = n - length
    for i in range(start, n):
        samples[i] = int(samples[i] * (n - i) / length)
    return samples


def read_wav(path):
    with wave.open(path, "rb") as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        samples = to_16_bit(w.readframes(w.getnframes()), width)
    return samples, channels, rate


def encode_mp3(samples, channels, rate, kbps=320):
    import lameenc
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(kbps)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    return encoder.encode(samples.tobytes()) + encoder.flush()


def fetch(remote, host, folder):
    """Copy a WAV from the Push into `folder` (ssh cat: Set names have spaces, brackets and
    parentheses, and scp quotes remote paths differently from one version to the next); returns
    the local path."""
    local = os.path.join(folder, "render.wav")
    with open(local, "wb") as f:
        subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", host, "cat -- " + shlex.quote(remote)],
                       stdout=f, check=True)
    return local


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("wav", help="the WAV's path on the Push, as render_song printed it, or a local WAV")
    parser.add_argument("mp3", help="where to write the MP3")
    parser.add_argument("--host", default="push3", help="the Push's SSH host (default push3)")
    parser.add_argument("--kbps", type=int, default=320)
    parser.add_argument("--keep-tail", action="store_true", help="do not cut the silence at the end")
    args = parser.parse_args(argv)
    try:
        import lameenc  # noqa: F401
    except ImportError:
        sys.exit("lameenc is not installed: pip install lameenc")
    with tempfile.TemporaryDirectory() as folder:
        path = args.wav if os.path.isfile(args.wav) else fetch(args.wav, args.host, folder)
        samples, channels, rate = read_wav(path)
    if not args.keep_tail:
        del samples[sound_end(samples, channels, rate):]
    fade_out(samples, channels, rate)
    out = os.path.expanduser(args.mp3)
    data = encode_mp3(samples, channels, rate, args.kbps)
    with open(out, "wb") as f:
        f.write(data)
    print("%s: %.1f s, %d kbps, %d bytes" % (out, len(samples) / channels / rate, args.kbps, len(data)))


if __name__ == "__main__":
    main()
