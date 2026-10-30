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
import time
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
TEMPLATE = "/opt/push3/products/live/Live/AppLive/Resources/Builtin/Templates/DefaultLiveSet.als"
# copied from the Push's log: creating a MIDI track logs the default track it is built from
TRACK_DEFAULT_LINE = ('2026-10-29T13:30:23.078080: info: Loading document "/data/Music/Ableton/Live 12 Core '
                      'Library/Defaults/Creating Tracks/MIDI Track/Default MIDI Track.als"\n')
LOAD_LINE = '2026-10-29T01:04:19.429789: info: Loading document "{path}"\n'
NOT_OPENED_LINE = '2026-10-29T01:04:19.456859: info: Exception: The file "{name}" could not be opened.\n'


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
        self.missing = []       # files the loaded Set refers to that Live cannot open
        self.warning = False    # the Push is showing "some referenced media files are missing"
        self.ok_works = True    # False: OK does not close the warning
        self.open_file = self.sets / "Arcing the Singularity Project" / "Arcing the Singularity.als"
        self.pending = None     # what the answered save question goes on to load

    def entries(self):
        return [s["als"] for s in P.list_sets(str(self.sets))]

    def send(self, steps, listen=0.0, until_cc=None, until_value=None):
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
            elif number in (P.CC_JOG_PRESS, P.CC_NEW_SET) and value == 127 and self.browser_open and self.dirty:
                # as measured: the Sets and Save lights go dark, the three answers light up
                self.prompt = True
                # the highlighted Set, as pressed: saving first can reorder the list under it
                self.pending = TEMPLATE if number == P.CC_NEW_SET else self.entries()[self.highlight]
                lights += [[0.05, [0xB0, 80, 0]], [0.05, [0xB0, 82, 0]], [0.05, [0xB0, 24, 122]],
                           [0.05, [0xB0, 26, 122]], [0.05, [0xB0, 27, 126]]]
            elif number == P.CC_JOG_PRESS and value == 127 and self.browser_open and self.loads:
                lights += self.load()
            elif number == P.CC_NEW_SET and value == 127 and self.browser_open and self.loads:
                lights += self.load(TEMPLATE)
            elif self.warning and number == 27 and value == 127 and self.ok_works:
                # as measured: OK relights every button, the Sets light at 14
                self.warning = False
                lights += [[0.04, [0x90, 80, 122]], [0.04, [0xB0, 80, 14]], [0.04, [0xB0, 27, 67]]]
            elif self.prompt and value == 127 and number in (24, 26, 27):
                self.prompt = False
                lights += [[0.05, [0xB0, 24, 0]], [0.05, [0xB0, 26, 0]], [0.05, [0xB0, 27, 0]]]
                if number == 26:
                    lights += [[0.05, [0xB0, 80, 127]], [0.05, [0xB0, 82, 127]]]
                    continue
                if number == 27:
                    os.utime(self.open_file, (self.clock.t + 1, self.clock.t + 1))
                self.dirty = False
                lights += self.load(self.pending)
            elif number == P.CC_SAVE and value == 127 and self.saves:
                lights.append([0.1, [0xB0, P.CC_SAVE, 0]])
                path = self.sets / "Set 12-1 Project" / "Set 12-1.als"
                os.utime(path, (self.clock.t + 1, self.clock.t + 1))
        self.clock.t += listen
        return lights

    def load(self, path=None):
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(LOAD_LINE.format(path=path or self.entries()[self.highlight]))
            for name in self.missing:
                f.write(NOT_OPENED_LINE.format(name=name))
        self.browser_open = False
        self.warning = bool(self.missing)
        # as measured: the load turns every light off, then the warning lights only OK, green
        return [[2.1, [0xB0, 49, 0]], [2.1, [0xB0, 27, 126]]] if self.missing else []


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


def fake_output(cls):
    """push_midi.open_output with cls's ports in place of ALSA's (the real one sends through libasound)."""
    return lambda name: cls() if any(name in p for p in cls.ports) else None


