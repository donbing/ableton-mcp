"""list_sets, which_set, load_set and save_set: open and save Sets by pressing the Push 3's own buttons.

The MIDI and the timings follow what was measured on Push 3 standalone, Live 12.4.15 (2026-10-29):
Sets (CC80) lights 127 when the browser opens and 14 when a press closes it; the jog wheel (CC70,
touch note 11) moves one entry per message, 1 = down; the jog press (CC94) loads; Save (CC82) goes
dark when the Set is written. The log lines are copied from that Push's Log.txt. Here push_midi.py
never runs: push_ui.send is replaced by a fake Push that answers with lights and writes the log and
the Set files the way Live did.
"""
import json
import os
import sys
import types

import pytest

import MCP_Server.push_midi as M
import MCP_Server.push_ui as P
import MCP_Server.server as server
from tests.test_scenes import call

LOG_HEAD = (
    '2026-10-29T00:27:01.100000: info: Loading document "{sets}/Arcing the Singularity Project/'
    'Arcing the Singularity.als"\n'
    "2026-10-29T01:04:19.429591: info: Default App: End ExchangeDocument\n"
)
LOAD_LINE = '2026-10-29T01:04:19.429789: info: Loading document "{path}"\n'


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


@pytest.fixture
def push(tmp_path, monkeypatch):
    """A Sets folder and a Live log like the Push's, and a fake Push behind push_ui.send."""
    sets, prefs = tmp_path / "Sets", tmp_path / "prefs"
    clock = Clock()
    # newest first: Set 12-1, Set 12, Arcing the Singularity, then an [Autosave] one
    for age, name in enumerate(["Set 12-1", "Set 12", "Arcing the Singularity", "Diamond of Specter [Autosave]"]):
        folder = sets / (name + " Project")
        folder.mkdir(parents=True)
        (folder / (name + ".als")).write_bytes(b"als")
        t = clock.t - 3600 * (age + 1)
        os.utime(folder / (name + ".als"), (t, t))
        os.utime(folder, (t, t))
    for old in ("Live 12.4.6", "Live 12.4.15"):
        (prefs / old).mkdir(parents=True)
    (prefs / "Live 12.4.6" / "Log.txt").write_text("", encoding="utf-8")
    log = prefs / "Live 12.4.15" / "Log.txt"
    log.write_text(LOG_HEAD.format(sets=sets.as_posix()), encoding="utf-8")
    monkeypatch.setattr(P, "SETS_DIR", str(sets))
    monkeypatch.setattr(P, "LIVE_PREFS_DIR", str(prefs))
    monkeypatch.setattr(P, "now", clock.now)
    monkeypatch.setattr(P, "sleep", clock.sleep)
    fake = FakePush(sets, log, clock)
    monkeypatch.setattr(P, "send", fake.send)
    return fake


