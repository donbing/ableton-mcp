"""render_song: Arrangement-record the whole mix onto the scratch track, measure the WAV, delete the take.

The fake Live answers the commands the tool sends and plays in time: while it plays, the song time moves
with the test clock (120 bpm, 2 beats a second), Arrangement recording stops itself at its end_time, and
the take is an Arrangement clip on the scratch track with a file.
"""
import pytest

import MCP_Server.listen as L
import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_scenes import call, conn  # noqa: F401

WAV = "/data/Music/Ableton/Sets/Test Project/Samples/Recorded/Listen 0001.wav"


class Live(object):
    def __init__(self):
        self.t = 1000.0
        self.tracks = [{"index": 0, "name": "Drums", "kind": "midi", "arm": True, "monitoring": "auto"},
                       {"index": 1, "name": "Vox", "kind": "audio", "arm": False, "monitoring": "in"},
                       {"index": 2, "name": "Listen", "kind": "audio", "arm": False, "monitoring": "off"}]
        self.input = {"type": "Resampling", "channel": "", "available_types": ["Ext. In", "Resampling", "Main"],
                      "available_channels": ["Post FX", "Post Mixer"]}
        self.main, self.song_length, self.loop = 0.85, 64.0, False
        self.playing, self.time, self.played_from, self.started = False, 130.0, 130.0, self.t
        self.recording, self.record_end, self.stop_at = False, None, None
        self.arrangement = []   # the scratch track's clips
        self.scratch = 2
        self.sent = []

    def tick(self):
        if self.playing:
            self.time = self.played_from + (self.t - self.started) * 2.0
            if self.stop_at is not None and self.time >= self.stop_at:
                self.playing = False
            if self.recording and self.time >= self.record_end:
                self.recording = False
                self.arrangement[-1]["end_time"] = self.record_end

    def send_command(self, command, params=None):
        params = params or {}
        self.sent.append((command, params))
        self.tick()
        if command == "get_tracks_overview":
            return {"tempo": 120.0, "time_signature": "4/4", "tracks": [dict(t) for t in self.tracks]}
        if command == "get_track_routing":
            return {"input": dict(self.input)}
        if command == "set_track_routing":
            if params.get("routing_type"):
                self.input["type"] = params["routing_type"]
            if params.get("routing_channel"):
                self.input["channel"] = params["routing_channel"]
            return {"after": dict(self.input)}
        if command == "get_session_info":
            return {"is_playing": self.playing, "current_song_time": self.time, "song_length": self.song_length,
                    "loop": self.loop}
        if command == "get_track_info":
            return {"volume": self.main}
        if command == "set_track_volume":
            self.main = params["value"]
            return {"display": "%.2f" % params["value"]}
        if command == "set_track_arm":
            self.tracks[params["track_index"]]["arm"] = params["enabled"]
            return {}
        if command == "start_arrangement_record":
            armed = [t for t in self.tracks if t["arm"]]
            self.playing, self.played_from, self.started = True, params["start_time"], self.t
            self.time, self.recording, self.record_end = params["start_time"], True, params["end_time"]
            self.arrangement.append({"name": "Listen", "start_time": params["start_time"],
                                     "end_time": params["start_time"] + 1.0})
            return {"armed_tracks": [{"name": t["name"]} for t in armed], "warnings": []}
        if command == "stop_recording":
            if self.recording:
                self.recording = False
                self.arrangement[-1]["end_time"] = self.time
            if params.get("stop_transport"):
                self.playing = False
            return {}
        if command == "get_arrangement_clips":
            if params["track_index"] != self.scratch:
                return {"clips": []}
            return {"clips": [dict(c) for c in self.arrangement]}
        if command == "get_audio_clip_info":
            assert params["arrangement"] is True
            return {"file_path": WAV}
        if command == "delete_arrangement_clips":
            assert params["confirm"] is True and params["expected_name"] == self.tracks[self.scratch]["name"]
            self.arrangement = [c for c in self.arrangement
                                if not params["start_time"] <= c["start_time"] < params["end_time"]]
            return {}
        if command == "create_audio_track":
            self.scratch = len(self.tracks)
            self.tracks.append({"index": self.scratch, "name": "4-Audio", "kind": "audio", "arm": False,
                                "monitoring": "auto"})
            return {"index": self.scratch, "name": "4-Audio"}
        if command == "set_track_name":
            self.tracks[params["track_index"]]["name"] = params["name"]
            return {}
        if command == "set_track_monitoring":
            self.tracks[params["track_index"]]["monitoring"] = params["state"]
            return {}
        if command == "delete_track":
            assert params["dry_run"] is False and self.tracks[params["track_index"]]["name"] == params["expected_name"]
            del self.tracks[params["track_index"]]
            return {}
        if command == "set_current_song_time":
            self.time = params["time"]
            return {}
        raise AssertionError("unexpected command %s" % command)

    def commands(self):
        return [c for c, _ in self.sent]


