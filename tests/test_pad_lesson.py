"""pad_lesson: play chords on the Push 3's pads, then read the user's own presses and score them.
Here push_ui.send_and_watch (or rtmidi) is replaced, so nothing runs."""
import json
import sys
import types

import MCP_Server.push_midi as M
import MCP_Server.push_ui as P
import MCP_Server.server as server
from tests.test_scenes import call

ON, OFF = 0x90, 0x80


def press(note, down, up, velocity=70, channel=0):
    """A pad press as the hardware port sends it (a channel per press: the pads are MPE)."""
    return [[down, [ON | channel, note, velocity]], [up, [OFF | channel, note, 64]]]


def events(*presses):
    return sorted((e for p in presses for e in p), key=lambda e: e[0])


def test_pad_presses_pair_downs_with_ups_and_skip_the_demo():
    ev = events(press(36, 0.5, 1.0), press(36, 5.0, 6.0, channel=7), press(99, 5.5, 7.0, channel=8))
    ev.append([8.0, [ON, 43, 60]])  # still held when listening stopped
    got = P.pad_presses(ev, after=4.0)
    assert got == [
        {"pad": [1, 1], "down": 5.0, "up": 6.0, "velocity": 70},
        {"pad": [8, 8], "down": 5.5, "up": 7.0, "velocity": 70},
        {"pad": [1, 8], "down": 8.0, "up": None, "velocity": 60},
    ]


def test_a_note_on_with_velocity_zero_is_a_release():
    got = P.pad_presses([[1.0, [ON, 36, 80]], [2.0, [ON, 36, 0]]])
    assert got == [{"pad": [1, 1], "down": 1.0, "up": 2.0, "velocity": 80}]


def test_presses_close_together_are_one_chord():
    presses = P.pad_presses(events(press(36, 1.0, 3.0), press(38, 1.05, 3.1), press(40, 1.12, 3.0),
                                   press(44, 4.0, 5.0)))
    groups = P.chord_groups(presses)
    assert [[p["pad"] for p in g] for g in groups] == [[[1, 1], [1, 3], [1, 5]], [[2, 1]]]


def test_a_chord_put_down_one_finger_at_a_time_is_one_chord():
    # as measured on the Push: four pads over 1.1 s, all held, then let go together
    presses = P.pad_presses(events(press(36, 6.12, 8.99), press(45, 6.41, 9.0), press(38, 6.84, 9.02),
                                   press(40, 7.23, 9.03), press(36, 10.66, 11.5)))
    groups = P.chord_groups(presses)
    assert [[p["pad"] for p in g] for g in groups] == [[[1, 1], [2, 2], [1, 3], [1, 5]], [[1, 1]]]


def test_score_names_missed_and_extra_pads_and_the_timing():
    demo = [[[1, 1], [1, 3], [1, 5]], [[2, 1], [2, 3], [2, 5]]]
    played = P.chord_groups(P.pad_presses(events(
        press(36, 1.0, 3.0), press(38, 1.04, 3.1), press(40, 1.1, 2.9),
        press(44, 4.1, 6.0), press(46, 4.12, 6.0), press(47, 4.15, 6.0))))
    scored, all_right = P.score_lesson(demo, played)
    assert not all_right
    first, second = scored
    assert first["right"] and first["spread"] == 0.1 and first["held"] == 2.1 and first["gap_after"] == 1.0
    assert second["missed"] == [[2, 5]] and second["extra"] == [[2, 4]] and not second["right"]
    assert "gap_after" not in second


def test_score_counts_missing_and_surplus_chords():
    demo = [[[1, 1]], [[1, 2]]]
    one = P.chord_groups(P.pad_presses(events(press(36, 1.0, 2.0))))
    scored, all_right = P.score_lesson(demo, one)
    assert not all_right and scored[1]["played"] == [] and scored[1]["missed"] == [[1, 2]]
    three = P.chord_groups(P.pad_presses(events(press(36, 1.0, 2.0), press(37, 3.0, 4.0), press(38, 5.0, 6.0))))
    scored, all_right = P.score_lesson(demo, three)
    assert not all_right and scored[2]["demo"] == [] and not scored[2]["right"]


def test_pad_lesson_plays_the_demo_then_scores_what_came_after(monkeypatch):
    calls = []

    def watch(steps, release, wait, quiet, max_seconds):
        calls.append((steps, release, wait, quiet, max_seconds))
        # a press during the demo (3.0 s long) is not the user's answer
        return events(press(36, 0.5, 0.8), press(36, 4.0, 5.5), press(38, 4.05, 5.5), press(40, 4.08, 5.6)), 3.0

    monkeypatch.setattr(P, "send_and_watch", watch)
    out = json.loads(call(server.pad_lesson, None, [[[1, 1], [1, 3], [1, 5]]], hold=2.5, wait=5))
    assert out["all_right"] and out["chords_played"] == 1 and out["started_after"] == 1.0
    assert out["chords"][0]["held"] == 1.6 and out["demo_hold"] == 2.5
    assert out["chords"][0]["velocity"] == 70 and out["played_velocity"] == 70
    steps, release, wait, quiet, max_seconds = calls[0]
    assert [d[1:] for _, d in steps if d[0] & 0xF0 == ON] == [[36, 64], [38, 64], [40, 64]]
    assert [d[1] for d in release] == [36, 38, 40]
    assert (wait, quiet) == (5, 2.0) and max_seconds == 5 + 3 * 3.0 + 2.0


