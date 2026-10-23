"""Devices by name, scale, scene tempo, grooves, warp markers, clip copies (all measured on Live 12.4 Lite)."""
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import FakeNote, NoteVector, make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


# ------------------------------------------------------------------ devices

class Device(object):
    def __init__(self, name):
        self.name = name


AVAILABLE = {"Compressor", "Reverb", "Utility", "Limiter"}


class DevTrack(object):
    def __init__(self, name, devices=()):
        self.name = name
        self.devices = [Device(n) for n in devices]

    def insert_device(self, name, index=None):
        if name not in AVAILABLE:
            raise RuntimeError("Device %s not available." % name if name in ("EQ Eight",) else "Device %s not found." % name)
        d = Device(name)
        self.devices.insert(len(self.devices) if index is None else index, d)
        return d

    def duplicate_device(self, i):
        if i >= len(self.devices):
            raise RuntimeError("bad index")
        self.devices.insert(i + 1, Device(self.devices[i].name))


class DevSong(object):
    def __init__(self):
        self.tracks = [DevTrack("Bass", ["Amp"]), DevTrack("Keys", ["Reverb"])]
        self.return_tracks, self.master_track = [DevTrack("A-Reverb")], DevTrack("Main")

    def move_device(self, device, target, position):
        for t in self.tracks + self.return_tracks + [self.master_track]:
            if device in t.devices:
                t.devices.remove(device)
        target.devices.insert(position, device)
        return position


@pytest.fixture
def dev(script_module):
    song = DevSong()
    return song, make_inst(script_module, song)


def test_a_native_device_is_inserted_by_name_at_the_end_or_at_a_position(dev):
    song, inst = dev
    r = ok(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="Compressor"))
    assert r["devices"] == ["Amp", "Compressor"] and r["position"] == 1
    r = ok(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="Utility", index=0))
    assert r["devices"] == ["Utility", "Amp", "Compressor"] and r["position"] == 0


def test_a_device_this_edition_lacks_or_a_wrong_name_changes_nothing(dev):
    song, inst = dev
    assert "not available" in err(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="EQ Eight"))
    assert "not found" in err(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="Nope"))
    assert "not 'Other'" in err(run(inst, "insert_device", track_index=0, expected_name="Other", device_name="Reverb"))
    assert "device_name is required" in err(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name=""))
    assert "index must be" in err(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="Reverb", index=9))
    assert [d.name for d in song.tracks[0].devices] == ["Amp"]


def test_a_device_can_be_inserted_on_a_return_and_the_master(dev):
    song, inst = dev
    ok(run(inst, "insert_device", track_index=0, track_type="return", expected_name="A-Reverb", device_name="Limiter"))
    ok(run(inst, "insert_device", track_type="master", expected_name="Main", device_name="Limiter"))
    assert [d.name for d in song.return_tracks[0].devices] == ["Limiter"] and [d.name for d in song.master_track.devices] == ["Limiter"]


def test_a_device_moves_inside_its_chain_and_to_another_track(dev):
    song, inst = dev
    ok(run(inst, "insert_device", track_index=0, expected_name="Bass", device_name="Compressor"))
    r = ok(run(inst, "move_device", track_index=0, device_index=1, new_index=0, expected_name="Bass",
               expected_device_name="Compressor"))
    assert r["devices"] == ["Compressor", "Amp"] and r["position"] == 0
    r = ok(run(inst, "move_device", track_index=0, device_index=0, new_index=1, expected_name="Bass",
               expected_device_name="Compressor", to_track_index=1, to_expected_name="Keys"))
    assert r["devices"] == ["Reverb", "Compressor"] and r["source_devices"] == ["Amp"]


