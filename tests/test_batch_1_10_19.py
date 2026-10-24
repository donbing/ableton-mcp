"""1.10.19: transport options, delete a return, drum pads, macro variations, browser preview, plug-in window.

The fakes follow what Live 12.4 Lite did (2026-10-24): punch and overdub flags apply on the NEXT tick
(a read in the same call still shows the old value), an empty drum pad cannot be muted, store_variation
adds a variation and recall needs selected_variation_index set first, Browser.preview_item plays an item.
"""
import sys
import types

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class FakeLive(types.ModuleType):
    def __init__(self):
        types.ModuleType.__init__(self, "Live")
        self.Song = types.SimpleNamespace(
            Quantization=types.SimpleNamespace(q_no_q=0, q_8_bars=1, q_4_bars=2, q_2_bars=3, q_bar=4, q_half=5,
                                               q_half_triplet=6, q_quarter=7, q_quarter_triplet=8, q_eight=9,
                                               q_eight_triplet=10, q_sixtenth=11, q_sixtenth_triplet=12,
                                               q_thirtytwoth=13),
            RecordingQuantization=types.SimpleNamespace(
                rec_q_no_q=0, rec_q_quarter=1, rec_q_eight=2, rec_q_eight_triplet=3, rec_q_eight_eight_triplet=4,
                rec_q_sixtenth=5, rec_q_sixtenth_triplet=6, rec_q_sixtenth_sixtenth_triplet=7,
                rec_q_thirtysecond=8))


@pytest.fixture(autouse=True)
def live(monkeypatch):
    fake = FakeLive()
    monkeypatch.setitem(sys.modules, "Live", fake)
    return fake


class Param(object):
    def __init__(self, name, value=0.0):
        self.name, self.value = name, value


class Chain(object):
    def __init__(self, *names):
        self.devices = [types.SimpleNamespace(name=n) for n in names]


class Pad(object):
    def __init__(self, note, name, chains=()):
        self.note, self.name, self.chains = note, name, list(chains)
        self.mute = self.solo = False


class DrumRack(object):
    name, class_name, can_have_drum_pads, can_have_chains = "808 Kit", "DrumGroupDevice", True, True

    def __init__(self):
        self.drum_pads = [Pad(36, "Kick", [Chain("Kick")]), Pad(37, "Rim", [Chain("Rim")]), Pad(38, "Empty")]
        self.visible_drum_pads = self.drum_pads
        self.parameters = []
        self.variation_count, self.selected_variation_index, self.has_macro_mappings = 0, -1, False
        self.recalled = self.randomized = 0
        self.macro = Param("Macro 1", 0.0)
        self.parameters = [self.macro]

    def store_variation(self):
        self.variation_count += 1

    def recall_selected_variation(self):
        self.recalled += 1

    def delete_selected_variation(self):
        self.variation_count -= 1
        self.selected_variation_index = -1

    def randomize_macros(self):
        self.randomized += 1
        self.macro.value = 0.42


class Plugin(object):
    name, class_name = "AmpliTube 5", "AuPluginDevice"

    def __init__(self):
        self.is_editor_open = False
        self.parameters = []


class Plain(object):
    name, class_name, parameters = "Tuner", "Tuner", []


def mixer(*sends):
    return types.SimpleNamespace(sends=[Param("Send", v) for v in sends])


class Track(object):
    def __init__(self, name, devices=(), sends=(0.0, 0.0)):
        self.name, self.devices, self.mixer_device = name, list(devices), mixer(*sends)
        self.clip_slots = []


class Song(object):
    def __init__(self):
        self.drums, self.plugin = DrumRack(), Plugin()
        self.tracks = [Track("Drums", [self.drums]), Track("Guitar", [self.plugin, Plain()], sends=(0.5, 0.0))]
        self.return_tracks = [Track("A-Reverb", [types.SimpleNamespace(name="Reverb")]),
                              Track("B-Delay", [types.SimpleNamespace(name="Delay")])]
        self.punch_in = self.punch_out = self.arrangement_overdub = self.loop = False
        self.clip_trigger_quantization, self.midi_recording_quantization = 4, 0
        self.count_in_duration = 1
        self._pending = {}
        self.deleted = []

    def tick(self):
        for key, value in self._pending.items():
            object.__setattr__(self, key, value)
        self._pending = {}

    def delete_return_track(self, index):
        self.deleted.append(self.return_tracks.pop(index).name)


