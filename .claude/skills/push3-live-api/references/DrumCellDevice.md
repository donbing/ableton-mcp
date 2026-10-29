# Live.DrumCellDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## DrumCellDevice.DrumCellDevice

This class represents a DrumCell device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `gain` `float` (rw, listenable): Return the Gain value
- `is_active` `bool` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` `bool` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float` (r): Returns the latency of the device in ms.
- `latency_in_samples` `int` (r): Returns the latency of the device in samples.
- `name` `str` (rw): Return access to the name of the device.
- `parameters` `Device.ATimeableValueVector` (r): Const access to the list of available automatable parameters for this device.
