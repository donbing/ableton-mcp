"""configure_simpler: a recording of your own as an instrument (Simpler.replace_sample, playback_mode, retrigger)."""
import os
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Simpler(object):
    name, class_name = "Cowbell", "OriginalSimpler"

    def __init__(self):
        self.playback_mode, self.retrigger, self.slicing_playback_mode = 0, False, 1
        self.sample = types.SimpleNamespace(file_path="/old.wav")
        self.loaded = []

    def replace_sample(self, path):
        if path.endswith("bad.wav"):
            raise RuntimeError("cannot decode")
        self.loaded.append(path)
        self.sample = types.SimpleNamespace(file_path=path)


def make(script_module, device=None):
    device = device or Simpler()
    track = types.SimpleNamespace(name="Pluck", devices=[device])
    return device, make_inst(script_module, types.SimpleNamespace(tracks=[track]))


def run(inst, **params):
    base = dict(track_index=0, device_index=0, expected_name="Pluck", expected_device_name="Cowbell")
    base.update(params)
    return inst._process_command({"type": "configure_simpler", "params": base})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_a_sample_and_the_mode_are_set_and_read_back(script_module, tmp_path):
    wav = tmp_path / "pluck.wav"
    wav.write_bytes(b"RIFF")
    device, inst = make(script_module)
    r = ok(run(inst, sample_path=str(wav), playback_mode="One-Shot", retrigger=True, slicing_playback_mode="thru"))
    assert r["before"]["sample_file"] == "/old.wav" and r["before"]["playback_mode"] == "classic"
    assert r["after"] == {"device": "Cowbell", "class": "OriginalSimpler", "playback_mode": "one-shot",
                          "slicing_playback_mode": "thru", "retrigger": True, "sample_file": str(wav)}
    assert device.playback_mode == 1 and device.slicing_playback_mode == 2


@pytest.mark.parametrize("kwargs,needle", [
    (dict(), "Give sample_path"),
    (dict(sample_path="relative.wav"), "absolute path of an existing audio file"),
    (dict(sample_path="/does/not/exist.wav"), "absolute path of an existing audio file"),
    (dict(playback_mode="loop"), "playback_mode must be"),
    (dict(retrigger="yes"), "retrigger must be"),
    (dict(slicing_playback_mode="stereo"), "slicing_playback_mode must be"),
    (dict(expected_device_name="Other", playback_mode="classic"), "not 'Other'"),
    (dict(expected_name="Other", playback_mode="classic"), "not 'Other'"),
])
def test_bad_input_changes_nothing(script_module, kwargs, needle):
    device, inst = make(script_module)
    assert needle in err(run(inst, **kwargs))
    assert (device.playback_mode, device.retrigger, device.loaded) == (0, False, [])


def test_a_file_live_cannot_decode_is_reported(script_module, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"x")
    device, inst = make(script_module)
    assert "could not load that file" in err(run(inst, sample_path=str(bad)))


def test_only_a_simpler_is_accepted(script_module):
    other = types.SimpleNamespace(name="Cowbell", class_name="DrumGroupDevice")
    _, inst = make(script_module, other)
    assert "not a Simpler" in err(run(inst, playback_mode="classic"))


def test_tool(conn):
    conn.response = {"after": {}}
    call(server.configure_simpler, None, 0, 1, "Pluck", "Simpler", "/tmp/a.wav", "one-shot", True)
    assert conn.sent[-1] == ("configure_simpler", {"track_index": 0, "device_index": 1, "expected_name": "Pluck",
                                                   "expected_device_name": "Simpler", "track_type": "track",
                                                   "sample_path": "/tmp/a.wav", "playback_mode": "one-shot", "retrigger": True})
    assert "required" in call(server.configure_simpler, None, 0, 1, None, "Simpler")
    assert "configure_simpler" in MODIFYING_TOOLS
