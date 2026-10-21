"""Tests for get_audio_clip_info and set_audio_clip_warp / gain / pitch.

No Ableton, no network. ``_Framework`` is stubbed and the script class is
instantiated without ``__init__`` (which would open a socket). The Live Object
Model (tracks, Session slots, Arrangement clips, audio and MIDI clips) is a
small fake. Attribute names on the fake clip (warping, warp_mode, gain,
gain_display_string, pitch_coarse, pitch_fine, loop_start, loop_end,
start_marker, end_marker, file_path, warp_markers) are the ones the Remote
Script reads; they are UNVERIFIED against a real Live except where an upstream
PR or the existing snapshot code already uses them.
"""

import asyncio
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

import MCP_Server.server as server

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")

COMMANDS = ("get_audio_clip_info", "set_audio_clip_warp",
            "set_audio_clip_gain", "set_audio_clip_pitch")


# ----------------------------------------------------------------- fixtures

def _load_script_module():
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)
    spec = importlib.util.spec_from_file_location(
        "ableton_mcp_script_audio_clip", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeMarker(object):
    def __init__(self, beat_time, sample_time):
        self.beat_time = beat_time
        self.sample_time = sample_time


class FakeAudioClip(object):
    is_audio_clip = True
    is_midi_clip = False

    def __init__(self, name="loop", length=64.0, start_time=0.0):
        self.name = name
        self.length = length
        self.start_time = start_time
        self.end_time = start_time + length
        self.looping = True
        self.loop_start = 0.0
        self.loop_end = length
        self.start_marker = 0.0
        self.end_marker = length
        self.warping = True
        self.warp_mode = 0
        self.gain = 0.4
        self.pitch_coarse = 0
        self.pitch_fine = 0.0
        self.file_path = "/samples/loop.wav"
        self.warp_markers = [FakeMarker(0.0, 0.0), FakeMarker(64.0, 131.0)]

    @property
    def gain_display_string(self):
        return "%.1f dB" % ((self.gain - 0.4) * 30.0 - 18.0)


class FakeMidiClip(object):
    is_audio_clip = False
    is_midi_clip = True

    def __init__(self):
        self.name = "notes"
        self.length = 4.0
        self.warping = False
        self.gain = 0.0


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeTrack(object):
    def __init__(self, name, slots, arrangement=()):
        self.name = name
        self.clip_slots = list(slots)
        self.arrangement_clips = list(arrangement)


class FakeSong(object):
    def __init__(self):
        self.session_clip = FakeAudioClip("session loop")
        self.arr_a = FakeAudioClip("arr A", 16.0, 0.0)
        self.arr_b = FakeAudioClip("arr B", 32.0, 16.0)
        self.arr_midi = FakeMidiClip()
        self.tracks = [
            FakeTrack("1-Audio", [FakeSlot(self.session_clip), FakeSlot()],
                      [self.arr_a, self.arr_b]),
            FakeTrack("2-Midi", [FakeSlot(FakeMidiClip())], [self.arr_midi]),
        ]


@pytest.fixture
def song():
    return FakeSong()


@pytest.fixture
def inst(script_module, song):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


# ------------------------------------------------------- get_audio_clip_info

def test_info_reads_a_session_clip(inst, song):
    reply = run(inst, "get_audio_clip_info", track_index=0, clip_index=0)
    assert reply["status"] == "success"
    info = reply["result"]
    assert info["name"] == "session loop"
    assert info["arrangement"] is False
    assert info["length"] == 64.0
    assert info["warping"] is True
    assert info["warp_mode"] == 0 and info["warp_mode_name"] == "Beats"
    assert info["gain"] == pytest.approx(0.4)
    assert info["gain_display_string"] == "-18.0 dB"
    assert info["pitch_coarse"] == 0 and info["pitch_fine"] == 0.0
    assert (info["loop_start"], info["loop_end"]) == (0.0, 64.0)
    assert (info["start_marker"], info["end_marker"]) == (0.0, 64.0)
    assert info["file_path"] == "/samples/loop.wav"
    assert info["warp_marker_count"] == 2
    assert info["warp_markers"][1] == {"beat_time": 64.0, "sample_time": 131.0}
    assert "start_time" not in info


def test_info_reads_an_arrangement_clip_by_position(inst, song):
    info = run(inst, "get_audio_clip_info", track_index=0, clip_index=1,
               arrangement=True)["result"]
    assert info["name"] == "arr B"
    assert info["arrangement"] is True
    assert (info["start_time"], info["end_time"]) == (16.0, 48.0)


def test_info_reports_the_name_for_every_known_warp_mode(inst, song):
    expected = {0: "Beats", 1: "Tones", 2: "Texture", 3: "Re-Pitch",
                4: "Complex", 6: "Complex Pro"}
    for number, name in expected.items():
        song.session_clip.warp_mode = number
        info = run(inst, "get_audio_clip_info", track_index=0,
                   clip_index=0)["result"]
        assert (info["warp_mode"], info["warp_mode_name"]) == (number, name)


def test_info_survives_a_clip_without_optional_attributes(inst, song):
    del song.session_clip.warp_markers
    del song.session_clip.file_path
    info = run(inst, "get_audio_clip_info", track_index=0, clip_index=0)["result"]
    assert info["warp_markers"] == []
    assert "file_path" not in info


# ---------------------------------------------------------------- refusals

@pytest.mark.parametrize("command,extra", [
    ("get_audio_clip_info", {}),
    ("set_audio_clip_warp", {"warping": False}),
    ("set_audio_clip_gain", {"gain": 0.5}),
    ("set_audio_clip_pitch", {"pitch_coarse": 1}),
])
def test_midi_clips_and_empty_slots_are_refused(inst, command, extra):
    midi = run(inst, command, track_index=1, clip_index=0, **extra)
    assert midi["status"] == "error"
    assert "not an audio clip" in midi["message"]
    arr_midi = run(inst, command, track_index=1, clip_index=0,
                   arrangement=True, **extra)
    assert arr_midi["status"] == "error"
    assert "not an audio clip" in arr_midi["message"]
    empty = run(inst, command, track_index=0, clip_index=1, **extra)
    assert empty["status"] == "error"
    assert "empty" in empty["message"]


@pytest.mark.parametrize("track,clip,arrangement", [
    (5, 0, False), (-1, 0, False), (0, 9, False), (0, -1, False),
    (0, 2, True), (0, 5, True),
])
def test_out_of_range_indices_are_clear_errors(inst, track, clip, arrangement):
    reply = run(inst, "get_audio_clip_info", track_index=track,
                clip_index=clip, arrangement=arrangement)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]