class TickedSong(Song):
    """punch_in, punch_out and arrangement_overdub show the new value only after a tick."""

    def __setattr__(self, key, value):
        if key in ("punch_in", "punch_out", "arrangement_overdub") and "_pending" in self.__dict__:
            self._pending[key] = value
        else:
            object.__setattr__(self, key, value)


@pytest.fixture
def song():
    return TickedSong()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    obj = make_inst(script_module, song)
    monkeypatch.setattr(script_module.time, "sleep", lambda s: song.tick())
    obj.previews, obj.stopped = [], []
    items = {"query:Drums#Kick": types.SimpleNamespace(name="Kick.wav")}
    browser = types.SimpleNamespace(preview_item=lambda item: obj.previews.append(item.name),
                                    stop_preview=lambda: obj.stopped.append(True))
    obj.application = lambda: types.SimpleNamespace(browser=browser)
    obj._find_browser_item_by_uri = lambda b, uri: items.get(uri)
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


# --------------------------------------------------------------------------- transport

def test_options_are_read_with_no_arguments(inst):
    r = ok(run(inst, "set_transport_options"))
    assert r["after"] == r["before"] and r["after"]["clip_trigger_quantization"] == "bar"
    assert r["after"]["midi_recording_quantization"] == "none" and r["after"]["punch_in"] is False
    assert "not_applied" not in r


def test_flags_that_apply_on_the_next_tick_are_waited_for_and_read_back(inst, song):
    r = ok(run(inst, "set_transport_options", punch_in=True, punch_out=True, arrangement_overdub=True,
               clip_trigger_quantization="2 bars", midi_recording_quantization="eighth"))
    assert r["before"]["punch_in"] is False and r["after"]["punch_in"] is True
    assert r["after"]["clip_trigger_quantization"] == "2 bars" and r["after"]["midi_recording_quantization"] == "eighth"
    assert r["not_applied"] == [] and song.clip_trigger_quantization == 3 and song.midi_recording_quantization == 2


def test_a_flag_that_does_not_land_is_reported(inst, song, monkeypatch):
    monkeypatch.setattr(TickedSong, "tick", lambda self: None)
    r = ok(run(inst, "set_transport_options", punch_in=True))
    assert r["not_applied"] == ["punch_in"]


def test_a_bad_quantization_name_changes_nothing(inst, song):
    msg = err(run(inst, "set_transport_options", punch_in=True, clip_trigger_quantization="3 bars"))
    assert "clip_trigger_quantization must be one of" in msg
    song.tick()
    assert song.punch_in is False
    assert "midi_recording_quantization must be" in err(run(inst, "set_transport_options", midi_recording_quantization="x"))
    assert "true or false" in err(run(inst, "set_transport_options", punch_out="yes"))


# --------------------------------------------------------------------------- returns

def test_deleting_a_return_previews_then_deletes_and_checks_the_name(inst, song):
    r = ok(run(inst, "delete_return_track", index=1, expected_name="B-Delay"))
    assert r["applied"] is False and r["devices"] == ["Delay"] and song.deleted == []
    assert "not 'A-Reverb'" in err(run(inst, "delete_return_track", index=1, expected_name="A-Reverb", confirm=True))
    assert "expected_name" in err(run(inst, "delete_return_track", index=1))
    assert "out of range" in err(run(inst, "delete_return_track", index=5, expected_name="x", confirm=True))
    r = ok(run(inst, "delete_return_track", index=1, expected_name="B-Delay", confirm=True))
    assert r["applied"] is True and song.deleted == ["B-Delay"] and [t["name"] for t in r["return_tracks_after"]] == ["A-Reverb"]