def test_the_helper_opens_the_ui_ports_by_name_and_stops_at_the_awaited_light(monkeypatch):
    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=FakeOut, MidiIn=FakeIn))
    monkeypatch.setattr(M, "open_output", fake_output(FakeOut))
    FakeOut.sent, FakeIn.queue = [], []
    FakePorts.replies = [[[0xB0, 80, 127], [0xB0, 107, 122]], []]
    result = M.run({"steps": P.press(80), "listen": 30, "until_cc": 80})
    assert FakeOut.sent == [[0xB0, 80, 127], [0xB0, 80, 0]]
    # it returned at once instead of listening for 30 s
    assert [d for _, d in result["lights"]] == [[0xB0, 80, 127], [0xB0, 107, 122]]


def test_the_helper_can_wait_for_one_value_of_a_light(monkeypatch):
    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=FakeOut, MidiIn=FakeIn))
    monkeypatch.setattr(M, "open_output", fake_output(FakeOut))
    FakeOut.sent, FakeIn.queue = [], []
    FakePorts.replies = [[[0xB0, 27, 0], [0xB0, 82, 0], [0xB0, 27, 126]], []]
    result = M.run({"steps": P.press(94), "listen": 30, "until_cc": 27, "until_value": 126})
    # it did not stop at the first CC27 message, and returned at once instead of listening for 30 s
    assert [d for _, d in result["lights"]] == [[0xB0, 27, 0], [0xB0, 82, 0], [0xB0, 27, 126]]


def test_the_helper_says_which_port_is_missing(monkeypatch):
    class NoUi(FakeOut):
        ports = ["Ableton Push 3:Ableton Push 3 Live Port 16:0"]
    monkeypatch.setitem(sys.modules, "rtmidi", types.SimpleNamespace(MidiOut=NoUi, MidiIn=FakeIn))
    monkeypatch.setattr(M, "open_output", fake_output(NoUi))
    assert "Ableton Internal Input" in M.run({"steps": []})["error"]


# --------------------------------------------------------------------------- Sets on disk and the log

def test_sets_are_listed_newest_first_like_the_browser(push):
    sets = P.list_sets()
    assert [(s["position"], s["name"]) for s in sets] == [
        (1, "Set 12-1"), (2, "Set 12"), (3, "Arcing the Singularity"), (4, "Diamond of Specter [Autosave]")]
    assert sets[1]["als"].endswith(os.path.join("Set 12 Project", "Set 12.als"))


def test_the_order_and_date_are_the_set_files_not_the_folders(push):
    # Push 3, 2026-10-30: Live made a Samples folder in an older project (its folder became the newest)
    # without saving it; the browser still listed it by its Set file's date
    folder = push.sets / "Arcing the Singularity Project"
    (folder / "Samples").mkdir()
    os.utime(folder, (push.clock.t, push.clock.t))
    sets = P.list_sets()
    assert [s["name"] for s in sets][:3] == ["Set 12-1", "Set 12", "Arcing the Singularity"]
    assert sets[2]["modified"] == os.path.getmtime(folder / "Arcing the Singularity.als")


def test_copies_in_a_projects_backup_folder_are_entries_too_and_ties_go_by_path(tmp_path):
    # the Push 3's Set browser on 2026-10-30, top to bottom: Remix, its two hand-named Backup copies (each
    # copied with its time kept, so tied with a Set), Original, Arcing; Live's stamped backups hidden
    sets = tmp_path / "Sets"

    def als(path, t):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"als")
        os.utime(path, ns=(t, t))

    remix, original = sets / "Play With Me (Remix) Project", sets / "Play With Me (Original) Project"
    als(remix / "Play With Me (Remix).als", 1793318289310454097)
    als(remix / "Backup" / "Collection of Meditation [Autosave] [2026-10-30 at rename].als", 1793318289310454097)
    als(remix / "Backup" / "Collection of Meditation [Autosave] [2026-10-29 235808].als", 1793310548310492349)
    als(remix / "Backup" / "Collection of Meditation [2026-10-29 before vocal edit].als", 1793302434229152757)
    als(original / "Play With Me (Original).als", 1793302434229152757)
    als(sets / "Arcing the Singularity Project" / "Arcing the Singularity.als", 1793243738000000000)
    rows = P.list_sets(str(sets))
    assert [(r["name"], r["copy"]) for r in rows] == [
        ("Play With Me (Remix)", False), ("Collection of Meditation [Autosave] [2026-10-30 at rename]", True),
        ("Collection of Meditation [2026-10-29 before vocal edit]", True), ("Play With Me (Original)", False),
        ("Arcing the Singularity", False)]
    assert P.find_set("Arcing the Singularity", rows)["position"] == 5
    assert "Collection" not in str(pytest.raises(P.PushError, P.find_set, "Nope", rows).value)