@pytest.mark.parametrize("kwargs,needle", [
    (dict(expected_device_name="Nope"), "not 'Nope'"),
    (dict(device_index=7), "out of range"),
    (dict(new_index=-1), "chain position"),
    (dict(new_index=9), "past the end"),
    (dict(expected_name=None), "expected_name is required"),
    (dict(to_track_index=1), "expected_name is required"),
])
def test_bad_device_moves_change_nothing(dev, kwargs, needle):
    song, inst = dev
    args = dict(track_index=0, device_index=0, new_index=0, expected_name="Bass", expected_device_name="Amp")
    args.update(kwargs)
    assert needle in err(run(inst, "move_device", **args))
    assert [d.name for d in song.tracks[0].devices] == ["Amp"]


def test_a_device_is_duplicated_right_after_itself(dev):
    song, inst = dev
    r = ok(run(inst, "duplicate_device", track_index=1, device_index=0, expected_name="Keys", expected_device_name="Reverb"))
    assert r["devices"] == ["Reverb", "Reverb"]
    assert "not 'Other'" in err(run(inst, "duplicate_device", track_index=1, device_index=0, expected_name="Keys", expected_device_name="Other"))


# -------------------------------------------------------------------- scale

SCALES = {"Major": [0, 2, 4, 5, 7, 9, 11], "Minor": [0, 2, 3, 5, 7, 8, 10], "Dorian": [0, 2, 3, 5, 7, 9, 10]}


class ScaleSong(object):
    def __init__(self):
        self.root_note, self._scale, self.scale_mode = 0, "Major", True

    @property
    def scale_name(self):
        return self._scale

    @scale_name.setter
    def scale_name(self, v):
        # measured: Live does not raise for an unknown name, it falls back to Major
        self._scale = v if v in SCALES else "Major"

    @property
    def scale_intervals(self):
        return SCALES[self._scale]


def test_the_scale_is_read_with_its_notes(script_module):
    r = ok(run(make_inst(script_module, ScaleSong()), "get_song_scale"))
    assert (r["root_name"], r["scale_name"], r["scale_notes"]) == ("C", "Major", ["C", "D", "E", "F", "G", "A", "B"])


@pytest.mark.parametrize("root,expected", [("F#", 6), ("Bb", 10), ("a", 9), (3, 3), ("db", 1)])
def test_the_key_can_be_a_name_or_a_number(script_module, root, expected):
    song = ScaleSong()
    r = ok(run(make_inst(script_module, song), "set_song_scale", root_note=root, scale_name="Minor"))
    assert song.root_note == expected and r["after"]["scale_name"] == "Minor"
    assert r["before"]["root_name"] == "C"


def test_the_scale_tool_refuses_bad_input_and_changes_nothing(script_module):
    song = ScaleSong()
    inst = make_inst(script_module, song)
    assert "Unknown root note" in err(run(inst, "set_song_scale", root_note="H"))
    assert "0-11" in err(run(inst, "set_song_scale", root_note=12))
    ok(run(inst, "set_song_scale", scale_name="Dorian"))
    message = err(run(inst, "set_song_scale", scale_name="Klezmer"))
    assert "does not know a scale called 'Klezmer'" in message and "put back to 'Dorian'" in message
    assert song.scale_name == "Dorian"
    song.scale_name = "Major"
    assert "Give root_note" in err(run(inst, "set_song_scale"))
    assert "scale_mode must be" in err(run(inst, "set_song_scale", scale_mode="on"))
    assert (song.root_note, song.scale_name) == (0, "Major")
    ok(run(inst, "set_song_scale", scale_mode=False))
    assert song.scale_mode is False


# --------------------------------------------------------------- scene tempo

class SceneSong(object):
    def __init__(self):
        self.scenes = [types.SimpleNamespace(name="Verse", tempo=-1.0, tempo_enabled=False, time_signature_numerator=-1,
                                             time_signature_denominator=-1, time_signature_enabled=False)]