class FakePush:
    def __init__(self, sets, log, clock):
        self.sets, self.log, self.clock = sets, log, clock
        self.browser_open = False
        self.highlight = 0
        self.sent = []
        self.loads = True      # False: the jog press loads nothing (a question on the Push's screen)
        self.saves = True
        self.sets_light = True  # False: the Sets light never answers
        self.dirty = False      # the open Set has unsaved changes: the jog press asks first
        self.prompt = False
        self.open_file = self.sets / "Arcing the Singularity Project" / "Arcing the Singularity.als"

    def entries(self):
        return [s["als"] for s in P.list_sets(str(self.sets))]

    def send(self, steps, listen=0.0, until_cc=None):
        lights = []
        for _, data in steps:
            self.sent.append(data)
            kind, number, value = data[0] & 0xF0, data[1], data[2]
            if kind != 0xB0:
                continue
            if number == P.CC_SETS and value == 127:
                self.browser_open = not self.browser_open
                self.highlight = 0
                if self.sets_light:
                    lights.append([0.03, [0xB0, P.CC_SETS, 127 if self.browser_open else 14]])
            elif number == P.CC_JOG and self.browser_open:
                self.highlight = max(0, self.highlight + (1 if value == 1 else -1))
            elif number == P.CC_JOG_PRESS and value == 127 and self.browser_open and self.dirty:
                # as measured: the Sets and Save lights go dark, the three answers light up
                self.prompt = True
                lights += [[0.05, [0xB0, 80, 0]], [0.05, [0xB0, 82, 0]], [0.05, [0xB0, 24, 122]],
                           [0.05, [0xB0, 26, 122]], [0.05, [0xB0, 27, 126]]]
            elif number == P.CC_JOG_PRESS and value == 127 and self.browser_open and self.loads:
                self.load()
            elif self.prompt and value == 127 and number in (24, 26, 27):
                self.prompt = False
                lights += [[0.05, [0xB0, 24, 0]], [0.05, [0xB0, 26, 0]], [0.05, [0xB0, 27, 0]]]
                if number == 26:
                    lights += [[0.05, [0xB0, 80, 127]], [0.05, [0xB0, 82, 127]]]
                    continue
                if number == 27:
                    os.utime(self.open_file, (self.clock.t + 1, self.clock.t + 1))
                self.dirty = False
                self.load()
            elif number == P.CC_SAVE and value == 127 and self.saves:
                lights.append([0.1, [0xB0, P.CC_SAVE, 0]])
                path = self.sets / "Set 12-1 Project" / "Set 12-1.als"
                os.utime(path, (self.clock.t + 1, self.clock.t + 1))
        self.clock.t += listen
        return lights

    def load(self):
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(LOAD_LINE.format(path=self.entries()[self.highlight]))
        self.browser_open = False


# --------------------------------------------------------------------------- MIDI

def test_a_press_is_the_button_down_then_up():
    assert P.press(80) == [[0.0, [0xB0, 80, 127]], [0.2, [0xB0, 80, 0]]]


def test_jog_steps_are_one_message_per_detent_inside_the_touch():
    down = P.jog(2)
    assert [d for _, d in down] == [[0x90, 11, 127], [0xB0, 70, 1], [0xB0, 70, 1], [0x80, 11, 0]]
    assert [d for _, d in P.jog(-1)][1] == [0xB0, 70, 127]


def test_the_last_light_for_a_controller_wins():
    lights = [[0.1, [0xB0, 80, 14]], [0.2, [0x90, 80, 127]], [0.3, [0xB0, 80, 127]]]
    assert P.last_light(lights, 80) == 127 and P.last_light(lights, 82) is None


def test_send_refuses_off_the_push(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "PUSH_PYTHON", str(tmp_path / "no-python"))
    with pytest.raises(P.PushError, match="only work where the server runs on the Push"):
        P.send(P.press(80))


# --------------------------------------------------------------------------- the helper (fake rtmidi)

class FakePorts:
    replies = []

    def __init__(self):
        self.messages, self.opened = [], None

    def get_ports(self):
        return self.ports

    def open_port(self, i):
        self.opened = i

    def close_port(self):
        pass


class FakeOut(FakePorts):
    ports = ["Ableton Push 3:Ableton Push 3 Live Port 16:0", "RtMidi Input Client:Ableton Internal Input 129:0"]
    sent = []

    def send_message(self, data):
        FakeOut.sent.append(data)
        FakeIn.queue.extend(FakePorts.replies.pop(0) if FakePorts.replies else [])


class FakeIn(FakePorts):
    ports = ["RtMidi Output Client:Ableton Internal Output 130:0"]
    queue = []

    def get_message(self):
        return (FakeIn.queue.pop(0), 0.0) if FakeIn.queue else None


def test_the_helper_opens_the_ui_ports_by_name_and_stops_at_the_awaited_light(monkeypatch):
    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=FakeOut, MidiIn=FakeIn))
    FakeOut.sent, FakeIn.queue = [], []
    FakePorts.replies = [[[0xB0, 80, 127], [0xB0, 107, 122]], []]
    result = M.run({"steps": P.press(80), "listen": 30, "until_cc": 80})
    assert FakeOut.sent == [[0xB0, 80, 127], [0xB0, 80, 0]]
    # it returned at once instead of listening for 30 s
    assert [d for _, d in result["lights"]] == [[0xB0, 80, 127], [0xB0, 107, 122]]