def test_the_preview_counts_tracks_that_send_to_it(inst):
    assert ok(run(inst, "delete_return_track", index=0, expected_name="A-Reverb"))["tracks_sending_to_it"] == 1
    assert ok(run(inst, "delete_return_track", index=1, expected_name="B-Delay"))["tracks_sending_to_it"] == 0


# --------------------------------------------------------------------------- drum pads

def test_only_pads_with_a_sound_are_listed_unless_asked(inst):
    r = ok(run(inst, "get_drum_pads", track_index=0, device_index=0))
    assert [p["note"] for p in r["pads"]] == [36, 37] and r["pad_count_with_sound"] == 2
    assert r["pads"][0]["devices"] == ["Kick"]
    assert len(ok(run(inst, "get_drum_pads", track_index=0, device_index=0, include_empty=True))["pads"]) == 3
    assert "not a Drum Rack" in err(run(inst, "get_drum_pads", track_index=1, device_index=0))


PAD = dict(track_index=0, device_index=0, expected_name="Drums", expected_device_name="808 Kit")


def test_a_pad_is_muted_and_soloed_by_note(inst, song):
    r = ok(run(inst, "set_drum_pad", note=36, mute=True, **PAD))
    assert r["before"]["mute"] is False and r["after"]["mute"] is True and song.drums.drum_pads[0].mute is True
    r = ok(run(inst, "set_drum_pad", note=37, solo=True, **PAD))
    assert r["after"]["solo"] is True


def test_drum_pad_refusals(inst):
    assert "no sound" in err(run(inst, "set_drum_pad", note=38, mute=True, **PAD))
    assert "no pad for MIDI note 99" in err(run(inst, "set_drum_pad", note=99, mute=True, **PAD))
    assert "Give mute and/or solo" in err(run(inst, "set_drum_pad", note=36, **PAD))
    assert "true or false" in err(run(inst, "set_drum_pad", note=36, mute="yes", **PAD))
    assert "not 'Wrong'" in err(run(inst, "set_drum_pad", note=36, mute=True, **dict(PAD, expected_name="Wrong")))
    assert "not a Drum Rack" in err(run(inst, "set_drum_pad", track_index=1, device_index=1, expected_name="Guitar",
                                        expected_device_name="Tuner", note=36, mute=True))


# --------------------------------------------------------------------- macro variations

RACK = dict(track_index=0, device_index=0, expected_name="Drums", expected_device_name="808 Kit")


def test_status_stores_and_warns_when_no_macro_is_mapped(inst, song):
    assert ok(run(inst, "rack_variations", **RACK))["before"]["variation_count"] == 0
    r = ok(run(inst, "rack_variations", action="store", **RACK))
    assert r["after"]["variation_count"] == 1 and "No macro is mapped" in r["warning"]
    song.drums.has_macro_mappings = True
    assert "warning" not in ok(run(inst, "rack_variations", action="store", **RACK))


def test_recall_selects_before_recalling_and_checks_the_index(inst, song):
    song.drums.variation_count = 2
    r = ok(run(inst, "rack_variations", action="recall", index=1, **RACK))
    assert song.drums.selected_variation_index == 1 and song.drums.recalled == 1 and r["applied"] is True
    assert "index must be a variation 0..1" in err(run(inst, "rack_variations", action="recall", index=2, **RACK))
    assert "index must be" in err(run(inst, "rack_variations", action="recall", **RACK))


def test_delete_and_randomize_preview_until_confirmed(inst, song):
    song.drums.variation_count = 1
    r = ok(run(inst, "rack_variations", action="delete", index=0, **RACK))
    assert r["applied"] is False and r["dry_run"] is True and song.drums.variation_count == 1
    ok(run(inst, "rack_variations", action="delete", index=0, confirm=True, **RACK))
    assert song.drums.variation_count == 0
    assert ok(run(inst, "rack_variations", action="randomize", **RACK))["applied"] is False and song.drums.randomized == 0
    r = ok(run(inst, "rack_variations", action="randomize", confirm=True, **RACK))
    assert song.drums.randomized == 1 and r["after"]["macros"][0]["value"] == 0.42