def test_a_scene_gets_its_own_tempo_and_time_signature_and_can_be_cleared(script_module):
    song = SceneSong()
    inst = make_inst(script_module, song)
    r = ok(run(inst, "set_scene_tempo", scene_index=0, tempo=96.0, numerator=6, denominator=8, expected_name="Verse"))
    assert (r["tempo"], r["tempo_enabled"], r["time_signature"], r["time_signature_enabled"]) == (96.0, True, [6, 8], True)
    r = ok(run(inst, "set_scene_tempo", scene_index=0, clear=True))
    assert r["tempo_enabled"] is False and r["time_signature_enabled"] is False


@pytest.mark.parametrize("kwargs,needle", [
    (dict(), "Give tempo"), (dict(tempo=10), "between 20 and 999"), (dict(tempo=1000), "between 20 and 999"),
    (dict(numerator=4), "both numerator and denominator"), (dict(numerator=4, denominator=3), "denominator 1, 2, 4"),
    (dict(tempo=100, expected_name="Other"), "not 'Other'"),
])
def test_bad_scene_tempo_changes_nothing(script_module, kwargs, needle):
    song = SceneSong()
    assert needle in err(run(make_inst(script_module, song), "set_scene_tempo", scene_index=0, **kwargs))
    assert song.scenes[0].tempo_enabled is False and song.scenes[0].tempo == -1.0
    assert "out of range" in err(run(make_inst(script_module, SceneSong()), "set_scene_tempo", scene_index=4, tempo=100))


# ------------------------------------------------------------------- grooves

class Groove(object):
    def __init__(self, name):
        self.name, self.timing_amount, self.quantization_amount = name, 100.0, 0.0
        self.random_amount, self.velocity_amount = 0.0, 0.0


class GrooveSong(object):
    def __init__(self):
        self.groove_pool = types.SimpleNamespace(grooves=[Groove("Swing 16ths 66"), Groove("MPC 8")])
        self.groove_amount, self.swing_amount = 0.0, 0.0
        clip = types.SimpleNamespace(name="Riff", has_groove=False, groove=None)
        self.tracks = [types.SimpleNamespace(name="Keys", clip_slots=[types.SimpleNamespace(has_clip=True, clip=clip)])]


def test_grooves_are_listed_changed_and_given_to_a_clip(script_module):
    song = GrooveSong()
    inst = make_inst(script_module, song)
    assert [g["name"] for g in ok(run(inst, "get_grooves"))["grooves"]] == ["Swing 16ths 66", "MPC 8"]
    r = ok(run(inst, "set_groove", groove_index=1, timing_amount=60.0, random_amount=5.0, groove_amount=0.8))
    assert r["grooves"][1]["timing_amount"] == 60.0 and r["grooves"][1]["random_amount"] == 5.0 and r["groove_amount"] == 0.8
    class LiveClip(object):
        name = "Riff"
        _g = None

        @property
        def groove(self):
            return self._g

        @groove.setter
        def groove(self, v):
            self._g = v

        @property
        def has_groove(self):
            return self._g is not None

    song.tracks[0].clip_slots[0].clip = LiveClip()
    r = ok(run(inst, "set_clip_groove", track_index=0, clip_index=0, groove_index=0))
    assert r["groove"] == "Swing 16ths 66" and r["groove_before"] is None
    assert "cannot take a groove away" in err(run(inst, "set_clip_groove", track_index=0, clip_index=0))
    assert song.tracks[0].clip_slots[0].clip.groove is not None


@pytest.mark.parametrize("kwargs,needle", [
    (dict(), "Give groove_amount"), (dict(groove_amount=5), "0 to 1.3"),
    (dict(timing_amount=10.0), "groove_index required"), (dict(groove_index=9, timing_amount=1.0), "groove_index required"),
])
def test_bad_groove_changes_are_refused(script_module, kwargs, needle):
    song = GrooveSong()
    assert needle in err(run(make_inst(script_module, song), "set_groove", **kwargs))
    assert song.groove_amount == 0.0


# --------------------------------------------------------------- warp markers

class Marker(object):
    def __init__(self, sample_time, beat_time):
        self.sample_time, self.beat_time = sample_time, beat_time


