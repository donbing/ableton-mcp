"""load_instrument_or_effect and set_arrangement_time read Live back AFTER it applied
the change (upstream issue #134): a reply built in the same tick showed an empty
device chain and the previous playhead."""
import types

import pytest

import MCP_Server.server as server
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Device(object):
    def __init__(self, name):
        self.name = name


class Song(object):
    """Changes land only when the code waits (like Live's one-tick delay)."""

    def __init__(self):
        self._time, self._applied_time = 10.0, 10.0
        self.is_playing = True
        self._pending_devices = []
        track = types.SimpleNamespace(name="Bass", devices=[Device("EQ")])
        self.tracks = [track]
        self.view = types.SimpleNamespace(selected_track=None)

    @property
    def current_song_time(self):
        return self._applied_time

    @current_song_time.setter
    def current_song_time(self, value):
        self._time = value

    def tick(self):
        self._applied_time = self._time
        self.tracks[0].devices += [Device(n) for n in self._pending_devices]
        self._pending_devices = []


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    monkeypatch.setattr(script_module.time, "sleep", lambda s: song.tick())
    obj = make_inst(script_module, song)

    class Browser(object):
        def load_item(self, item):
            song._pending_devices.append(item.name)

    obj.application = lambda: types.SimpleNamespace(browser=Browser())
    obj._find_browser_item_by_uri = lambda browser, uri: types.SimpleNamespace(name="Compressor") if uri == "ok" else None
    return obj


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def test_a_loaded_device_is_listed_after_live_adds_it(inst):
    reply = run(inst, "load_instrument_or_effect", track_index=0, uri="ok")
    assert reply["status"] == "success", reply
    result = reply["result"]
    assert result["loaded"] is True
    assert result["devices_before"] == ["EQ"] and result["devices_after"] == ["EQ", "Compressor"]
    assert result["new_devices"] == ["Compressor"]


def test_load_browser_item_does_the_same(inst):
    result = run(inst, "load_browser_item", track_index=0, item_uri="ok")["result"]
    assert result["new_devices"] == ["Compressor"]


def test_a_load_that_changes_nothing_says_so_instead_of_claiming_success(inst, song, monkeypatch):
    inst.application = lambda: types.SimpleNamespace(browser=types.SimpleNamespace(load_item=lambda item: None))
    result = run(inst, "load_instrument_or_effect", track_index=0, uri="ok")["result"]
    assert result["loaded"] is False and "did not change" in result["warning"]


def test_an_unknown_uri_is_an_error(inst):
    assert "not found" in run(inst, "load_instrument_or_effect", track_index=0, uri="nope")["message"]


def test_the_playhead_reply_has_the_new_position_not_the_old_one(inst):
    result = run(inst, "set_current_song_time", time=73.34)["result"]
    assert result["current_song_time"] == 73.34 and result["requested"] == 73.34
    assert "warning" not in result


def test_a_playhead_that_did_not_move_is_flagged(inst, song, monkeypatch):
    monkeypatch.setattr(song, "tick", lambda: None)
    result = run(inst, "set_current_song_time", time=73.34)["result"]
    assert result["current_song_time"] == 10.0 and "not the requested 73.34" in result["warning"]


def test_tool_messages(conn):
    conn.response = {"current_song_time": 73.34, "requested": 73.34}
    assert call(server.set_arrangement_time, None, 73.34) == "Playhead moved to beat 73.34"
    conn.response = {"current_song_time": 10.0, "requested": 73.0, "warning": "at 10"}
    assert "WARNING: at 10" in call(server.set_arrangement_time, None, 73.0)
    conn.response = {"loaded": False, "warning": "list did not change"}
    assert "list did not change" in call(server.load_instrument_or_effect, None, 0, "x")
