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
with that value). It prints
{"lights": [[seconds, [byte, ...]], ...]}: every message the UI sent to the lights from just before the
first step, with seconds since then. It imports nothing outside the standard library and rtmidi.
"""

import json
import sys
import time

INPUT_PORT = "Ableton Internal Input"
LIGHTS_PORT = "Ableton Internal Output"


def _port(midi, name):
    for i, port in enumerate(midi.get_ports()):
        if name in port:
            return i
    return None


def run(request):
    import rtmidi

    out, lights = rtmidi.MidiOut(), rtmidi.MidiIn()
    for midi, name in ((out, INPUT_PORT), (lights, LIGHTS_PORT)):
        index = _port(midi, name)
        if index is None:
            return {"error": "no MIDI port named '%s' (is Live running on this Push?)" % name}
        midi.open_port(index)
    got, start = [], time.monotonic()
    until, until_value = request.get("until_cc"), request.get("until_value")

    def drain():
        """Collect what has arrived; True once the light for until_cc has changed (to until_value)."""
        while True:
            message = lights.get_message()
            if not message:
                break
            got.append([round(time.monotonic() - start, 3), message[0]])
        return until is not None and any(len(d) == 3 and d[0] & 0xF0 == 0xB0 and d[1] == until
                                         and until_value in (None, d[2]) for _, d in got)

    try:
        for delay, data in request.get("steps", []):
            end = time.monotonic() + float(delay)
            while time.monotonic() < end:
                drain()
                time.sleep(0.005)
            out.send_message(data)
        end = time.monotonic() + float(request.get("listen", 0))
        while time.monotonic() < end:
            if drain():
                break
            time.sleep(0.01)
        drain()
    finally:
        out.close_port()
        lights.close_port()
    return {"lights": got}


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.argv[1]))))
