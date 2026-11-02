"""Runs on the Push, piped over SSH by board.sh, with the MCP server's Python for its hidden MIDI port.

Live holds the board's raw MIDI port, so CCs go through the ALSA sequencer from a port Live can't subscribe to
(HiddenOut), which keeps them out of Live's tracks. All of them are on channel 16.

    update [off]       Wi-Fi update mode (CC119)
    calibrate [off]    calibration mode (CC118)
    restart            restart the board (CC117)
    split [NOTE|off]   left-hand colour for play notes below NOTE (CC116, value = the note): Live's names
                       (C3 = MIDI 60, the default; F#2, Bb1) or a MIDI number. Saved on the board.
    sparks [off]       each play note throws sparks along the strip (CC115). Saved on the board.
    restart-test [N]   restart N times (10); after each, check the Push sets the board up again (USB
                       configuration and MIDI port), following it through any restarts of its own: when the
                       Push refuses it ("can't set config #1, error -32"), the board restarts itself after 3 s.
                       Counts those refusals. Fails if the board stays off the Push.
"""
import glob
import sys
import time

from MCP_Server.push_midi import open_output

PORT = "FP10 Lights MIDI 1"
CCS = {"update": 119, "calibrate": 118, "restart": 117, "split": 116, "sparks": 115}
NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_number(text):
    """A MIDI note from Live's names (C3 = 60, F#2, Bb-1) or a number."""
    if text.isdigit():
        n = int(text)
    else:
        name = text[0].upper()
        if name not in NOTE_NAMES:
            raise SystemExit("not a note: %s" % text)
        rest = text[1:]
        shift = 1 if rest[:1] == "#" else -1 if rest[:1] == "b" else 0
        rest = rest[1:] if shift else rest
        try:
            n = NOTE_NAMES[name] + shift + 12 * (int(rest) + 2)
        except ValueError:
            raise SystemExit("not a note: %s" % text)
    if not 1 <= n <= 127:
        raise SystemExit("note out of range (1-127): %s" % text)
    return n
MAX_SELF_RESTARTS = 5


def send_cc(cc, value):
    out = open_output(PORT)
    if out is None:
        raise SystemExit("FP10 Lights is not connected to the Push")
    out.send_message([0xBF, cc, value])
    out.close_port()


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def board():
    """(USB path, device number, configuration) of the board, or None. The configuration is "" while the Push
    hasn't set it up, which is what a refusal leaves."""
    for d in glob.glob("/sys/bus/usb/devices/*"):
        if read(d + "/product") == "FP10 Lights":
            return d.rsplit("/", 1)[1], int(read(d + "/devnum")), read(d + "/bConfigurationValue")
    return None


def wait(test, timeout):
    end = time.time() + timeout
    while time.time() < end:
        result = test()
        if result:
            return result
        time.sleep(0.05)
    return None


def has_port():
    out = open_output(PORT)
    if out is None:
        return False
    out.close_port()
    return True


def follow(devnum, started):
    """Wait for the board after it left as device `devnum`: until a later device is set up, through refusals
    and the board's own restarts. Returns (device, refusals) or (None, refusals)."""
    refusals = 0
    while True:
        dev = wait(lambda: (b := board()) and b[1] != devnum and b, 10)
        if not dev:
            return None, refusals
        if wait(lambda: (b := board()) and b[1] == dev[1] and b[2], 2):
            return dev, refusals
        refusals += 1
        print("   refused at %.1f s (device %d)" % (time.time() - started, dev[1]))
        if refusals > MAX_SELF_RESTARTS:
            return None, refusals
        devnum = dev[1]


def restart_test(count):
    first = board()
    if not first or not first[2]:
        raise SystemExit("FP10 Lights isn't set up on the Push: replug it first")
    refusals = 0
    for i in range(1, count + 1):
        before = board()
        started = time.time()
        send_cc(CCS["restart"], 127)
        dev, refused = follow(before[1], started)
        refusals += refused
        if not dev:
            print("%d: didn't come back (refused %d times)" % (i, refused))
            return False, refusals, i
        if not wait(has_port, 10):
            print("%d: set up, but no MIDI port" % i)
            return False, refusals, i
        print("%d: back in %.1f s (device %d)" % (i, time.time() - started, dev[1]))
        time.sleep(3)  # Live rescans its MIDI ports about 1 s after one appears
    return True, refusals, count


def main(args):
    if not args:
        raise SystemExit(__doc__)
    cmd = args[0]
    if cmd == "split":
        arg = args[1] if len(args) > 1 else "C3"
        note = 0 if arg == "off" else note_number(arg)
        send_cc(CCS[cmd], note)
        print("split off" if not note else "split at %s (MIDI %d): notes below it light the left-hand colour"
              % (arg, note))
    elif cmd in ("update", "calibrate", "sparks"):
        off = len(args) > 1 and args[1] == "off"
        send_cc(CCS[cmd], 0 if off else 127)
        print("%s %s" % (cmd, "off" if off else "on"))
    elif cmd == "restart":
        send_cc(CCS[cmd], 127)
        print(cmd)
    elif cmd == "restart-test":
        ok, refusals, done = restart_test(int(args[1]) if len(args) > 1 else 10)
        if ok:
            print("passed: %d restarts; the Push refused the board %d times, and it restarted itself each time"
                  % (done, refusals))
        else:
            print("FAILED at restart %d; %d refusals so far" % (done, refusals))
        sys.exit(0 if ok else 1)
    else:
        raise SystemExit(__doc__)


main(sys.argv[1:])