@pytest.mark.parametrize("bad", ["0", 1.5, True, None])
def test_indices_must_be_integers(inst, bad):
    assert run(inst, "get_audio_clip_info", track_index=bad,
               clip_index=0)["status"] == "error"
    assert run(inst, "get_audio_clip_info", track_index=0,
               clip_index=bad)["status"] == "error"


@pytest.mark.parametrize("bad", ["yes", 1, None])
def test_arrangement_must_be_a_real_boolean(inst, bad):
    reply = run(inst, "get_audio_clip_info", track_index=0, clip_index=0,
                arrangement=bad)
    assert reply["status"] == "error"
    assert "arrangement" in reply["message"]


# ---------------------------------------------------------------- set warp

def test_warp_off_reports_previous_and_new(inst, song):
    reply = run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
                warping=False)
    assert reply["status"] == "success"
    result = reply["result"]
    assert result["previous"]["warping"] is True
    assert result["value"]["warping"] is False
    assert result["changed"] is True
    assert song.session_clip.warping is False
    assert song.session_clip.warp_mode == 0  # untouched


def test_warp_mode_by_name_and_by_number(inst, song):
    result = run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
                 warping=True, warp_mode="Complex Pro")["result"]
    assert song.session_clip.warp_mode == 6
    assert result["previous"]["warp_mode_name"] == "Beats"
    assert result["value"]["warp_mode_name"] == "Complex Pro"
    run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
        warping=True, warp_mode=3)
    assert song.session_clip.warp_mode == 3