class AudioClip(object):
    is_audio_clip, name, warping = True, "take", True

    def __init__(self):
        self.warp_markers = [Marker(0.0, 0.0), Marker(2.0, 4.0)]

    def add_warp_marker(self, m):
        self.warp_markers = sorted(self.warp_markers + [m], key=lambda x: x.beat_time)

    def move_warp_marker(self, beat, distance):
        for m in self.warp_markers:
            if abs(m.beat_time - beat) < 1e-3:
                m.beat_time += distance
                return
        raise RuntimeError("The specified warp marker doesn't exist")

    def remove_warp_marker(self, beat):
        self.warp_markers = [m for m in self.warp_markers if abs(m.beat_time - beat) > 1e-3]


def warp_inst(script_module, clip=None):
    clip = clip or AudioClip()
    song = types.SimpleNamespace(tracks=[types.SimpleNamespace(name="Gtr", clip_slots=[types.SimpleNamespace(has_clip=True, clip=clip)])])
    return clip, make_inst(script_module, song)


def test_warp_markers_are_added_moved_and_removed(script_module):
    clip, inst = warp_inst(script_module)
    r = ok(run(inst, "edit_warp_marker", track_index=0, action="add", beat_time=1.0, seconds=0.6))
    assert {"beat_time": 1.0, "seconds": 0.6} in r["markers"] and len(r["markers_before"]) == 2
    r = ok(run(inst, "edit_warp_marker", track_index=0, action="move", beat_time=1.0, distance=0.25))
    assert {"beat_time": 1.25, "seconds": 0.6} in r["markers"]
    r = ok(run(inst, "edit_warp_marker", track_index=0, action="remove", beat_time=1.25))
    assert [m["beat_time"] for m in r["markers"]] == [0.0, 4.0]


@pytest.mark.parametrize("kwargs,needle", [
    (dict(action="stretch", beat_time=1.0), "action must be"),
    (dict(action="add", beat_time=1.0), "seconds must be a number"),
    (dict(action="move", beat_time=3.0, distance=0.1), "No warp marker at beat 3.0"),
    (dict(action="remove", beat_time=3.0), "No warp marker at beat 3.0"),
    (dict(action="move", beat_time=0.0), "distance must be a number"),
])
def test_bad_warp_edits_change_nothing(script_module, kwargs, needle):
    clip, inst = warp_inst(script_module)
    assert needle in err(run(inst, "edit_warp_marker", track_index=0, **kwargs))
    assert len(clip.warp_markers) == 2


def test_warp_markers_need_a_warped_audio_clip(script_module):
    clip = AudioClip()
    clip.warping = False
    _, inst = warp_inst(script_module, clip)
    assert "not warped" in err(run(inst, "edit_warp_marker", track_index=0, action="remove", beat_time=0.0))
    midi = types.SimpleNamespace(is_audio_clip=False, name="m")
    _, inst2 = warp_inst(script_module, midi)
    assert "belong to audio clips" in err(run(inst2, "edit_warp_marker", track_index=0, action="remove", beat_time=0.0))


# ------------------------------------------------------- loop, region, copies

class MidiClip(object):
    is_midi_clip = True
    name = "Riff"

    def __init__(self):
        self.length = self.loop_end = 4.0
        self.notes = [FakeNote(1, 60, 0.0, 1.0), FakeNote(2, 64, 2.0, 1.0)]
        self.regions = []

    def get_notes_extended(self, a, b, t, span):
        return NoteVector(n for n in self.notes if t <= n.start_time < t + span)

    def duplicate_loop(self):
        self.notes += [FakeNote(len(self.notes) + i + 1, n.pitch, n.start_time + self.length, n.duration) for i, n in enumerate(list(self.notes))]
        self.length = self.loop_end = self.length * 2

    def duplicate_region(self, start, length, dest, pitch, transposition):
        self.regions.append((start, length, dest, pitch, transposition))
        for n in list(self.notes):
            if start <= n.start_time < start + length and pitch in (-1, n.pitch):
                self.notes.append(FakeNote(len(self.notes) + 1, n.pitch + transposition, dest + n.start_time - start, n.duration))