def test_pad_lesson_says_when_nothing_was_played(monkeypatch):
    monkeypatch.setattr(P, "send_and_watch", lambda *a: ([], 2.0))
    out = json.loads(call(server.pad_lesson, None, [[[1, 1]]]))
    assert not out["all_right"] and out["chords_played"] == 0 and "no pad was pressed" in out["note"]


def test_pad_lesson_refuses_bad_input_without_sending(monkeypatch):
    def watch(*a):
        raise AssertionError("nothing should be sent")

    monkeypatch.setattr(P, "send_and_watch", watch)
    assert call(server.pad_lesson, None, [[[0, 1]]]).startswith("Error: pads are row 1-8")
    assert call(server.pad_lesson, None, [[[1, 1]]] * 17).startswith("Error")
    assert call(server.pad_lesson, None, [[[1, 1]]], wait=0).startswith("Error")
    assert call(server.pad_lesson, None, [[[1, 1]]], quiet=9).startswith("Error")


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


def fake_rtmidi(monkeypatch, clock, script):
    """rtmidi with the three ports; the pad port plays `script` ([[time, bytes], ...]) by the fake clock."""
    sent = []

    class Port:
        def __init__(self):
            self.name = None

        def get_ports(self):
            return ["Ableton Internal Input", "Ableton Internal Output", "Ableton Push 3:Ableton Push 3 Live Port 16:0"]

        def open_port(self, i):
            self.name = self.get_ports()[i]

        def ignore_types(self, **k):
            pass

        def close_port(self):
            pass

        def get_message(self):
            if self.name and "Live Port" in self.name and script and script[0][0] <= clock.t:
                return [script.pop(0)[1], 0.0]
            return None

        def send_message(self, data):
            sent.append((round(clock.t, 2), data))

    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=Port, MidiIn=Port))
    monkeypatch.setattr(M, "open_output", lambda name: Port())
    monkeypatch.setattr(M, "time", types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep,
                                                       time=lambda: 1000.0, localtime=__import__("time").localtime,
                                                       strftime=__import__("time").strftime))
    return sent


def test_push_midi_listens_until_the_user_has_been_quiet(monkeypatch):
    clock = FakeClock()
    script = events(press(36, 2.0, 3.0), press(38, 2.02, 3.0))
    fake_rtmidi(monkeypatch, clock, script)
    out = M.run({"steps": [[1.0, [ON, 36, 90]]], "release": [], "pads": {"wait": 5, "quiet": 1.0, "max": 30}})
    assert out["steps_end"] == 1.0
    assert [d[1] for _, d in out["pads"] if d[0] == ON] == [36, 38]
    assert 4.0 <= clock.t < 4.2  # last release at 3.0, then 1 s of quiet


def test_push_midi_gives_up_when_nobody_plays(monkeypatch):
    clock = FakeClock()
    fake_rtmidi(monkeypatch, clock, [])
    out = M.run({"steps": [], "release": [], "pads": {"wait": 3, "quiet": 1.0, "max": 30}})
    assert out["pads"] == [] and 3.0 <= clock.t < 3.2


def test_push_midi_without_pads_replies_as_before(monkeypatch):
    clock = FakeClock()
    fake_rtmidi(monkeypatch, clock, [])
    assert M.run({"steps": [], "release": []}) == {"lights": []}


def test_wait_for_rescan_returns_once_live_has_reopened_its_devices(tmp_path, monkeypatch):
    import time as real_time
    log = tmp_path / "Log.txt"
    since = real_time.mktime((2026, 10, 30, 15, 25, 11, 0, 0, -1)) + 0.96
    log.write_text("2026-10-30T15:25:10.000000: info: MidiDeviceManager: End OpenAllActivatedDevices\n"
                   "2026-10-30T15:25:12.999545: info: MidiDeviceManager: End OpenAllActivatedDevices\n")
    assert M.wait_for_rescan(str(log), since, timeout=0.5)


def test_wait_for_rescan_ignores_an_older_rescan_and_gives_up(tmp_path):
    import time as real_time
    log = tmp_path / "Log.txt"
    since = real_time.mktime((2026, 10, 30, 15, 25, 11, 0, 0, -1))
    log.write_text("2026-10-30T15:25:10.000000: info: MidiDeviceManager: End OpenAllActivatedDevices\n")
    assert not M.wait_for_rescan(str(log), since, timeout=0.2)
    assert not M.wait_for_rescan(str(tmp_path / "missing.txt"), since, timeout=0.2)


def test_push_midi_waits_for_the_rescan_when_given_the_log(monkeypatch):
    clock, waited = FakeClock(), []
    fake_rtmidi(monkeypatch, clock, [])
    monkeypatch.setattr(M, "wait_for_rescan", lambda path, since: waited.append(path) or True)
    M.run({"steps": [], "release": [], "live_log": "/x/Log.txt"})
    assert waited == ["/x/Log.txt"] and clock.t >= M.AFTER_RESCAN  # and then 2 s more
    before = clock.t
    M.run({"steps": [], "release": []})
    assert waited == ["/x/Log.txt"] and clock.t == before  # Set buttons don't wait


def test_pad_lesson_passes_lives_log_for_the_rescan_wait(monkeypatch):
    seen = []
    monkeypatch.setattr(P, "live_log", lambda prefs_dir=None: "/x/Log.txt")
    monkeypatch.setattr(P, "_run", lambda request, seconds: seen.append(request) or {"pads": [], "steps_end": 0.0})
    P.send_and_watch([], [], 5, 2, 10)
    assert seen[0]["live_log"] == "/x/Log.txt"