def test_variation_refusals(inst):
    assert "action must be" in err(run(inst, "rack_variations", action="x", **RACK))
    assert "not a rack with macro variations" in err(run(inst, "rack_variations", track_index=1, device_index=1,
                                                         expected_name="Guitar", expected_device_name="Tuner"))


# ----------------------------------------------------------------- preview, plug-in window

def test_a_browser_item_is_previewed_and_stopped(inst):
    assert ok(run(inst, "preview_browser_item", uri="query:Drums#Kick"))["previewing"] == "Kick.wav"
    assert inst.previews == ["Kick.wav"]
    assert ok(run(inst, "stop_browser_preview")) == {"stopped": True} and inst.stopped == [True]
    assert "No browser item" in err(run(inst, "preview_browser_item", uri="query:Nope"))
    assert "uri is required" in err(run(inst, "preview_browser_item", uri=""))


PLUG = dict(track_index=1, device_index=0, expected_name="Guitar", expected_device_name="AmpliTube 5")


def test_a_plugin_window_opens_and_closes(inst, song):
    r = ok(run(inst, "set_plugin_window", open=True, **PLUG))
    assert r["was_open"] is False and r["open"] is True and song.plugin.is_editor_open is True
    assert ok(run(inst, "set_plugin_window", open=False, **PLUG))["open"] is False


def test_only_a_plugin_has_a_window(inst):
    assert "not a VST/AU plug-in" in err(run(inst, "set_plugin_window", track_index=1, device_index=1,
                                              expected_name="Guitar", expected_device_name="Tuner", open=True))
    assert "true or false" in err(run(inst, "set_plugin_window", open="yes", **PLUG))
    assert "not 'Wrong'" in err(run(inst, "set_plugin_window", open=True, **dict(PLUG, expected_name="Wrong")))


# ------------------------------------------------------------------------------ tools

def test_the_tools_forward_their_arguments(conn):
    call(server.set_transport_options, None, True, None, False, "bar", "eighth")
    assert conn.sent[-1] == ("set_transport_options", {"punch_in": True, "arrangement_overdub": False,
                                                       "clip_trigger_quantization": "bar",
                                                       "midi_recording_quantization": "eighth"})
    call(server.set_transport_options, None)
    assert conn.sent[-1] == ("set_transport_options", {})
    assert "NOT DELETED" in call(server.delete_return_track, None, 1, "B-Delay")
    assert conn.sent[-1] == ("delete_return_track", {"index": 1, "expected_name": "B-Delay", "confirm": False})
    call(server.get_drum_pads, None, 0, 1, "track", True)
    assert conn.sent[-1][1]["include_empty"] is True
    call(server.set_drum_pad, None, 0, 1, "Drums", "808 Kit", 36, True)
    assert conn.sent[-1] == ("set_drum_pad", {"track_index": 0, "device_index": 1, "expected_name": "Drums",
                                              "expected_device_name": "808 Kit", "note": 36, "track_type": "track",
                                              "mute": True})
    call(server.rack_variations, None, 0, 1, "Drums", "808 Kit", "recall", 2)
    assert conn.sent[-1][1]["index"] == 2 and conn.sent[-1][1]["action"] == "recall"
    call(server.preview_browser_item, None, "query:Drums#Kick")
    assert conn.sent[-1] == ("preview_browser_item", {"uri": "query:Drums#Kick"})
    call(server.stop_browser_preview, None)
    call(server.set_plugin_window, None, 1, 0, "Guitar", "AmpliTube 5", True)
    assert conn.sent[-1][1]["open"] is True


def test_the_names_are_required_and_modifying_tools_are_listed(conn):
    assert "required" in call(server.delete_return_track, None, 0, None)
    assert "required" in call(server.set_drum_pad, None, 0, 0, None, "x", 36)
    assert "required" in call(server.rack_variations, None, 0, 0, "x", None)
    assert "required" in call(server.set_plugin_window, None, 0, 0, None, "x", True)
    for name in ("set_transport_options", "delete_return_track", "set_drum_pad", "rack_variations"):
        assert name in MODIFYING_TOOLS
