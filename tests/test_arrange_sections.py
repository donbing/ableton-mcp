"""arrange_sections: a song plan of Session clips into the Arrangement in one call.

The fake Live answers the commands the tool sends. Like Live, a copy replaces what the Arrangement
holds under it on that track (the old clip is cut or removed), and a trim only shortens a clip.
"""
import json

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_scenes import call, conn  # noqa: F401


def slot(name=None, length=16.0):
    return {"has_clip": name is not None, "clip": {"name": name, "length": length} if name else None}


class Arrangement(object):
    def __init__(self):
        # Drums: 4-bar loops in scenes 0-1; Bass: scene 1 only; Pad: an 8-bar clip in scene 0
        self.tracks = [
            {"name": "Drums", "clip_slots": [slot("Beat A"), slot("Beat B"), slot()]},
            {"name": "Bass", "clip_slots": [slot(), slot("Bass"), slot()]},
            {"name": "Pad", "clip_slots": [slot("Pad", 32.0), slot(), slot("Pad short", 8.0)]},
        ]
        self.arrangement = {0: [], 1: [], 2: []}
        self.sent = []

    def send_command(self, command, params=None):
        params = params or {}
        self.sent.append((command, params))
        if command == "get_tracks_overview":
            return {"time_signature": "4/4", "tempo": 120.0,
                    "tracks": [{"index": i, "name": t["name"]} for i, t in enumerate(self.tracks)]}
        if command == "get_session_snapshot":
            return {"tracks": self.tracks}
        if command == "get_arrangement_clips":
            return {"clips": [dict(c) for c in self.arrangement[params["track_index"]]]}
        if command == "duplicate_session_clip_to_arrangement":
            index, start = params["track_index"], params["destination_time"]
            clip = self.tracks[index]["clip_slots"][params["clip_index"]]["clip"]
            end = start + clip["length"]
            kept = []
            for c in self.arrangement[index]:
                if c["end_time"] <= start or c["start_time"] >= end:
                    kept.append(c)
                elif c["start_time"] < start:
                    kept.append(dict(c, end_time=start))
            kept.append({"name": clip["name"], "start_time": start, "end_time": end})
            self.arrangement[index] = sorted(kept, key=lambda c: c["start_time"])
            return {"clip_name": clip["name"]}
        if command == "trim_arrangement_clip":
            assert params["confirm"] is True and params["expected_name"] == self.tracks[params["track_index"]]["name"]
            for c in self.arrangement[params["track_index"]]:
                if c["start_time"] == params["clip_start_time"]:
                    assert params["new_end_time"] <= c["end_time"]
                    c["end_time"] = params["new_end_time"]
                    return {"applied": True}
            raise Exception("no clip starts at %s" % params["clip_start_time"])
        raise AssertionError("unexpected command %s" % command)

    def placed(self, index):
        return [(c["name"], c["start_time"], c["end_time"]) for c in self.arrangement[index]]

    def commands(self):
        return [c for c, _ in self.sent]


@pytest.fixture
def live(conn, monkeypatch):
    fake = Arrangement()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    return fake


PLAN = [{"name": "Intro", "bars": 8, "clips": {"Pad": 0}},
        {"name": "Groove", "bars": 8, "scene": 1, "clips": {"Pad": 2}}]


def test_the_preview_changes_nothing_and_shows_the_plan(live):
    out = call(server.arrange_sections, None, PLAN)
    assert out.startswith("NOT CHANGED (preview only).") and "confirm=true" in out
    assert "duplicate_session_clip_to_arrangement" not in live.commands()
    data = json.loads(out[out.index("{"):out.rindex("}") + 1])
    assert [s["bars"] for s in data["sections"]] == ["1-8", "9-16"]
    assert data["sections"][1]["tracks"] == ["Drums", "Bass", "Pad"]
    assert data["copies"] == 1 + 2 + 2 + 4 and data["copy_starts_by_track"]["Pad"] == [0.0, 32.0, 40.0, 48.0, 56.0]


