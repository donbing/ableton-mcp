# Live.MeldDevice

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## MeldDevice.MeldDevice

This class represents a Meld device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_active` `bool`† (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` `bool`† (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float`† (r): Returns the latency of the device in ms.
- `latency_in_samples` `int`† (r): Returns the latency of the device in samples.
- `mono_poly` `int`† (rw, listenable): Returns the mode of Polyphony
- `name` `str`† (rw): Return access to the name of the device.
- `parameters` `Device.ATimeableValueVector`† (r): Const access to the list of available automatable parameters for this device.
- `poly_voices` `int`† (rw, listenable): Return the Poly Voice count
- `selected_engine` `bool`† (rw, listenable): Return what Voice Engine is selected
- `unison_voices` `int`† (rw, listenable): Return the Unison Voice count
