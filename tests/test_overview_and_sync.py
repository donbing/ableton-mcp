"""get_tracks_overview and check_arrangement_sync (adapted from upstream #110)."""
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Param(object):
    def __init__(self, value, text):
        self.value, self._text = value, text

    def str_for_value(self, v):
        return self._text


class Clip(object):
    def __init__(self, start, end, name="c"):
        self.start_time, self.end_time, self.name = float(start), float(end), name


class Track(object):
    def __init__(self, name, midi=False, foldable=False, clips=(), devices=(), group=None):
        self.name, self.has_midi_input, self.is_foldable = name, midi, foldable
        self.devices = [types.SimpleNamespace(name=n) for n in devices]
        self.mixer_device = types.SimpleNamespace(volume=Param(0.85, "0.0 dB"), panning=Param(0.0, "C"))
        self.mute, self.solo, self.arm, self.can_be_armed = False, True, True, not foldable
        self.clip_slots = [types.SimpleNamespace(has_clip=True), types.SimpleNamespace(has_clip=False)]
        self.arrangement_clips = list(clips)
        self.group_track, self.color_index = group, 7


class Song(object):
    def __init__(self, *tracks):
        self.tracks = list(tracks)
        self.return_tracks = [Track("A-Reverb", devices=["Reverb"])]
        self.master_track = Track("Master")
        self.tempo, self.signature_numerator, self.signature_denominator = 120.0, 4, 4
        self.is_playing, self.scenes, self.cue_points = False, [1, 2], [1]


def inst(script_module, *tracks):
    return make_inst(script_module, Song(*tracks))


def run(i, command, **params):
    reply = i._process_command({"type": command, "params": params})
    assert reply["status"] == "success", reply
    return reply["result"]


def test_overview_is_one_compact_read_of_everything(script_module):
    group = Track("Drums", foldable=True)
    i = inst(script_module,
             Track("Bass", clips=[Clip(0, 4)], devices=["EQ", "Compressor"]),
             Track("Keys", midi=True, group=group), group)
    result = run(i, "get_tracks_overview")
    assert result["tempo"] == 120.0 and result["time_signature"] == "4/4"
    assert [t["kind"] for t in result["tracks"]] == ["audio", "midi", "group"]
    bass = result["tracks"][0]
    assert bass["devices"] == ["EQ", "Compressor"] and bass["volume"] == "0.0 dB" and bass["pan"] == "C"
    assert bass["session_clips"] == 1 and bass["arrangement_clips"] == 1 and bass["arm"] is True
    assert result["tracks"][1]["group"] == "Drums" and "arrangement_clips" not in result["tracks"][2]
    assert "arm" not in result["tracks"][2]
    assert result["return_tracks"][0]["devices"] == ["Reverb"]
    assert result["master"]["name"] == "Master" and "mute" not in result["master"]
    assert result["scene_count"] == 2 and result["cue_point_count"] == 1


def test_a_tidy_arrangement_is_in_sync(script_module):
    i = inst(script_module, Track("Bass", clips=[Clip(0, 8), Clip(8, 16)]))
    result = run(i, "check_arrangement_sync")
    assert result["totals"] == {"clips": 2, "off_grid": 0, "overlaps": 0, "gaps": 0, "in_sync": True}


def test_off_grid_overlaps_and_gaps_are_found(script_module):
    i = inst(script_module, Track("Bass", clips=[Clip(0, 6, "a"), Clip(5, 12, "b"), Clip(20, 24, "c")]))
    result = run(i, "check_arrangement_sync")
    totals = result["totals"]
    assert totals["off_grid"] == 2 and totals["overlaps"] == 1 and totals["gaps"] == 1
    assert totals["in_sync"] is False
    problems = result["tracks"][0]["problems"]
    assert {"clip": "a", "edge": "end", "beat": 6.0} in problems["off_grid"]
    assert problems["overlaps"] == [{"clips": ["a", "b"], "overlap_beats": 1.0}]
    assert problems["gaps"] == [{"from": 12.0, "to": 20.0, "length": 8.0}]


def test_the_grid_is_a_parameter_and_group_tracks_are_skipped(script_module):
    i = inst(script_module, Track("Bass", clips=[Clip(0, 1), Clip(1, 2.5)]), Track("G", foldable=True))
    assert run(i, "check_arrangement_sync", grid_beats=1.0)["totals"]["off_grid"] == 1
    assert run(i, "check_arrangement_sync", grid_beats=0.5)["totals"]["off_grid"] == 0
    assert len(run(i, "check_arrangement_sync")["tracks"]) == 1


def test_lists_are_cut_but_counts_are_complete(script_module):
    clips = [Clip(i * 8 + 1, i * 8 + 9) for i in range(30)]
    result = run(inst(script_module, Track("Bass", clips=clips)), "check_arrangement_sync")
    assert result["tracks"][0]["counts"]["off_grid"] == 60
    assert len(result["tracks"][0]["problems"]["off_grid"]) == 20


def test_bad_arguments_are_errors(script_module):
    i = inst(script_module, Track("Bass"))
    out = i._process_command({"type": "check_arrangement_sync", "params": {"grid_beats": 0}})
    assert out["status"] == "error" and "grid_beats must be > 0" in out["message"]


def test_tools_forward_their_arguments(conn):
    conn.response = {"tracks": []}
    call(server.get_tracks_overview, None)
    assert conn.sent[-1] == ("get_tracks_overview", {})
    call(server.check_arrangement_sync, None, 1.0, 0.01)
    assert conn.sent[-1] == ("check_arrangement_sync", {"grid_beats": 1.0, "tolerance": 0.01})