@pytest.mark.parametrize("name,number", [
    ("Beats", 0), ("Tones", 1), ("Texture", 2), ("Re-Pitch", 3),
    ("repitch", 3), ("COMPLEX", 4), ("complex pro", 6), ("complex_pro", 6),
    (4.0, 4),
])
def test_warp_mode_mapping(inst, song, name, number):
    run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
        warping=True, warp_mode=name)
    assert song.session_clip.warp_mode == number


@pytest.mark.parametrize("bad", ["Sparkle", "", 5, 7, -1, 99, True, [3]])
def test_unknown_warp_modes_are_refused_and_nothing_changes(inst, song, bad):
    reply = run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
                warping=False, warp_mode=bad)
    assert reply["status"] == "error"
    assert "warp_mode" in reply["message"]
    assert song.session_clip.warping is True
    assert song.session_clip.warp_mode == 0


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_warping_must_be_a_real_boolean(inst, song, bad):
    reply = run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
                warping=bad)
    assert reply["status"] == "error"
    assert song.session_clip.warping is True


def test_warp_on_an_arrangement_clip_leaves_the_session_clip_alone(inst, song):
    run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
        warping=False, warp_mode="Tones", arrangement=True)
    assert song.arr_a.warping is False and song.arr_a.warp_mode == 1
    assert song.arr_b.warping is True
    assert song.session_clip.warping is True


def test_warp_reports_the_value_read_back_from_live(inst, song):
    """If Live ignores the request the reply must say so, not echo the ask."""
    clip = song.session_clip

    class Stubborn(FakeAudioClip):
        @property
        def warping(self):
            return True

        @warping.setter
        def warping(self, value):
            pass

    stubborn = Stubborn()
    song.tracks[0].clip_slots[0].clip = stubborn
    result = run(inst, "set_audio_clip_warp", track_index=0, clip_index=0,
                 warping=False)["result"]
    assert result["value"]["warping"] is True
    assert result["changed"] is False
    assert clip is not stubborn


# ---------------------------------------------------------------- set gain

def test_gain_reports_previous_and_new_with_display_string(inst, song):
    result = run(inst, "set_audio_clip_gain", track_index=0, clip_index=0,
                 gain=0.7)["result"]
    assert result["previous"]["gain"] == pytest.approx(0.4)
    assert result["value"]["gain"] == pytest.approx(0.7)
    assert result["value"]["gain_display_string"] == "-9.0 dB"
    assert result["changed"] is True
    assert song.session_clip.gain == pytest.approx(0.7)


@pytest.mark.parametrize("edge", [0.0, 1.0, 1, 0])
def test_gain_accepts_the_range_edges(inst, song, edge):
    reply = run(inst, "set_audio_clip_gain", track_index=0, clip_index=0,
                gain=edge)
    assert reply["status"] == "success"
    assert song.session_clip.gain == float(edge)


@pytest.mark.parametrize("bad", [-0.01, 1.01, 6.0, float("nan"), float("inf"),
                                 "0.5", None, True])
def test_gain_outside_the_raw_range_is_refused(inst, song, bad):
    reply = run(inst, "set_audio_clip_gain", track_index=0, clip_index=0,
                gain=bad)
    assert reply["status"] == "error"
    assert "gain" in reply["message"]
    assert song.session_clip.gain == pytest.approx(0.4)


def test_gain_on_an_arrangement_clip(inst, song):
    run(inst, "set_audio_clip_gain", track_index=0, clip_index=0, gain=0.9,
        arrangement=True)
    assert song.arr_a.gain == pytest.approx(0.9)
    assert song.session_clip.gain == pytest.approx(0.4)


# --------------------------------------------------------------- set pitch

