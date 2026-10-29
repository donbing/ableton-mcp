"""Open and save Live Sets on a Push 3 in standalone mode by pressing its own buttons.

Live's Python API can neither open nor save a Set. On the Push the MCP server runs on the same
machine as Live, so it can press the Push's buttons instead (push_midi.py sends the MIDI) and check
the results in Live's log and on disk. Measured on Push 3 standalone, Live 12.4.15 (2026-10-29):

- Save is CC82. Its light is on while the Set has unsaved changes and goes off (value 0) on saving;
  the .als is written within about 3 s.
- The Sets button CC80 opens the Set browser (its light goes to 127) on the top entry; pressed while
  the browser is open it goes back to the previous mode (light 14).
- The browser lists every project folder in the Sets folder, newest first ([Autosave] ones too).
- The jog wheel CC70 moves the highlight one entry per message (1 = down, 127 = up), wrapped in its
  touch note 11; pressing it (CC94) loads the highlighted Set.
- If the open Set has unsaved changes, the jog press puts up "Save changes before closing?" on the
  Push's screen (not a Live dialog) and lights the buttons below it: Don't Save CC24 and Cancel CC26
  white (122), Save CC27 green (126). Cancel goes back to the browser.
- If the loaded Set refers to files Live cannot find, the Push says "some referenced media files are
  missing" (fix them with the File Manager): about 2 s after the load turns every light off, only the
  OK button below the screen, CC27, lights green (126), and nothing answers the Sets button until OK
  is pressed. Live's log has a line `Exception: The file "<name>" could not be opened.` for each.
  Pressing OK closes it: the Push relights every button, the Sets light back at 14.
- "+ New Set" is the second button above the screen (CC103) while the browser is open; it asks the
  same save question first, then Live loads its default template.
- Live's Log.txt says `Loading document "<path>"` for every Set it opens (and for the default track
  a new track is built from, under Defaults/, which is skipped).
"""

import glob
import json
import os
import re
import subprocess
import time

SETS_DIR = os.environ.get("ABLETON_MCP_SETS_DIR", "/data/Music/Ableton/Sets")
LIVE_PREFS_DIR = os.environ.get("ABLETON_MCP_LIVE_PREFS_DIR", os.path.expanduser("~/.config/Ableton"))
PUSH_PYTHON = os.environ.get("ABLETON_MCP_PUSH_PYTHON", "/usr/bin/python3")
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "push_midi.py")

CC_SETS, CC_SAVE, CC_JOG, CC_JOG_PRESS, NOTE_JOG_TOUCH = 80, 82, 70, 94, 11
SETS_LIGHT_OPEN = 127
# the buttons below the screen that "Save changes before closing?" lights: Don't Save (white, 122),
# Cancel (white, 122) and Save (green, 126)
CC_PROMPT_DONT_SAVE, CC_PROMPT_CANCEL, CC_PROMPT_SAVE = 24, 26, 27
# the second button above the screen is "+ New Set" while the Set browser is open (lit 122)
CC_NEW_SET = 103
PROMPT_SAVE_GREEN = 126
# the log is read from its end; a load is far less than this far back
LOG_TAIL_BYTES = 1 << 20
LOADING = re.compile(r'^(\S+): info: Loading document "(.*)"\s*$')
NOT_OPENED = re.compile(r'^(\S+): info: Exception: The file "(.*)" could not be opened\.\s*$')
# the light the missing-media warning puts on its OK button, the same green as the save question's Save
CC_MEDIA_OK = CC_PROMPT_SAVE
PROJECT_SUFFIX = " Project"

# the clock and sleep, replaceable in tests
now = time.time
sleep = time.sleep


class PushError(Exception):
    pass


# ---------------------------------------------------------------------------- MIDI

def press(cc):
    return [[0.0, [0xB0, cc, 127]], [0.2, [0xB0, cc, 0]]]