def test_a_project_without_a_set_file_goes_by_its_folder(push):
    folder = push.sets / "Empty Project"
    folder.mkdir()
    os.utime(folder, (push.clock.t, push.clock.t))
    assert P.list_sets()[0]["name"] == "Empty" and P.list_sets()[0]["als"] is None


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


def start_new_set(push, minutes_ago=30):
    """Live's log line for the template loading, `minutes_ago` before the fake clock's now."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000000", time.localtime(push.clock.t - 60 * minutes_ago))
    with open(push.log, "a", encoding="utf-8") as f:
        f.write('%s: info: Loading document "%s"\n' % (stamp, TEMPLATE))
    return stamp


def save_new_project(push, name, minutes_ago):
    """A project folder as the Push's first save of a new Set leaves it (as on 2026-10-29: the Set,
    Ableton Project Info, Samples/Recorded, and after a second save a Backup copy), all written
    `minutes_ago` before now."""
    folder = push.sets / (name + " Project")
    paths = [folder / (name + ".als"), folder / "Backup" / (name + " [2026-10-29 193353].als"),
             folder / "Ableton Project Info" / "Project8_1.cfg", folder / "Samples" / "Recorded" / "Vox 0005.wav"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    t = push.clock.t - 60 * minutes_ago
    for root, dirs, files in os.walk(folder):
        for entry in dirs + files:
            os.utime(os.path.join(root, entry), (t, t))
    os.utime(folder, (t, t))
    return str(paths[0])


def test_a_new_set_not_saved_yet_reads_as_new(push):
    start_new_set(push)
    assert "not saved under a name yet" in call(server.which_set, None)


def test_a_new_sets_first_save_is_found_on_disk(push):
    stamp = start_new_set(push, minutes_ago=30)
    als = save_new_project(push, "Collection of Meditation", minutes_ago=10)
    out = call(server.which_set, None)
    assert "Collection of Meditation.als (a new Set from the default template, started %s" % stamp[:19] in out
    assert "not saved" not in out
    assert P.first_saved_as(P.current_document()) == als
    listed = call(server.list_sets, None)
    assert listed.count("<- open") == 1
    assert "Collection of Meditation (saved" in [line for line in listed.splitlines() if "<- open" in line][0]
    assert "is already open" in call(server.load_set, None, "Collection of Meditation")


def test_a_project_older_than_the_new_set_is_not_its_save(push):
    # Arcing the Singularity was saved an hour or more before the template loaded
    start_new_set(push, minutes_ago=30)
    assert P.first_saved_as(P.current_document()) is None


def test_the_pushs_autosave_copies_are_not_a_save(push):
    start_new_set(push, minutes_ago=30)
    save_new_project(push, "Hazy Facade [Autosave]", minutes_ago=5)
    assert "not saved under a name yet" in call(server.which_set, None)


def test_two_new_projects_are_not_guessed_between(push):
    start_new_set(push, minutes_ago=30)
    save_new_project(push, "One", minutes_ago=10)
    save_new_project(push, "Two", minutes_ago=5)
    assert "not saved under a name yet" in call(server.which_set, None)


def test_a_set_loaded_by_name_is_not_looked_up_on_disk(push):
    save_new_project(push, "Newer", minutes_ago=1)
    assert P.first_saved_as(P.current_document()) is None
    assert "Arcing the Singularity.als (loaded" in call(server.which_set, None)


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


def test_a_silent_sets_light_says_to_look_at_the_screen(push):
    push.sets_light = False
    assert "media files are missing" in call(server.load_set, None, "Set 12", confirm=True)


def test_missing_media_is_named_and_left_for_the_user(push):
    push.missing = ["silence.wav"]
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "Live could not open: silence.wav." in out
    assert 'is showing "some referenced media files are missing"' in out and "press OK" in out
    # OK is the user's to press
    assert [0xB0, 27, 127] not in push.sent


def test_missing_media_can_be_answered_with_ok(push):
    push.missing = ["silence.wav"]
    out = call(server.load_set, None, "Set 12", missing_media="ok", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "silence.wav" in out and out.endswith("I pressed OK.")
    assert push.sent[-2:] == [[0xB0, 27, 127], [0xB0, 27, 0]] and not push.warning


def test_an_ok_that_changes_nothing_is_reported(push):
    push.missing, push.ok_works = ["silence.wav"], False
    out = call(server.load_set, None, "Set 12", missing_media="ok", confirm=True)
    assert "I pressed OK but its lights did not come back" in out


def test_ok_is_never_pressed_without_the_warning(push):
    out = call(server.load_set, None, "Set 12", missing_media="ok", confirm=True)
    assert out.startswith("Loaded") and [0xB0, 27, 127] not in push.sent


def test_an_unknown_missing_media_answer_is_refused(push):
    out = call(server.load_set, None, "Set 12", missing_media="maybe", confirm=True)
    assert out.startswith("Error: missing_media must be") and push.sent == []


def test_missing_media_after_saving_first_is_reported(push):
    push.dirty, push.missing = True, ["silence.wav"]
    out = call(server.load_set, None, "Set 12", unsaved="save", confirm=True)
    assert "with Save" in out and 'is showing "some referenced media files are missing"' in out


def test_files_the_log_could_not_open_are_named_even_without_the_light(push, monkeypatch):
    push.missing = ["silence.wav", "silence.wav", "kick.aif"]
    original = push.load
    monkeypatch.setattr(push, "load", lambda: original() and [])
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert "Live could not open: silence.wav, kick.aif." in out and "may be showing" in out


def test_only_files_logged_after_the_load_count(push):
    with open(push.log, "a", encoding="utf-8") as f:
        # from the Set loaded before
        f.write(NOT_OPENED_LINE.format(name="old.wav").replace("T01:04:19.456859", "T00:27:01.200000"))
    out = call(server.load_set, None, "Set 12", confirm=True)
    assert out.startswith("Loaded 'Set 12'") and "could not open" not in out


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


# --------------------------------------------------------------------------- closing the browser

def test_a_browser_already_closed_is_left_alone(push):
    assert P.close_set_browser([[0.1, [0xB0, 80, 14]]]) and push.sent == []


def test_an_open_browser_is_closed_and_the_light_checked(push):
    push.browser_open = True
    assert P.close_set_browser([[0.1, [0xB0, 80, 127]]])
    assert push.sent == [[0xB0, 80, 127], [0xB0, 80, 0]] and not push.browser_open


def test_a_silent_sets_light_is_reported_not_guessed(push):
    push.browser_open, push.sets_light = True, False
    assert not P.close_set_browser([[0.1, [0xB0, 80, 127]]])
    assert push.sent.count([0xB0, 80, 127]) == 2


# --------------------------------------------------------------------------- new_set and track defaults

def test_a_new_tracks_default_is_not_the_open_set(push):
    with open(push.log, "a", encoding="utf-8") as f:
        f.write(TRACK_DEFAULT_LINE)
    assert P.current_document()[1].endswith("Arcing the Singularity.als")


def test_new_set_previews_without_pressing(push):
    out = call(server.new_set, None)
    assert out.startswith("NOT STARTED") and "Arcing the Singularity.als" in out and push.sent == []


def test_new_set_presses_sets_then_new_set_and_checks_the_template_loaded(push):
    out = call(server.new_set, None, confirm=True)
    assert out.startswith("Loaded a new Set (pressed Sets once and New Set")
    assert push.sent == [[0xB0, 80, 127], [0xB0, 80, 0], [0xB0, 103, 127], [0xB0, 103, 0]]
    assert P.is_template(P.current_document()[1])
    assert "not saved under a name yet" in call(server.which_set, None)


def test_new_set_leaves_unsaved_changes_to_the_user(push):
    push.dirty = True
    out = call(server.new_set, None, confirm=True)
    assert out.startswith("Not loaded:") and "call new_set again" in out
    assert P.current_document()[1].endswith("Arcing the Singularity.als") and not push.browser_open


def test_new_set_can_drop_unsaved_changes(push):
    push.dirty = True
    out = call(server.new_set, None, unsaved="discard", confirm=True)
    assert "with Don't Save" in out and P.is_template(P.current_document()[1])
