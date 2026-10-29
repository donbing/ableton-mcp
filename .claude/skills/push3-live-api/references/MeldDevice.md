# Live.MeldDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## MeldDevice.MeldDevice

This class represents a Meld device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `mono_poly` `int`† (rw, listenable): Returns the mode of Polyphony
- `poly_voices` `int`† (rw, listenable): Return the Poly Voice count
- `selected_engine` `bool`† (rw, listenable): Return what Voice Engine is selected
- `unison_voices` `int`† (rw, listenable): Return the Unison Voice count
