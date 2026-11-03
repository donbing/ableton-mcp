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


def test_held_notes_follow_offs_and_all_notes_off():
    """A client that drops mid-note left keys lit (2026-11-03): the hub keeps what each one has on."""
    from MCP_Server.midi_hub import track_held
    held = set()
    track_held(held, LIGHTS[0], [0x90, 48, 90])
    track_held(held, LIGHTS[0], [0x90, 50, 90])
    track_held(held, LIGHTS[0], [0x91, 60, 45])
    track_held(held, LIGHTS[0], [0x80, 48, 0])
    track_held(held, LIGHTS[0], [0x90, 50, 0])  # note-on with velocity 0 is an off
    assert held == {(LIGHTS[0], 1, 60)}
    track_held(held, LIGHTS[0], [0x90, 52, 90])
    track_held(held, LIGHTS[0], [0xB1, 123, 0])  # all notes off clears its own channel only
    assert held == {(LIGHTS[0], 0, 52)}


def test_ping_gets_its_own_time_back():
    from MCP_Server.midi_hub import pong_for
    assert json.loads(pong_for(json.dumps({"type": "ping", "t": 1234.5}))) == {"type": "pong", "t": 1234.5}
    assert pong_for(json.dumps({"type": "midi", "to": LIGHTS[0], "data": [0x90, 60, 1]})) is None
    assert pong_for("not json") is None


def test_timing_summary():
    from MCP_Server.midi_hub import timing
    assert timing([40, 10, 30, 20, 1000]) == "n=5, median 30 ms, 95% 1000 ms, max 1000 ms"
    assert timing([7]) == "n=1, median 7 ms, 95% 7 ms, max 7 ms"


def test_a_stopped_hubs_connections_dont_count_as_taken():
    """After the hub was killed its connections lingered, and the restarted hub refused to start (2026-11-03)."""
    import socket
    from MCP_Server.midi_hub import port_taken
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _ = server.accept()
    server.close()  # the listener is gone, a connection on the port is left
    try:
        assert not port_taken("127.0.0.1", port)
    finally:
        accepted.close()
        client.close()
