"""play_pads: press the Push 3's pads through push_midi.py. Here push_ui.send is replaced, so nothing runs."""
import MCP_Server.push_midi as M
import MCP_Server.push_ui as P
import MCP_Server.server as server
from tests.test_scenes import call


def test_pad_notes_run_from_bottom_left_to_top_right():
    assert P.pad_note(1, 1) == 36
    assert P.pad_note(1, 8) == 43
    assert P.pad_note(2, 1) == 44
    assert P.pad_note(8, 8) == 99


def test_pad_steps_press_a_chord_together_hold_it_then_the_next():
    steps, release = P.pad_steps([[(1, 1), (1, 3)], [(2, 1)]], hold=1.5, gap=0.5, velocity=90)
    # a channel per press from channel 2, bend centred first, released with velocity 64
    assert steps == [
        [0.0, [0xE1, 0, 64]], [0.0, [0x91, 36, 90]], [0.0, [0xE2, 0, 64]], [0.0, [0x92, 38, 90]],
        [1.5, [0x81, 36, 64]], [0.0, [0x82, 38, 64]],
        [0.5, [0xE3, 0, 64]], [0.0, [0x93, 44, 90]],
        [1.5, [0x83, 44, 64]],
    ]
    assert release == [[0x81, 36, 64], [0x82, 38, 64], [0x83, 44, 64]]


def test_pad_steps_never_use_channel_1_and_wrap_after_16():
    steps, release = P.pad_steps([[(1, c)] for c in range(1, 9)] * 2, hold=0.1, gap=0.0, velocity=90)
    channels = [d[0] & 0x0F for _, d in steps if d[0] & 0xF0 == 0x90]
    assert 0 not in channels and channels[:16] == list(range(1, 16)) + [1]


def test_pad_lights_names_the_pads_the_push_relit():
    lights = [[0.0, [0x90, 36, 122]], [0.1, [0xB0, 82, 0]], [0.2, [0x90, 99, 5]], [0.3, [0x90, 36, 0]]]
    assert P.pad_lights(lights) == [[1, 1], [8, 8]]


def test_play_pads_sends_the_steps_and_lets_go_of_every_pad(monkeypatch):
    sent = []

    def send(steps, listen=0.0, until_cc=None, until_value=None, release=(), settle=False):
        sent.append((steps, list(release), settle))
        return [[0.0, [0x90, 36, 122]]]

    monkeypatch.setattr(P, "send", send)
    out = call(server.play_pads, None, [[[1, 1], [1, 3], [1, 5]]], hold=1.0)
    assert "Pressed [1,1] + [1,3] + [1,5]" in out and "lit 1 pad" in out
    steps, release, settle = sent[0]
    assert settle  # pads wait out Live's MIDI rescan
    assert [d[1:] for _, d in steps if d[0] & 0xF0 == 0x90] == [[36, 64], [38, 64], [40, 64]]
    assert [d[1] for d in release if d[0] & 0xF0 == 0x80] == [36, 38, 40]


def test_play_pads_says_when_no_pad_lit(monkeypatch):
    monkeypatch.setattr(P, "send", lambda steps, **k: [])
    assert "may not have reached it" in call(server.play_pads, None, [[[1, 1]]])


def test_play_pads_refuses_bad_pads_without_sending(monkeypatch):
    def send(*a, **k):
        raise AssertionError("nothing should be sent")

    monkeypatch.setattr(P, "send", send)
    assert call(server.play_pads, None, [[[9, 1]]]).startswith("Error: pads are row 1-8")
    assert call(server.play_pads, None, []).startswith("Error")
    assert call(server.play_pads, None, [[[1, 1]]], velocity=0).startswith("Error")
    assert call(server.play_pads, None, [[[1, 1]]], hold=20).startswith("Error")


def test_push_midi_sends_release_even_when_a_step_fails(monkeypatch):
    import sys
    import types

    sent = []

    class Port:
        def get_ports(self):
            return ["Ableton Internal Input", "Ableton Internal Output"]

        def open_port(self, i):
            pass

        def close_port(self):
            pass

        def get_message(self):
            return None

        def send_message(self, data):
            if data == "bad":
                raise RuntimeError("boom")
            sent.append(data)

    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=Port, MidiIn=Port))
    monkeypatch.setattr(M, "open_output", lambda name: Port())
    try:
        M.run({"steps": [[0, [0x90, 36, 90]], [0, "bad"]], "release": [[0x80, 36, 0]]})
    except RuntimeError:
        pass
    assert sent == [[0x90, 36, 90], [0x80, 36, 0]]