def jog(steps):
    """Steps down (positive) or up (negative) the browser, one jog-wheel detent each."""
    value = 1 if steps > 0 else 127
    clicks = [[0.2, [0xB0, CC_JOG, value]] for _ in range(abs(steps))]
    return [[0.0, [0x90, NOTE_JOG_TOUCH, 127]]] + clicks + [[0.2, [0x80, NOTE_JOG_TOUCH, 0]]]


def send(steps, listen=0.0, until_cc=None, until_value=None):
    """Run push_midi.py under the Push's system Python; returns the light messages it saw."""
    if not os.path.isfile(PUSH_PYTHON):
        raise PushError("no %s here: Set loading and saving only work where the server runs on the Push 3"
                        % PUSH_PYTHON)
    request = json.dumps({"steps": steps, "listen": listen, "until_cc": until_cc, "until_value": until_value})
    timeout = 10.0 + listen + sum(delay for delay, _ in steps)
    done = subprocess.run([PUSH_PYTHON, "-I", HELPER, request], capture_output=True, text=True, timeout=timeout)
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise PushError("the MIDI helper failed: %s" % (done.stderr.strip() or done.stdout.strip() or done.returncode))
    if "error" in result:
        raise PushError(result["error"])
    return result["lights"]


def last_light(lights, cc):
    values = [d[2] for _, d in lights if len(d) == 3 and d[0] & 0xF0 == 0xB0 and d[1] == cc]
    return values[-1] if values else None


def save_prompt_shown(lights):
    """Whether these lights are the Push putting up "Save changes before closing?"."""
    return (last_light(lights, CC_PROMPT_SAVE) == PROMPT_SAVE_GREEN
            and last_light(lights, CC_PROMPT_CANCEL) not in (None, 0)
            and last_light(lights, CC_PROMPT_DONT_SAVE) not in (None, 0))


def media_warning_shown(lights):
    """Whether these lights are the Push saying "some referenced media files are missing": OK green
    on its own, without the save question's other two answers."""
    return (last_light(lights, CC_MEDIA_OK) == PROMPT_SAVE_GREEN
            and last_light(lights, CC_PROMPT_CANCEL) in (None, 0)
            and last_light(lights, CC_PROMPT_DONT_SAVE) in (None, 0))


def dismiss_media_warning():
    """Press OK on the missing-media warning; True when the Push went back to its mode (the Sets
    light came back)."""
    return last_light(send(press(CC_MEDIA_OK), listen=3.0, until_cc=CC_SETS), CC_SETS) is not None


def open_set_browser():
    """Press Sets until its light says the browser has just opened (so the top entry is highlighted)."""
    for attempt in range(2):
        value = last_light(send(press(CC_SETS), listen=1.5, until_cc=CC_SETS), CC_SETS)
        if value == SETS_LIGHT_OPEN:
            return attempt + 1
        if value is None:
            raise PushError("the Sets button's light did not change after pressing it, so the Push's mode is "
                            "unknown; nothing more was sent. The Push may be showing a message (\"some "
                            "referenced media files are missing\" waits for OK): ask the user to look at its screen")
        # it was open already and has closed: one more press opens it on the top entry
    raise PushError("the Set browser did not open after two presses of Sets; nothing more was sent")


def close_set_browser(lights):
    """Close the browser that `lights` (from the last press) left open: press Sets until its light no
    longer says open. Returns True when closed, False when the light never said either way."""
    value = last_light(lights, CC_SETS)
    for _ in range(2):
        if value is not None and value != SETS_LIGHT_OPEN:
            return True
        value = last_light(send(press(CC_SETS), listen=1.5, until_cc=CC_SETS), CC_SETS)
    return value is not None and value != SETS_LIGHT_OPEN


# ---------------------------------------------------------------------------- Sets on disk