def midi_inst(script_module, clip=None):
    clip = clip or MidiClip()
    song = types.SimpleNamespace(tracks=[types.SimpleNamespace(name="Keys", clip_slots=[types.SimpleNamespace(has_clip=True, clip=clip)])])
    return clip, make_inst(script_module, song)


def test_a_clip_loop_is_doubled_with_its_notes(script_module):
    clip, inst = midi_inst(script_module)
    r = ok(run(inst, "duplicate_clip_loop", track_index=0))
    assert r["before"]["notes"] == 2 and r["after"]["notes"] == 4 and r["after"]["loop_end"] == 8.0


def test_a_note_region_is_copied_transposed_inside_the_clip(script_module):
    clip, inst = midi_inst(script_module)
    r = ok(run(inst, "copy_note_region", track_index=0, region_start=0.0, region_length=2.0, destination_time=3.0, transposition=7))
    assert clip.regions == [(0.0, 2.0, 3.0, -1, 7)] and r["copied"] == 1 and (67, 3.0) in [(n.pitch, n.start_time) for n in clip.notes]


@pytest.mark.parametrize("kwargs,needle", [
    (dict(region_start=0.0, region_length=9.0, destination_time=1.0), "inside the clip"),
    (dict(region_start=0.0, region_length=2.0, destination_time=4.0), "would never play"),
    (dict(region_start=-1.0, region_length=2.0, destination_time=1.0), "inside the clip"),
    (dict(region_start=0.0, region_length=2.0, destination_time=1.0, pitch=200), "pitch must be"),
    (dict(region_start=0.0, region_length=2.0, destination_time=1.0, transposition=1.5), "integer number of semitones"),
])
def test_a_bad_region_copy_changes_nothing(script_module, kwargs, needle):
    clip, inst = midi_inst(script_module)
    assert needle in err(run(inst, "copy_note_region", track_index=0, **kwargs))
    assert clip.regions == [] and len(clip.notes) == 2


class Slot(object):
    def __init__(self, clip=None):
        self.clip = clip
        self.copied = []

    @property
    def has_clip(self):
        return self.clip is not None

    def duplicate_clip_to(self, other):
        other.clip = types.SimpleNamespace(name=self.clip.name)

    def delete_clip(self):
        self.clip = None


def test_a_session_clip_is_copied_to_a_free_slot_and_overwrite_is_explicit(script_module):
    src = Slot(types.SimpleNamespace(name="Riff"))
    tracks = [types.SimpleNamespace(name="A", clip_slots=[src, Slot(), Slot(types.SimpleNamespace(name="Old"))]),
              types.SimpleNamespace(name="B", clip_slots=[Slot()])]
    inst = make_inst(script_module, types.SimpleNamespace(tracks=tracks))
    r = ok(run(inst, "copy_clip_to_slot", track_index=0, clip_index=0, to_track_index=1, to_clip_index=0))
    assert r["copied"] is True and r["to"] == "B / slot 0"
    assert "already holds a clip ('Old')" in err(run(inst, "copy_clip_to_slot", track_index=0, clip_index=0, to_track_index=0, to_clip_index=2))
    assert tracks[0].clip_slots[2].clip.name == "Old"
    ok(run(inst, "copy_clip_to_slot", track_index=0, clip_index=0, to_track_index=0, to_clip_index=2, overwrite=True))
    assert tracks[0].clip_slots[2].clip.name == "Riff"
    assert "out of range" in err(run(inst, "copy_clip_to_slot", track_index=0, clip_index=0, to_track_index=0, to_clip_index=9))


# ---------------------------------------------------------- parameter details

