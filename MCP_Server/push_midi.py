"""Press Push 3 buttons from software: send MIDI into the Push3 UI process and read the lights it sends back.

On a Push 3 in standalone mode the hardware's buttons, pads and encoders reach the Push3 UI process
(which runs Live's Push screens) on the ALSA sequencer port "Ableton Internal Input" (129:0 on Live
12.4.15), and the UI drives the lights through "Ableton Internal Output" (130:0). Writing the bytes the
hardware sends to that input is the same as pressing the button. Measured on the Push (2026-10-29).

This file runs under the Push's system Python (/usr/bin/python3, which ships python-rtmidi); the MCP
server's own environment has no rtmidi, so push_ui.py runs it as a subprocess:

    python3 -I push_midi.py '{"steps": [[delay, [byte, ...]], ...], "listen": seconds, "until_cc": cc,
                              "until_value": value}'

Each step waits `delay` seconds, then sends its message. After the last step it keeps listening for
`listen` seconds, or until a light message for controller `until_cc` arrives (with `until_value`, one
with that value). The messages in "release" are sent last whatever happens, so a pad held down is let
go even if a step fails. It prints
{"lights": [[seconds, [byte, ...]], ...]}: every message the UI sent to the lights from just before the
first step, with seconds since then. It imports nothing outside the standard library and rtmidi.

With "pads": {"wait": s, "quiet": s, "max": s} it also reads the hardware's own pad port ("Ableton
Push 3 Live Port", 16:0, which the UI reads too: ALSA gives every reader a copy) and, after the steps,
keeps listening for the user to play: until no pad has gone down `wait` seconds after the steps, or
every pad is up and nothing happened for `quiet` seconds, or `max` seconds. The reply then also has
"pads": the pad note-ons and note-offs (36-99, any channel: the pads are MPE, a channel per press) and
"steps_end": when the last step was sent. Our own presses go to the UI's input, so they never show up
here. Measured on the Push (2026-10-30): the pads send 36 bottom left to 99 top right.

We send from an ALSA port nobody can subscribe to (HiddenOut, through libasound with ctypes), so Live
does not hear our raw bytes. With "live_log" (Live's Log.txt) it first waits for Live's MIDI rescan
that opening ports sets off, so no note is held across it.
"""

import json
import sys
import time

INPUT_PORT = "Ableton Internal Input"
LIGHTS_PORT = "Ableton Internal Output"
PADS_PORT = "Ableton Push 3 Live Port"
FIRST_PAD, LAST_PAD = 36, 99
# Live's rescan comes about 1.0 s after a port appears and takes ~25 ms (measured 2026-10-30)
RESCAN_TIMEOUT = 3.0
# and a chord pressed right after it still never ended in Live; 2 s after it, it did (Capture MIDI)
AFTER_RESCAN = 2.0


def _port(midi, name):
    for i, port in enumerate(midi.get_ports()):
        if name in port:
            return i
    return None


class HiddenOut:
    """Sends to one ALSA port from a port of our own that nobody can subscribe to. Live takes every
    subscribable port as a track input (Track=on), so with rtmidi's MidiOut it played our raw pad
    numbers (36-99) as notes under the Push's own (measured with Capture MIDI 2026-10-30)."""

    QUEUE_DIRECT = 253

    def __init__(self, name):
        import ctypes
        self.ctypes, self.asound = ctypes, ctypes.CDLL("libasound.so.2")
        self.seq, self.coder = ctypes.c_void_p(), ctypes.c_void_p()
        if self.asound.snd_seq_open(ctypes.byref(self.seq), b"default", 1, 0) < 0:  # output only
            raise OSError("no ALSA sequencer")
        self.asound.snd_seq_set_client_name(self.seq, b"AbletonMCP pads")
        # capability READ without SUBS_READ: we can send from it, nobody can subscribe to it
        self.port = self.asound.snd_seq_create_simple_port(self.seq, b"AbletonMCP pads", 1, 1 << 20)
        self.dest = self._find(name)
        self.asound.snd_midi_event_new(16, ctypes.byref(self.coder))
        self.event = (ctypes.c_ubyte * 28)()  # snd_seq_event_t

    def _find(self, name):
        ctypes, asound = self.ctypes, self.asound
        cinfo, pinfo = ctypes.c_void_p(), ctypes.c_void_p()
        asound.snd_seq_client_info_malloc(ctypes.byref(cinfo))
        asound.snd_seq_port_info_malloc(ctypes.byref(pinfo))
        asound.snd_seq_port_info_get_name.restype = ctypes.c_char_p
        asound.snd_seq_client_info_set_client(cinfo, -1)
        while asound.snd_seq_query_next_client(self.seq, cinfo) >= 0:
            client = asound.snd_seq_client_info_get_client(cinfo)
            asound.snd_seq_port_info_set_client(pinfo, client)
            asound.snd_seq_port_info_set_port(pinfo, -1)
            while asound.snd_seq_query_next_port(self.seq, pinfo) >= 0:
                if name in asound.snd_seq_port_info_get_name(pinfo).decode(errors="replace"):
                    return client, asound.snd_seq_port_info_get_port(pinfo)
        return None

    def send_message(self, data):
        ctypes, event = self.ctypes, self.event
        ctypes.memset(event, 0, len(event))
        self.asound.snd_midi_event_reset_encode(self.coder)
        self.asound.snd_midi_event_encode(self.coder, (ctypes.c_ubyte * len(data))(*data), len(data), event)
        event[3] = self.QUEUE_DIRECT  # queue
        event[13] = self.port  # source port (the client is filled in by ALSA)
        event[14], event[15] = self.dest
        self.asound.snd_seq_event_output_direct(self.seq, event)

    def close_port(self):
        self.asound.snd_midi_event_free(self.coder)
        self.asound.snd_seq_close(self.seq)


