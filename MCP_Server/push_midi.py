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
"""

import json
import sys
import time

INPUT_PORT = "Ableton Internal Input"
LIGHTS_PORT = "Ableton Internal Output"
PADS_PORT = "Ableton Push 3 Live Port"
FIRST_PAD, LAST_PAD = 36, 99


def _port(midi, name):
    for i, port in enumerate(midi.get_ports()):
        if name in port:
            return i
    return None


def run(request):
    import rtmidi

    watch = request.get("pads")
    out, lights = rtmidi.MidiOut(), rtmidi.MidiIn()
    ports = [(out, INPUT_PORT), (lights, LIGHTS_PORT)]
    if watch:
        pad_in = rtmidi.MidiIn()
        pad_in.ignore_types(sysex=True, timing=True, active_sense=True)
        ports.append((pad_in, PADS_PORT))
    for midi, name in ports:
        index = _port(midi, name)
        if index is None:
            return {"error": "no MIDI port named '%s' (is Live running on this Push?)" % name}
        midi.open_port(index)
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
