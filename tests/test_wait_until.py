"""wait_until: wait while Live plays until the playhead reaches a bar or beat, or Live stops."""
import pytest

import MCP_Server.server as server
from tests.test_scenes import call, conn  # noqa: F401


class Live(object):
    """Plays at 2 beats a second from beat 0 on the test clock; stops at stop_at."""

    def __init__(self):
        self.t, self.playing, self.stop_at, self.sent = 0.0, True, None, []

    def time(self):
        beats = self.t * 2.0
        return min(beats, self.stop_at) if self.stop_at is not None else beats

    def send_command(self, command, params=None):
        self.sent.append(command)
        if command == "get_tracks_overview":
            return {"time_signature": "4/4", "tracks": []}
        playing = self.playing and (self.stop_at is None or self.t * 2.0 < self.stop_at)
        return {"current_song_time": self.time(), "is_playing": playing}


@pytest.fixture
def live(conn, monkeypatch):
    fake = Live()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(server, "_listen_now", lambda: fake.t)
    monkeypatch.setattr(server, "_listen_sleep", lambda s: setattr(fake, "t", fake.t + s))
    return fake


def test_it_waits_for_a_bar(live):
    # bar 5 = beat 16 = 8 s
    assert call(server.wait_until, None, bar=5) == "Reached beat 16.00 (bar 5) after 8.0 s."


def test_it_waits_for_a_beat(live):
    assert call(server.wait_until, None, beat=3.0) == "Reached beat 3.00 (bar 1) after 1.5 s."


def test_a_stop_ends_the_wait(live):
    live.stop_at = 10.0
    assert call(server.wait_until, None, bar=9) == "Live is stopped, at beat 10.00 (bar 3), before beat 32.00 (bar 9)."


def test_already_stopped_returns_at_once(live):
    live.playing = False
    out = call(server.wait_until, None, bar=9)
    assert out.startswith("Live is already stopped, at beat 0.00 (bar 1)") and live.t == 0.0


def test_it_gives_up_after_the_timeout(live):
    out = call(server.wait_until, None, bar=100, timeout_seconds=5)
    assert out == "Not there after 5 s: the playhead is at beat 10.00 (bar 3), before beat 396.00 (bar 100)."


@pytest.mark.parametrize("kwargs, expected", [
    ({}, "give bar or beat"), (dict(bar=2, beat=4), "give bar or beat"),
    (dict(bar=2, timeout_seconds=301), "at most 300"), (dict(bar=2, timeout_seconds=0), "above 0"),
])
def test_bad_arguments(live, kwargs, expected):
    assert expected in call(server.wait_until, None, **kwargs) and live.sent == []
