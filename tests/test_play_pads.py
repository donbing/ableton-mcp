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
    assert steps == [
        [0.0, [0x90, 36, 90]], [0.0, [0x90, 38, 90]],
        [1.5, [0x80, 36, 0]], [0.0, [0x80, 38, 0]],
        [0.5, [0x90, 44, 90]],
        [1.5, [0x80, 44, 0]],
    ]
    assert release == [[0x80, 36, 0], [0x80, 38, 0], [0x80, 44, 0]]


def test_pad_lights_names_the_pads_the_push_relit():
    lights = [[0.0, [0x90, 36, 122]], [0.1, [0xB0, 82, 0]], [0.2, [0x90, 99, 5]], [0.3, [0x90, 36, 0]]]
    assert P.pad_lights(lights) == [[1, 1], [8, 8]]


def test_play_pads_sends_the_steps_and_lets_go_of_every_pad(monkeypatch):
    sent = []

    def send(steps, listen=0.0, until_cc=None, until_value=None, release=()):
        sent.append((steps, list(release)))
        return [[0.0, [0x90, 36, 122]]]

    monkeypatch.setattr(P, "send", send)
    out = call(server.play_pads, None, [[[1, 1], [1, 3], [1, 5]]], hold=1.0)
    assert "Pressed [1,1] + [1,3] + [1,5]" in out and "lit 1 pad" in out
    steps, release = sent[0]
    assert [d for _, d in steps if d[0] == 0x90] == [[0x90, 36, 90], [0x90, 38, 90], [0x90, 40, 90]]
    assert release == [[0x80, 36, 0], [0x80, 38, 0], [0x80, 40, 0]]


def test_play_pads_says_when_no_pad_lit(monkeypatch):
    monkeypatch.setattr(P, "send", lambda steps, listen=0.0, until_cc=None, until_value=None, release=(): [])
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
    try:
        M.run({"steps": [[0, [0x90, 36, 90]], [0, "bad"]], "release": [[0x80, 36, 0]]})
    except RuntimeError:
        pass
    assert sent == [[0x90, 36, 90], [0x80, 36, 0]]
