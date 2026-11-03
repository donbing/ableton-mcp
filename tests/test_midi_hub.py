"""The MIDI hub's filters: what it passes on from a source, and what it accepts from a client."""

import json

from MCP_Server.midi_hub import keep, parse_request

PIANO = "Roland Digital Piano MIDI 1"
PADS = "Ableton Push 3 Live Port"
LIGHTS = ("FP10 Lights MIDI 1",)


def test_piano_passes_channel_messages_only():
    assert keep(PIANO, [0x90, 60, 100])
    assert keep(PIANO, [0xB0, 64, 127])
    assert not keep(PIANO, [0xF8])
    assert not keep(PIANO, [0xF0, 1, 2])


def test_push_pad_port_passes_pad_notes_only():
    assert keep(PADS, [0x93, 36, 90])
    assert keep(PADS, [0x83, 99, 0])
    assert not keep(PADS, [0x90, 35, 90])  # a touched encoder
    assert not keep(PADS, [0xB0, 71, 1])  # an encoder turn
    assert not keep(PADS, [0xA3, 50, 10])  # pad pressure


def test_request_needs_a_known_output_and_a_channel_message():
    ok = json.dumps({"type": "midi", "to": LIGHTS[0], "data": [0x91, 60, 80]})
    assert parse_request(ok, LIGHTS) == (LIGHTS[0], [0x91, 60, 80])
    assert parse_request(ok, ()) is None  # the strip isn't plugged in
    for bad in ({"type": "midi", "to": "Roland Digital Piano MIDI 1", "data": [0x90, 60, 80]},
                {"type": "midi", "to": LIGHTS[0], "data": [0xF0, 1, 2]},
                {"type": "midi", "to": LIGHTS[0], "data": [0x90, 200, 80]},
                {"type": "midi", "to": LIGHTS[0], "data": [0x90, True, 80]},
                {"type": "midi", "to": LIGHTS[0], "data": "90 3c 50"},
                {"type": "midi", "to": LIGHTS[0]}):
        assert parse_request(json.dumps(bad), LIGHTS) is None
    assert parse_request("not json", LIGHTS) is None
    assert parse_request("[1, 2]", LIGHTS) is None