def test_quantized_parameters_list_their_choices_and_others_their_default(script_module):
    class P(object):
        def __init__(self, name, quantized, **kw):
            self.name, self.is_quantized, self.value, self.min, self.max = name, quantized, kw.get("value", 0.0), 0.0, 1.0
            self.value_items = kw.get("items", [])
            self._default = kw.get("default")

        @property
        def default_value(self):
            if self._default is None:
                raise RuntimeError("There is no default value available for this type of parameter")
            return self._default

    dev = types.SimpleNamespace(name="Compressor", class_name="Compressor2", can_have_chains=False, can_have_drum_pads=False,
                                parameters=[P("Model", True, items=["Peak", "RMS", "Expand"]), P("Threshold", False, default=0.85)])
    inst = make_inst(script_module, types.SimpleNamespace())
    info = inst._serialize_device(dev, 0, include_params=True)
    by_name = {p["name"]: p for p in info["parameters"]}
    assert by_name["Model"]["items"] == ["Peak", "RMS", "Expand"] and "default" not in by_name["Model"]
    assert by_name["Threshold"]["default"] == 0.85 and "items" not in by_name["Threshold"]


# -------------------------------------------------------------------- tools

def test_the_tools_forward_and_demand_the_safety_names(conn):
    conn.response = {"ok": True}
    assert "expected_name is required" in call(server.insert_device, None, 0, None, "Reverb")
    call(server.insert_device, None, 0, "Bass", "Reverb", 1)
    assert conn.sent[-1] == ("insert_device", {"track_index": 0, "expected_name": "Bass", "device_name": "Reverb", "index": 1, "track_type": "track"})
    assert "required" in call(server.move_device, None, 0, 0, 1, None, "Amp")
    assert "to_expected_name is required" in call(server.move_device, None, 0, 0, 1, "Bass", "Amp", to_track_index=1)
    call(server.move_device, None, 0, 0, 1, "Bass", "Amp", to_track_index=1, to_expected_name="Keys")
    assert conn.sent[-1][1]["to_track_index"] == 1
    assert "required" in call(server.duplicate_device, None, 0, 0, "Bass", None)
    call(server.set_song_scale, None, "3", "Minor")
    assert conn.sent[-1] == ("set_song_scale", {"root_note": 3, "scale_name": "Minor"})
    call(server.set_song_scale, None, "F#")
    assert conn.sent[-1][1]["root_note"] == "F#"
    call(server.set_scene_tempo, None, 0, 96.0, 6, 8)
    assert conn.sent[-1][1] == {"scene_index": 0, "clear": False, "tempo": 96.0, "numerator": 6, "denominator": 8}
    call(server.set_clip_groove, None, 0, 1)
    assert conn.sent[-1][1] == {"track_index": 0, "clip_index": 0, "groove_index": 1}
    call(server.edit_warp_marker, None, 0, "add", 1.0, seconds=0.6)
    assert conn.sent[-1][1]["seconds"] == 0.6
    call(server.copy_note_region, None, 0, 0.0, 2.0, 3.0, transposition=7)
    assert conn.sent[-1][1]["transposition"] == 7 and conn.sent[-1][1]["pitch"] == -1
    call(server.copy_clip_to_slot, None, 0, 0, 1, 0, True)
    assert conn.sent[-1][1]["overwrite"] is True
    call(server.duplicate_clip_loop, None, 0, clip_start_time=16.0)
    assert conn.sent[-1][1]["clip_start_time"] == 16.0
    for name in ("insert_device", "move_device", "duplicate_device", "set_song_scale", "set_scene_tempo", "set_groove",
                 "set_clip_groove", "edit_warp_marker", "duplicate_clip_loop", "copy_note_region", "copy_clip_to_slot"):
        assert name in MODIFYING_TOOLS
    call(server.get_song_scale, None); call(server.get_grooves, None)
    assert [c[0] for c in conn.sent[-2:]] == ["get_song_scale", "get_grooves"]
