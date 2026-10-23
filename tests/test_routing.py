"""Tests for back_to_arrangement, get_track_routing and set_track_routing.

The fake tracks list the routing channels for the routing TYPE Live has applied,
and a new type is applied only when the code waits (like the playhead and the
cue points, Live updates a moment later), so a channel set in the same tick as
the type would be refused.
"""
import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from tests.test_notes_edit import make_inst, script_module  # noqa: F401
from tests.test_scenes import call, conn  # noqa: F401


class Routing(object):
    def __init__(self, name):
        self.display_name = name


CHANNELS = {"Ext. In": ["1/2", "3/4"], "Master": ["Track Out"], "Sends Only": []}


class Track(object):
    def __init__(self, name, state):
        self.name = name
        self._state = state          # shared dict: pending / applied types
        self.types = {d: [Routing(n) for n in ("Ext. In", "Master", "Sends Only")] for d in ("input", "output")}
        self._type = {"input": self.types["input"][0], "output": self.types["output"][1]}
        self._applied = {"input": "Ext. In", "output": "Master"}
        self._channel = {"input": Routing("1/2"), "output": Routing("Track Out")}
        self.channel_sets = []

    def tick(self):
        for d in ("input", "output"):
            self._applied[d] = self._type[d].display_name

    def _channels(self, d):
        return [Routing(n) for n in CHANNELS[self._applied[d]]]

    available_input_routing_types = property(lambda s: s.types["input"])
    available_output_routing_types = property(lambda s: s.types["output"])
    available_input_routing_channels = property(lambda s: s._channels("input"))
    available_output_routing_channels = property(lambda s: s._channels("output"))
    input_routing_type = property(lambda s: s._type["input"],
                                  lambda s, v: s._type.__setitem__("input", v))
    output_routing_type = property(lambda s: s._type["output"],
                                   lambda s, v: s._type.__setitem__("output", v))
    input_routing_channel = property(lambda s: s._channel["input"])
    output_routing_channel = property(lambda s: s._channel["output"])

    def _set_channel(self, d, value):
        if value.display_name not in [c.display_name for c in self._channels(d)]:
            raise RuntimeError("channel not available for the applied type")
        self.channel_sets.append((d, value.display_name))
        self._channel[d] = value


Track.input_routing_channel = property(Track.input_routing_channel.fget,
                                       lambda s, v: s._set_channel("input", v))
Track.output_routing_channel = property(Track.output_routing_channel.fget,
                                        lambda s, v: s._set_channel("output", v))


class MasterTrack(object):
    name = "Master"

    def __init__(self):
        self.output_routing_type = Routing("Ext. Out")
        self.output_routing_channel = Routing("1/2")
        self.available_output_routing_types = [Routing("Ext. Out")]
        self.available_output_routing_channels = [Routing("1/2")]


class Song(object):
    def __init__(self):
        self.tracks = [Track("Bass", {}), Track("Keys", {})]
        self.return_tracks = [Track("A-Reverb", {})]
        self.master_track = MasterTrack()
        self.back_to_arranger = 1


@pytest.fixture
def song():
    return Song()


@pytest.fixture
def inst(script_module, song, monkeypatch):
    def sleep(seconds):
        for t in song.tracks + song.return_tracks:
            t.tick()
    monkeypatch.setattr(script_module.time, "sleep", sleep)
    return make_inst(script_module, song)


def run(inst, command, **params):
    return inst._process_command({"type": command, "params": params})


def ok(reply):
    assert reply["status"] == "success", reply
    return reply["result"]


def err(reply):
    assert reply["status"] == "error", reply
    return reply["message"]


def test_back_to_arrangement_clears_the_flag_and_reports_before_and_after(inst, song):
    result = ok(run(inst, "back_to_arrangement"))
    assert result["before"] is True and result["read_back"] is False
    assert song.back_to_arranger == 0


def test_get_routing_lists_current_and_available(inst):
    result = ok(run(inst, "get_track_routing", track_index=0))
    assert result["track_name"] == "Bass"
    assert result["input"]["type"] == "Ext. In" and result["input"]["channel"] == "1/2"
    assert result["input"]["available_types"] == ["Ext. In", "Master", "Sends Only"]
    assert result["input"]["available_channels"] == ["1/2", "3/4"]
    assert result["output"]["available_channels"] == ["Track Out"]


