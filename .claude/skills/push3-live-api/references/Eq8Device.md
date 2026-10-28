# Live.Eq8Device

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Eq8Device.Eq8Device

This class represents an Eq8 device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `edit_mode` `bool`† (rw, listenable): Access to Eq8's edit mode.
- `global_mode` `int`† (rw, listenable): Access to Eq8's global mode.
- `is_active` `bool`† (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` `bool`† (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float`† (r): Returns the latency of the device in ms.
- `latency_in_samples` `int`† (r): Returns the latency of the device in samples.
- `name` `str`† (rw): Return access to the name of the device.
- `oversample` `bool`† (rw, listenable): Access to Eq8's oversample value.
- `parameters` `Device.ATimeableValueVector`† (r): Const access to the list of available automatable parameters for this device.

## Eq8Device.Eq8Device.View

Representing the view aspects of an Eq8 device.

Base: Device.Device.View, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_collapsed` `bool`† (rw): Get/Set/Listen if the device is shown collapsed in the device chain.
- `selected_band` `int`† (rw, listenable): Access to the selected filter band.

## Enums

- `EditMode`: a=0, b=1
- `GlobalMode`: stereo=0, left_right=1, mid_side=2