def test_pitch_coarse_and_fine_together(inst, song):
    result = run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
                 pitch_coarse=-7, pitch_fine=12.5)["result"]
    assert (song.session_clip.pitch_coarse, song.session_clip.pitch_fine) == (-7, 12.5)
    assert result["previous"] == {"pitch_coarse": 0, "pitch_fine": 0.0}
    assert result["value"] == {"pitch_coarse": -7, "pitch_fine": 12.5}
    assert result["changed"] is True


def test_pitch_leaves_the_omitted_one_alone(inst, song):
    song.session_clip.pitch_fine = 20.0
    run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
        pitch_coarse=3)
    assert song.session_clip.pitch_coarse == 3
    assert song.session_clip.pitch_fine == 20.0
    run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
        pitch_fine=-5)
    assert song.session_clip.pitch_coarse == 3
    assert song.session_clip.pitch_fine == -5.0


@pytest.mark.parametrize("coarse", [-48, 48, 7.0])
def test_pitch_coarse_edges_and_integral_floats(inst, song, coarse):
    reply = run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
                pitch_coarse=coarse)
    assert reply["status"] == "success"
    assert song.session_clip.pitch_coarse == int(coarse)


@pytest.mark.parametrize("fine", [-50, 50, 0.5])
def test_pitch_fine_edges(inst, song, fine):
    assert run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
               pitch_fine=fine)["status"] == "success"
    assert song.session_clip.pitch_fine == float(fine)


@pytest.mark.parametrize("kwargs", [
    {"pitch_coarse": 49}, {"pitch_coarse": -49}, {"pitch_coarse": 1.5},
    {"pitch_coarse": True}, {"pitch_coarse": "3"},
    {"pitch_fine": 50.1}, {"pitch_fine": -50.1}, {"pitch_fine": "5"},
    {"pitch_fine": True}, {"pitch_fine": float("nan")},
    {}, {"pitch_coarse": None, "pitch_fine": None},
])
def test_invalid_pitch_is_refused(inst, song, kwargs):
    reply = run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
                **kwargs)
    assert reply["status"] == "error"
    assert (song.session_clip.pitch_coarse, song.session_clip.pitch_fine) == (0, 0.0)


def test_a_bad_fine_value_blocks_a_good_coarse_value(inst, song):
    """Validate everything first: no half-applied change."""
    reply = run(inst, "set_audio_clip_pitch", track_index=0, clip_index=0,
                pitch_coarse=5, pitch_fine=99)
    assert reply["status"] == "error"
    assert song.session_clip.pitch_coarse == 0


def test_pitch_on_an_arrangement_clip(inst, song):
    run(inst, "set_audio_clip_pitch", track_index=0, clip_index=1,
        pitch_coarse=12, arrangement=True)
    assert song.arr_b.pitch_coarse == 12
    assert song.arr_a.pitch_coarse == 0


# ------------------------------------------------- dispatch and capabilities

@pytest.mark.parametrize("command,extra", [
    ("set_audio_clip_warp", {"warping": False}),
    ("set_audio_clip_gain", {"gain": 0.5}),
    ("set_audio_clip_pitch", {"pitch_coarse": 1}),
])
def test_setters_are_scheduled_on_the_main_thread(inst, command, extra):
    run(inst, command, track_index=0, clip_index=0, **extra)
    assert inst.scheduled == [(0, "main_thread_task")]


def test_the_read_is_not_scheduled(inst):
    run(inst, "get_audio_clip_info", track_index=0, clip_index=0)
    assert inst.scheduled == []


def test_commands_are_advertised_and_dispatched(script_module, inst):
    for command in COMMANDS:
        assert command in script_module.SCRIPT_CAPABILITIES
        reply = run(inst, command, track_index=0, clip_index=0)
        assert not reply.get("message", "").startswith("Unknown command")
    caps = script_module.SCRIPT_CAPABILITIES
    assert len(caps) == len(set(caps))
    assert caps[-4:] == list(COMMANDS)


def test_bundled_copy_is_identical_to_the_remote_script():
    source = REPO_ROOT / "AbletonMCP_Remote_Script" / "__init__.py"
    assert source.read_bytes() == BUNDLED_SCRIPT.read_bytes()


