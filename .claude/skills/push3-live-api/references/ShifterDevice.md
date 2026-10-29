# Live.ShifterDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## ShifterDevice.ShifterDevice

This class represents a Shifter device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `pitch_bend_range` `int`† (rw, listenable): Return the pitch bend range for MIDI pitch mode
- `pitch_mode_index` `int`† (rw, listenable): Return the current pitch mode index
- `pitch_mode_list` `Base.StringVector`† (r): Return the current pitch mode list