def test_a_plan_is_laid_out_with_each_clip_repeated_over_its_section(live):
    out = call(server.arrange_sections, None, PLAN, confirm=True)
    assert out.startswith("Placed 9 of 9 copies in 2 sections") and "save the Set on the Push" in out
    assert live.placed(0) == [("Beat B", 32.0, 48.0), ("Beat B", 48.0, 64.0)]
    assert live.placed(2) == [("Pad", 0.0, 32.0)] + [("Pad short", s, s + 8.0) for s in (32.0, 40.0, 48.0, 56.0)]
    assert "trim_arrangement_clip" not in live.commands() and "Not found" not in out


def test_a_copy_past_the_section_end_is_cut_there(live):
    out = call(server.arrange_sections, None, [{"bars": 6, "clips": {"Drums": 0}}], confirm=True)
    # 6 bars = 24 beats: one whole 16-beat loop, then one cut to 8 beats
    assert live.placed(0) == [("Beat A", 0.0, 16.0), ("Beat A", 16.0, 24.0)]
    assert '"cut_at_section_end":1' in out


def test_start_bar_leaves_a_gap_and_tracks_go_by_index(live):
    call(server.arrange_sections, None, [{"start_bar": 5, "bars": 4, "clips": {"0": 1}}], confirm=True)
    assert live.placed(0) == [("Beat B", 16.0, 32.0)]


def test_null_leaves_a_scene_track_out(live):
    call(server.arrange_sections, None, [{"bars": 4, "scene": 1, "clips": {"Bass": None}}], confirm=True)
    assert live.placed(1) == [] and live.placed(0) == [("Beat B", 0.0, 16.0)]


def test_the_preview_lists_what_would_be_replaced(live):
    live.arrangement[0] = [{"name": "Old", "start_time": 8.0, "end_time": 24.0}]
    out = call(server.arrange_sections, None, [{"bars": 4, "clips": {"Drums": 0}}])
    assert '"clip":"Old"' in out


def test_a_cut_copy_that_would_spill_onto_a_later_clip_is_refused(live):
    live.arrangement[2] = [{"name": "Keep me", "start_time": 40.0, "end_time": 48.0}]
    out = call(server.arrange_sections, None, [{"bars": 8, "clips": {"Pad": 0}}, {"bars": 2, "clips": {"Pad": 0}}])
    # the second section is bars 9-10 (beats 32-40): the 32-beat Pad would run to 64, over "Keep me"
    assert out.startswith("Error: 'Pad' slot 0 at beat 32 is 32 beats long and runs to beat 64, over 'Keep me'")
    assert "duplicate_session_clip_to_arrangement" not in live.commands()


@pytest.mark.parametrize("plan, expected", [
    ([], "sections must be a list of at least one section"),
    ([{"clips": {"Drums": 0}}], "'section 1' needs bars"),
    ([{"bars": 4}], "'section 1' has no clips"),
    ([{"bars": 4, "clips": {"Vox": 0}}], "no track is named 'Vox'"),
    ([{"bars": 4, "clips": {"7": 0}}], "track 7 is out of range"),
    ([{"name": "Drop", "bars": 4, "clips": {"Bass": 0}}], "'Drop': 'Bass' has no Session clip in slot 0"),
    ([{"bars": 4, "start_bar": 0, "clips": {"Drums": 0}}], "starts at bar 0; bar 1 is the start"),
    ([{"bars": 2000, "clips": {"Drums": 0}}], "the plan makes 500 copies; at most 400"),
])
def test_bad_plans_are_refused_before_anything_changes(live, plan, expected):
    out = call(server.arrange_sections, None, plan, confirm=True)
    assert out.startswith("Error") and expected in out
    assert "duplicate_session_clip_to_arrangement" not in live.commands()


def test_arrange_sections_is_a_modifying_tool():
    assert "arrange_sections" in MODIFYING_TOOLS