def test_the_helper_says_which_port_is_missing(monkeypatch):
    class NoUi(FakeOut):
        ports = ["Ableton Push 3:Ableton Push 3 Live Port 16:0"]
    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=NoUi, MidiIn=FakeIn))
    assert "Ableton Internal Input" in M.run({"steps": []})["error"]


# --------------------------------------------------------------------------- Sets on disk and the log

def test_sets_are_listed_newest_first_like_the_browser(push):
    sets = P.list_sets()
    assert [(s["position"], s["name"]) for s in sets] == [
        (1, "Set 12-1"), (2, "Set 12"), (3, "Arcing the Singularity"), (4, "Diamond of Specter [Autosave]")]
    assert sets[1]["als"].endswith(os.path.join("Set 12 Project", "Set 12.als"))


def test_a_project_whose_set_has_another_name_still_has_its_file(push):
    folder = push.sets / "Odd Project"
    folder.mkdir()
    (folder / "Renamed.als").write_bytes(b"als")
    odd = P.find_set("odd", P.list_sets())
    assert odd["als"].endswith("Renamed.als")


def test_an_unknown_name_lists_the_sets(push):
    with pytest.raises(P.PushError, match="no Set named 'Set 13'.*Set 12-1, Set 12"):
        P.find_set("Set 13", P.list_sets())


def test_the_newest_live_versions_log_names_the_open_set(push):
    assert P.live_log().endswith(os.path.join("Live 12.4.15", "Log.txt"))
    stamp, path = P.current_document()
    assert stamp.startswith("2026-10-29T00:27") and path.endswith("Arcing the Singularity.als")


def test_the_default_template_reads_as_a_new_set():
    assert P.is_template("/opt/push3/products/live/Live/AppLive/Resources/Builtin/Templates/DefaultLiveSet.als")
    assert "default template" in server._describe_open(("2026-10-29T01:09:06.5", "/x/Templates/DefaultLiveSet.als"))


def test_list_sets_marks_the_open_one(push):
    out = call(server.list_sets, None)
    assert "3. Arcing the Singularity (saved" in out and out.count("<- open") == 1
    assert "Arcing the Singularity (saved" in [line for line in out.splitlines() if "<- open" in line][0]


def test_which_set_reads_the_log(push):
    assert "Arcing the Singularity.als (loaded 2026-10-29T00:27:01)" in call(server.which_set, None)


# --------------------------------------------------------------------------- load_set

def test_load_set_previews_without_pressing_anything(push):
    out = call(server.load_set, None, "Set 12")
    assert out.startswith("NOT LOADED") and "1 jog step(s) down to entry 2" in out
    assert push.sent == []


def test_load_set_opens_the_browser_jogs_down_and_loads(push):
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "pressed Sets once, jogged 1 down" in out
    assert push.sent == [[0xB0, 80, 127], [0xB0, 80, 0], [0x90, 11, 127], [0xB0, 70, 1], [0x80, 11, 0],
                         [0xB0, 94, 127], [0xB0, 94, 0]]
    assert P.current_document()[1].endswith("Set 12.als")


def test_an_open_browser_is_closed_and_reopened_on_the_top_entry(push):
    push.browser_open, push.highlight = True, 3
    out = call(server.load_set, None, "Set 12-1", confirm=True)
    assert out.startswith("Loaded 'Set 12-1'") and "twice (the browser was open), jogged 0 down" in out
    assert push.sent[:4] == [[0xB0, 80, 127], [0xB0, 80, 0], [0xB0, 80, 127], [0xB0, 80, 0]]


def test_no_sets_light_means_nothing_more_is_sent(push):
    push.sets_light = False
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert "light did not change" in out and "nothing more was sent" in out
    assert push.sent == [[0xB0, 80, 127], [0xB0, 80, 0]]


def test_the_open_set_is_not_loaded_again(push):
    out = call(server.load_set, None, "Arcing the Singularity", confirm=True)
    assert "already open" in out and push.sent == []