def test_get_routing_of_a_return_and_of_the_master(inst):
    assert ok(run(inst, "get_track_routing", track_index=0, track_type="return"))["track_name"] == "A-Reverb"
    master = ok(run(inst, "get_track_routing", track_type="master"))
    assert master["input"] is None and master["output"]["type"] == "Ext. Out"


def test_set_a_type_then_a_channel_waits_for_live_to_list_the_channels(inst, song):
    result = ok(run(inst, "set_track_routing", track_index=0, expected_name="Bass",
                    direction="input", routing_type="Master", routing_channel="Track Out"))
    assert result["verified"] is True
    assert result["before"] == {"type": "Ext. In", "channel": "1/2"}
    assert result["after"]["type"] == "Master" and result["after"]["channel"] == "Track Out"
    assert song.tracks[0].channel_sets == [("input", "Track Out")]


def test_set_only_a_channel_and_match_names_ignoring_case(inst, song):
    ok(run(inst, "set_track_routing", track_index=1, expected_name="Keys", direction="input",
           routing_channel="3/4"))
    assert song.tracks[1].channel_sets == [("input", "3/4")]
    ok(run(inst, "set_track_routing", track_index=1, expected_name="Keys", direction="output",
           routing_type="sends only"))
    assert song.tracks[1]._type["output"].display_name == "Sends Only"


def test_a_wrong_name_an_unknown_type_or_channel_change_nothing(inst, song):
    t = song.tracks[0]
    assert "not 'Other'" in err(run(inst, "set_track_routing", track_index=0, expected_name="Other",
                                    direction="output", routing_type="Master"))
    message = err(run(inst, "set_track_routing", track_index=0, expected_name="Bass",
                      direction="output", routing_type="Nope"))
    assert "Routing type 'Nope' not found" in message and "Ext. In, Master, Sends Only" in message
    assert "Routing channel '9/9' not found" in err(run(inst, "set_track_routing", track_index=0,
                                                         expected_name="Bass", direction="input",
                                                         routing_channel="9/9"))
    assert t._type["output"].display_name == "Master" and t.channel_sets == []


def test_two_routings_with_the_same_name_cannot_be_chosen_by_name(inst, song):
    t = song.tracks[0]
    t.types["output"] = [Routing("Master"), Routing("Keys"), Routing("Keys")]
    message = err(run(inst, "set_track_routing", track_index=0, expected_name="Bass",
                      direction="output", routing_type="Keys"))
    assert "2 routing types are named 'Keys'" in message and "Rename one" in message
    assert t._type["output"].display_name == "Master"


def test_bad_arguments(inst):
    assert "direction must be" in err(run(inst, "set_track_routing", track_index=0, expected_name="Bass",
                                          direction="sideways", routing_type="Master"))
    assert "Give routing_type" in err(run(inst, "set_track_routing", track_index=0, expected_name="Bass",
                                          direction="input"))
    assert "expected_name is required" in err(run(inst, "set_track_routing", track_index=0,
                                                  expected_name=None, direction="input",
                                                  routing_type="Master"))


def test_the_master_has_no_input_to_set(inst):
    assert "no input routing" in err(run(inst, "set_track_routing", track_type="master",
                                         expected_name="Master", direction="input", routing_type="x"))


def test_tools_send_the_right_commands_and_need_the_name(conn):
    conn.response = {"verified": True}
    call(server.set_track_routing, None, 0, "Bass", "output", routing_type="Master")
    assert conn.sent[-1] == ("set_track_routing", {"track_index": 0, "track_type": "track",
                                                   "expected_name": "Bass", "direction": "output",
                                                   "routing_type": "Master"})
    assert "expected_name is required" in call(server.set_track_routing, None, 0, None, "output",
                                               routing_type="Master")
    call(server.get_track_routing, None, 2, "return")
    assert conn.sent[-1] == ("get_track_routing", {"track_index": 2, "track_type": "return"})
    call(server.back_to_arrangement, None)
    assert conn.sent[-1][0] == "back_to_arrangement"
    assert {"set_track_routing", "back_to_arrangement"} <= MODIFYING_TOOLS
