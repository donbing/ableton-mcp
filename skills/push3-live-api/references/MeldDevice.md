# Live.MeldDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## MeldDevice.MeldDevice

This class represents a Meld device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `mono_poly` (rw, listenable): Returns the mode of Polyphony
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `poly_voices` (rw, listenable): Return the Poly Voice count
- `selected_engine` (rw, listenable): Return what Voice Engine is selected
- `unison_voices` (rw, listenable): Return the Unison Voice count