def test_server_treats_setters_as_modifying_and_the_read_as_not():
    class _Sock(object):
        def __init__(self):
            self.timeouts = []

        def settimeout(self, value):
            self.timeouts.append(value)

        def sendall(self, data):
            pass

        def recv(self, _size):
            return b'{"status": "success", "result": {}}'

    for command, expected in (("set_audio_clip_warp", 15.0),
                              ("set_audio_clip_gain", 15.0),
                              ("set_audio_clip_pitch", 15.0),
                              ("get_audio_clip_info", 10.0)):
        conn = server.AbletonConnection(host="x", port=1, sock=_Sock())
        conn.send_command(command, {"track_index": 0, "clip_index": 0})
        assert conn.sock.timeouts[0] == expected, command


# ------------------------------------------------------------- server tools

class FakeConnection(object):
    def __init__(self, response=None, raise_exc=None):
        self.response = response if response is not None else {}
        self.raise_exc = raise_exc
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, params or {}))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    fake = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    return fake


def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def test_tools_are_registered_with_a_user_prompt_parameter():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in COMMANDS:
        assert name in tools
        assert "user_prompt" in tools[name].inputSchema["properties"]


def test_info_tool_forwards_params(conn):
    conn.response = {"name": "loop", "warping": True}
    out = json.loads(call(server.get_audio_clip_info, None, 2, 3, arrangement=True))
    assert conn.sent == [("get_audio_clip_info", {
        "track_index": 2, "clip_index": 3, "arrangement": True})]
    assert out["warping"] is True


def test_warp_tool_forwards_params_and_omits_an_absent_mode(conn):
    call(server.set_audio_clip_warp, None, 0, 1, False)
    call(server.set_audio_clip_warp, None, 0, 1, True, warp_mode="Complex",
         arrangement=True)
    call(server.set_audio_clip_warp, None, 0, 1, True, warp_mode=6)
    assert conn.sent[0] == ("set_audio_clip_warp", {
        "track_index": 0, "clip_index": 1, "warping": False, "arrangement": False})
    assert conn.sent[1][1]["warp_mode"] == "Complex"
    assert conn.sent[1][1]["arrangement"] is True
    assert conn.sent[2][1]["warp_mode"] == 6


def test_gain_and_pitch_tools_forward_params(conn):
    call(server.set_audio_clip_gain, None, 0, 0, 0.55)
    call(server.set_audio_clip_pitch, None, 0, 0, pitch_coarse=-2)
    call(server.set_audio_clip_pitch, None, 0, 0, pitch_fine=10.0, arrangement=True)
    assert conn.sent[0] == ("set_audio_clip_gain", {
        "track_index": 0, "clip_index": 0, "gain": 0.55, "arrangement": False})
    assert conn.sent[1] == ("set_audio_clip_pitch", {
        "track_index": 0, "clip_index": 0, "pitch_coarse": -2, "arrangement": False})
    assert conn.sent[2] == ("set_audio_clip_pitch", {
        "track_index": 0, "clip_index": 0, "pitch_fine": 10.0, "arrangement": True})


def test_tool_reports_script_errors_as_text(conn):
    conn.raise_exc = Exception("The clip is not an audio clip")
    out = call(server.set_audio_clip_gain, None, 1, 0, 0.5)
    assert out.startswith("Error setting audio clip gain:")
    assert "not an audio clip" in out


def test_tool_returns_the_capability_message_for_an_old_script(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    assert call(server.get_audio_clip_info, None, 0, 0) == "missing get_audio_clip_info"
    assert call(server.set_audio_clip_pitch, None, 0, 0, 1) == "missing set_audio_clip_pitch"
    assert conn.sent == []


def test_docstrings_carry_the_warnings():
    warp_doc = " ".join(server.set_audio_clip_warp.__doc__.split())
    gain_doc = " ".join(server.set_audio_clip_gain.__doc__.split())
    assert "can change what plays" in warp_doc
    assert "raw Clip.gain" in gain_doc
    assert "NOT dB" in gain_doc