@pytest.fixture
def live(conn, monkeypatch):
    fake = Live()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(server, "_listen_now", lambda: fake.t)
    monkeypatch.setattr(server, "_listen_sleep", lambda s: setattr(fake, "t", fake.t + s))
    monkeypatch.setattr(server, "_wait_for_file", lambda path, timeout=3.0: None)
    monkeypatch.setattr(L, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    fake.measured = []
    monkeypatch.setattr(L, "analyze_file", lambda path, spb=None, bars_per_row=None, silence_db=-50.0:
                        fake.measured.append((path, spb)) or {"integrated_lufs": -14.2, "duration": 32.0})
    monkeypatch.setattr(L, "format_report", lambda result: "Loudness %s LUFS" % result["integrated_lufs"])
    return fake


SCRATCH = dict(scratch_track_index=2, expected_name="Listen")


def test_the_preview_records_nothing(live):
    out = call(server.render_song, None, **SCRATCH)
    assert out.startswith("NOT RECORDED (preview only). This would record bars 1-16 (beats 0-64, 32 s at 120.0 bpm "
                          "4/4) of the Arrangement onto 'Listen'")
    assert "disarms track(s) 0" in out and "Main before its fader" in out
    assert "start_arrangement_record" not in live.commands() and live.main == 0.85


def test_a_render_records_the_song_measures_it_and_deletes_the_take(live):
    out = call(server.render_song, None, confirm=True, **SCRATCH)
    assert out.startswith("Rendered bars 1-16") and "File: %s" % WAV in out and "Loudness -14.2 LUFS" in out
    assert live.measured == [(WAV, 2.0)]
    # the take is gone, everything is put back, the playhead too
    assert live.arrangement == [] and live.playing is False and live.time == 130.0
    assert live.main == 0.85 and live.input["type"] == "Resampling"
    assert [t["arm"] for t in live.tracks] == [True, False, False]
    # only the scratch track was armed for the take, which took Main before its fader
    rec = live.commands().index("start_arrangement_record")
    arms = [p for c, p in live.sent[:rec] if c == "set_track_arm"]
    assert arms == [{"track_index": 0, "enabled": False, "track_type": "track"},
                    {"track_index": 2, "enabled": True, "track_type": "track", "expected_name": "Listen"}]
    assert "took its input from 'Main' (Post FX)" in out and "re-armed track(s) 0" in out
    assert "Note:" not in out


def test_bars_of_the_song(live):
    out = call(server.render_song, None, start_bar=5, end_bar=8, confirm=True, **SCRATCH)
    assert ("start_arrangement_record", {"start_time": 16.0, "end_time": 32.0, "confirm": True}) in live.sent
    assert "The table's bar 1 is bar 5 of the song." in out


def test_a_render_stopped_on_the_push_measures_what_came(live):
    live.stop_at = 40.0
    out = call(server.render_song, None, confirm=True, **SCRATCH)
    assert "Live was stopped at beat 40.0, before the end; the render is shorter" in out
    assert live.measured and live.arrangement == []


def test_without_quiet_main_stays(live):
    call(server.render_song, None, quiet=False, confirm=True, **SCRATCH)
    assert not [p for c, p in live.sent if c == "set_track_volume"]


@pytest.mark.parametrize("change, kwargs, expected", [
    (lambda l: setattr(l, "playing", True), {}, "Live is playing; stop it first"),
    (lambda l: setattr(l, "loop", True), {}, "the Arrangement loop is on"),
    (lambda l: l.arrangement.append({"name": "Old", "start_time": 8.0, "end_time": 12.0}), {},
     "already has an Arrangement clip between bars 1 and 16"),
    (lambda l: None, dict(end_bar=400), "a render is at most 600 s"),
    (lambda l: None, dict(start_bar=0), "start_bar must be a whole bar"),
    (lambda l: None, dict(start_bar=5, end_bar=4), "end_bar must be a whole bar, at or after start_bar"),
    (lambda l: l.tracks[2].update(monitoring="auto"), {}, "monitoring on 'Listen' is 'auto'"),
    (lambda l: l.input.update(available_types=["Ext. In", "Resampling"]), {}, "with quiet=True the render would be"),
])
def test_refusals_record_nothing(live, change, kwargs, expected):
    change(live)
    out = call(server.render_song, None, confirm=True, **dict(SCRATCH, **kwargs))
    assert out.startswith("Error") and expected in out
    assert "start_arrangement_record" not in live.commands() and live.main == 0.85


def test_render_song_is_a_modifying_tool():
    assert "render_song" in MODIFYING_TOOLS


def test_without_a_scratch_track_the_render_runs_on_a_temporary_one_and_keeps_the_wav(live):
    out = call(server.render_song, None, end_bar=4, confirm=True)
    assert out.startswith("On a temporary audio track 'Claude Listen (temporary)' (track 3), made for this call and "
                          "deleted after.\nRendered bars 1-4")
    assert "File: %s" % WAV in out and [t["name"] for t in live.tracks] == ["Drums", "Vox", "Listen"]