def test_a_load_that_never_shows_in_the_log_is_reported(push):
    push.loads = False
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert out.startswith("Error: Live's log shows no Set loading within 15 s")


def test_unsaved_changes_are_left_for_the_user_by_default(push):
    push.dirty = True
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert out.startswith("Not loaded:") and "unsaved changes" in out and 'unsaved="discard"' in out
    # Cancel, then Sets to close the browser again
    assert push.sent[-4:] == [[0xB0, 26, 127], [0xB0, 26, 0], [0xB0, 80, 127], [0xB0, 80, 0]]
    assert not push.prompt and not push.browser_open and P.current_document()[1].endswith("Arcing the Singularity.als")


def test_unsaved_changes_can_be_dropped(push):
    push.dirty = True
    out = call(server.load_set, None, "Set 12", unsaved="discard", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "answered the save-changes question with Don't Save" in out
    assert [0xB0, 24, 127] in push.sent and [0xB0, 27, 127] not in push.sent


def test_unsaved_changes_can_be_saved_first(push):
    push.dirty = True
    out = call(server.load_set, None, "Set 12", unsaved="save", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "with Save" in out and "WARNING" not in out
    assert [0xB0, 27, 127] in push.sent


def test_a_save_that_writes_nothing_is_flagged(push):
    push.dirty = True
    push.open_file = push.sets / "nowhere.als"
    push.open_file.write_bytes(b"")
    os.utime(push.open_file, (0, 0))
    out = call(server.load_set, None, "Set 12", unsaved="save", confirm=True)
    assert "WARNING: no new file for the Set that was open" in out


def test_without_unsaved_changes_the_answer_is_never_pressed(push):
    out = call(server.load_set, None, "Set 12", unsaved="discard", confirm=True)
    assert out.startswith("Loaded") and not any(d[1] in (24, 26, 27) for d in push.sent if d[0] == 0xB0)


def test_an_unknown_unsaved_answer_is_refused(push):
    assert call(server.load_set, None, "Set 12", unsaved="maybe", confirm=True).startswith("Error: unsaved must be")
    assert push.sent == []


def test_the_wrong_set_loading_is_an_error(push):
    # a set the browser lists first but whose folder is older than the others
    original = push.entries
    push.entries = lambda: [original()[1]] + original()
    out = call(server.load_set, None, "Set 12-1", confirm=True)
    assert out.startswith("Error: Live loaded") and "not 'Set 12-1'" in out


# --------------------------------------------------------------------------- save_set

def test_save_set_previews_without_pressing(push):
    out = call(server.save_set, None)
    assert out.startswith("NOT SAVED") and "Arcing the Singularity.als" in out and push.sent == []


def test_save_set_presses_save_and_finds_the_written_file(push):
    out = call(server.save_set, None, confirm=True)
    assert push.sent == [[0xB0, 82, 127], [0xB0, 82, 0]]
    assert out.startswith("Saved: ") and "Set 12-1.als written (the Save light went off)" in out


def test_save_with_nothing_to_save_says_so(push):
    # measured on the Push: a clean Set's Save press changes no light and writes nothing
    push.saves = False
    out = call(server.save_set, None, confirm=True)
    assert out.startswith("Not saved: the Save light did not change") and "no unsaved changes" in out


def test_no_file_written_is_never_reported_as_saved(push, monkeypatch):
    # the light went off but no file appeared (a question on the Push's screen, say)
    monkeypatch.setattr(P, "send", lambda steps, listen=0.0, until_cc=None: [[0.1, [0xB0, P.CC_SAVE, 0]]])
    out = call(server.save_set, None, confirm=True)
    assert out.startswith("Error: no Set file was written") and "Do not assume the Set is saved" in out


def test_the_set_tools_are_registered_with_the_right_hints():
    import asyncio
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert tools["list_sets"].annotations.readOnlyHint and tools["which_set"].annotations.readOnlyHint
    assert not tools["load_set"].annotations.readOnlyHint and not tools["save_set"].annotations.readOnlyHint
    assert "confirm" in json.dumps(tools["load_set"].inputSchema)