def open_output(name):
    """Our way into the UI's input `name`, or None when there is no such port."""
    out = HiddenOut(name)
    if out.dest is None:
        out.close_port()
        return None
    return out


def wait_for_rescan(log_path, since, timeout=RESCAN_TIMEOUT):
    """Live rescans its MIDI devices about 1 s after any ALSA port appears or goes, closing and
    reopening all of them, the Push UI's own input to Live included: a note held across it never
    gets its note-off (the first demo chord rang on). Wait until Live's log says the rescan after
    `since` (time.time()) is over, at most `timeout` s."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(since)) + ("%.6f" % (since % 1))[1:]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 20000))
                tail = f.read().decode("utf-8", "replace")
        except OSError:
            return False
        for line in tail.splitlines():
            if "End OpenAllActivatedDevices" in line and line[:26] > stamp:
                return True
        time.sleep(0.05)
    return False


def run(request):
    import rtmidi

    watch = request.get("pads")
    opened_at = time.time()
    out, lights = open_output(INPUT_PORT), rtmidi.MidiIn()
    if out is None:
        return {"error": "no MIDI port named '%s' (is Live running on this Push?)" % INPUT_PORT}
    ports = [(lights, LIGHTS_PORT)]
    if watch:
        pad_in = rtmidi.MidiIn()
        pad_in.ignore_types(sysex=True, timing=True, active_sense=True)
        ports.append((pad_in, PADS_PORT))
    for midi, name in ports:
        index = _port(midi, name)
        if index is None:
            out.close_port()
            return {"error": "no MIDI port named '%s' (is Live running on this Push?)" % name}
        midi.open_port(index)
    if "live_log" in request:
        if not (request["live_log"] and wait_for_rescan(request["live_log"], opened_at)):
            time.sleep(max(0.0, opened_at + RESCAN_TIMEOUT - time.time()))
        time.sleep(AFTER_RESCAN)
    got, pads, start = [], [], time.monotonic()
    until, until_value = request.get("until_cc"), request.get("until_value")

    def drain():
        """Collect what has arrived; True once the light for until_cc has changed (to until_value)."""
        while True:
            message = lights.get_message()
            if not message:
                break
            got.append([round(time.monotonic() - start, 3), message[0]])
        while watch:
            message = pad_in.get_message()
            if not message:
                break
            d = message[0]
            if len(d) == 3 and d[0] & 0xF0 in (0x80, 0x90) and FIRST_PAD <= d[1] <= LAST_PAD:
                pads.append([round(time.monotonic() - start, 3), d])
        return until is not None and any(len(d) == 3 and d[0] & 0xF0 == 0xB0 and d[1] == until
                                         and until_value in (None, d[2]) for _, d in got)

    def played(after):
        """Whether the user is done: (pressed anything since `after`, every pad up again)."""
        down = set()
        for t, d in pads:
            if t >= after:
                if d[0] & 0xF0 == 0x90 and d[2]:
                    down.add(d[1])
                else:
                    down.discard(d[1])
        return any(t >= after for t, _ in pads), not down

    steps_end = 0.0
    try:
        for delay, data in request.get("steps", []):
            end = time.monotonic() + float(delay)
            while time.monotonic() < end:
                drain()
                time.sleep(0.005)
            out.send_message(data)
        steps_end = time.monotonic() - start
        end = time.monotonic() + float(request.get("listen", 0))
        while time.monotonic() < end:
            if drain():
                break
            time.sleep(0.01)
        drain()
        if watch:
            began = time.monotonic()
            while time.monotonic() - began < float(watch["max"]):
                drain()
                any_played, all_up = played(steps_end)
                quiet_since = (pads[-1][0] + start) if pads and any_played else began
                if not any_played and time.monotonic() - began >= float(watch["wait"]):
                    break
                if any_played and all_up and time.monotonic() - quiet_since >= float(watch["quiet"]):
                    break
                time.sleep(0.005)
    finally:
        for data in request.get("release", []):
            out.send_message(data)
        out.close_port()
        lights.close_port()
        if watch:
            pad_in.close_port()
    if watch:
        return {"lights": got, "pads": pads, "steps_end": round(steps_end, 3)}
    return {"lights": got}


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.argv[1]))))