def list_sets(sets_dir=None):
    """The Sets folder's projects in the browser's order (newest first): dicts with position (1 = top),
    name, folder, als (the Set file, or None), modified (epoch seconds)."""
    sets_dir = sets_dir or SETS_DIR
    try:
        names = os.listdir(sets_dir)
    except FileNotFoundError:
        raise PushError("no Sets folder at %s" % sets_dir)
    rows = []
    for entry in names:
        folder = os.path.join(sets_dir, entry)
        if entry.startswith(".") or not os.path.isdir(folder):
            continue
        name = entry[:-len(PROJECT_SUFFIX)] if entry.endswith(PROJECT_SUFFIX) else entry
        als = os.path.join(folder, name + ".als")
        if not os.path.isfile(als):
            found = sorted(glob.glob(os.path.join(glob.escape(folder), "*.als")))
            als = found[0] if found else None
        rows.append({"name": name, "folder": folder, "als": als, "modified": os.path.getmtime(folder)})
    rows.sort(key=lambda r: r["modified"], reverse=True)
    for i, row in enumerate(rows):
        row["position"] = i + 1
    return rows


def find_set(name, sets):
    exact = [s for s in sets if s["name"] == name]
    matches = exact or [s for s in sets if s["name"].lower() == name.strip().lower()]
    if len(matches) == 1:
        return matches[0]
    raise PushError("no Set named '%s'%s. The Sets are: %s"
                    % (name, " (more than one matches)" if matches else "", ", ".join(s["name"] for s in sets)))


def set_files_written_since(since, sets_dir=None):
    """Set files (not Backup/ copies) modified at or after `since`, newest first."""
    pattern = os.path.join(glob.escape(sets_dir or SETS_DIR), "*", "*.als")
    files = [(os.path.getmtime(f), f) for f in glob.glob(pattern)]
    return [f for t, f in sorted(files, reverse=True) if t >= since]


# ---------------------------------------------------------------------------- Live's log

def live_log(prefs_dir=None):
    """The newest Live version's Log.txt."""
    def version(path):
        return [int(n) for n in re.findall(r"\d+", os.path.basename(os.path.dirname(path)))]
    logs = glob.glob(os.path.join(glob.escape(prefs_dir or LIVE_PREFS_DIR), "Live *", "Log.txt"))
    if not logs:
        raise PushError("no Live Log.txt under %s" % (prefs_dir or LIVE_PREFS_DIR))
    return max(logs, key=version)


def loaded_documents(log_path):
    """(timestamp text, path) of every `Loading document` line in the log's last megabyte, oldest first."""
    with open(log_path, "rb") as f:
        f.seek(max(0, os.path.getsize(log_path) - LOG_TAIL_BYTES))
        text = f.read().decode("utf-8", "replace")
    # Live logs the default track it builds a new track from (".../Defaults/Creating Tracks/MIDI
    # Track/Default MIDI Track.als") the same way; those are not Sets
    return [m.groups() for m in map(LOADING.match, text.splitlines()) if m and "/Defaults/" not in m.group(2)]


def current_document(log_path=None):
    """(timestamp text, path) of the Set Live loaded last, or None."""
    docs = loaded_documents(log_path or live_log())
    return docs[-1] if docs else None


def files_not_opened(log_path, after):
    """The file names Live logged it could not open after the `after` (timestamp, path) entry."""
    with open(log_path, "rb") as f:
        f.seek(max(0, os.path.getsize(log_path) - LOG_TAIL_BYTES))
        text = f.read().decode("utf-8", "replace")
    names = []
    for m in map(NOT_OPENED.match, text.splitlines()):
        if m and m.group(1) > after[0] and m.group(2) not in names:
            names.append(m.group(2))
    return names


def same_file(a, b):
    return bool(a and b) and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def is_template(path):
    return "/Templates/" in path or path.endswith("/DefaultLiveSet.als")


def wait_for_load(log_path, after, timeout=15.0):
    """The first (timestamp, path) Live logs loading after the `after` entry (None: any), or None
    within the timeout. Log timestamps are ISO times, so they compare as text."""
    deadline = now() + timeout
    while True:
        new = [d for d in loaded_documents(log_path) if after is None or d[0] > after[0]]
        if new:
            return new[0]
        if now() >= deadline:
            return None
        sleep(0.25)
