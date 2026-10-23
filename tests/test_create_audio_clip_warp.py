"""create_audio_clip says what auto-warp did (upstream issue #137) and can turn it off."""
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class AudioClip(object):
    def __init__(self, seconds, rounded_beats, sample_rate=44100.0):
        self.name, self.is_audio_clip = "take", True
        self.sample_rate, self.sample_length = sample_rate, seconds * sample_rate
        self.warp_mode, self._warping = 0, True
        self._rounded, self._seconds = rounded_beats, seconds

    @property
    def warping(self):
        return self._warping

    @warping.setter
    def warping(self, value):
        self._warping = value

    @property
    def length(self):
        return self._rounded if self._warping else self._seconds


class Slot(object):
    has_clip = False

    def __init__(self, clip):
        self._clip = clip

    def create_audio_clip(self, path):
        self.has_clip, self.clip = True, self._clip


def make(script_module, clip, tempo=102.0):
    song = types.SimpleNamespace(tempo=tempo, tracks=[types.SimpleNamespace(
        has_midi_input=False, has_audio_input=True, clip_slots=[Slot(clip)])])
    return make_inst(script_module, song)


def run(inst, **params):
    return inst._process_command({"type": "create_audio_clip", "params": dict(
        track_index=0, clip_index=0, path="/tmp/a.wav", **params)})


def test_an_auto_warp_that_rounded_the_length_is_reported(script_module):
    # 38.82 s at 102 BPM is 66 beats; Live imported it as 64 (upstream issue #137)
    result = run(make(script_module, AudioClip(38.82, 64.0)))["result"]
    assert result["warping"] is True and result["length"] == 64.0 and result["length_unit"] == "beats"
    assert result["file_beats_at_set_tempo"] == pytest.approx(66.0, abs=0.01)
    assert "auto-warp" in result["warning"] and "warping=false" in result["warning"]


def test_warping_false_keeps_the_files_own_length(script_module):
    result = run(make(script_module, AudioClip(38.82, 64.0)), warping=False)["result"]
    assert result["warping"] is False and result["length_unit"] == "seconds"
    assert result["length"] == pytest.approx(38.82) and "warning" not in result


def test_unwarped_length_is_the_files_even_if_live_still_reads_the_warped_one(script_module):
    clip = AudioClip(1.65, 4.0)
    type(clip).length = property(lambda self: self._rounded)      # stale: always the warped value
    try:
        result = run(make(script_module, clip), warping=False)["result"]
    finally:
        type(clip).length = property(lambda self: self._rounded if self._warping else self._seconds)
    assert result["length"] == pytest.approx(1.65)


def test_a_clip_whose_length_matches_has_no_warning(script_module):
    result = run(make(script_module, AudioClip(2.0, 4.0), tempo=120.0))["result"]
    assert "warning" not in result and result["warping"] is True


def test_warping_must_be_a_boolean(script_module):
    reply = run(make(script_module, AudioClip(2.0, 4.0)), warping="no")
    assert reply["status"] == "error" and "warping must be true or false" in reply["message"]


def test_tool_message_carries_the_warning_and_forwards_warping(conn):
    conn.response = {"name": "take", "length": 64.0, "length_unit": "beats", "warping": True,
                     "file_seconds": 38.82, "warning": "auto-warp rounded it"}
    out = call(server.create_audio_clip, None, 0, 0, "/tmp/a.wav", warping=False)
    assert conn.sent[-1][1]["warping"] is False
    assert "warping on" in out and "file 38.820 s" in out and "WARNING: auto-warp rounded it" in out
    call(server.create_audio_clip, None, 0, 0, "/tmp/a.wav")
    assert "warping" not in conn.sent[-1][1]
