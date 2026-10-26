# Live.Device

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Device.Device

This class represents a MIDI or Audio DSP-Device in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `can_compare_ab` `bool`† (r): Returns true if the Device has the capability to AB compare.
- `can_have_chains` `bool`† (r): Returns true if the device is a rack.
- `can_have_drum_pads` `bool`† (r): Returns true if the device is a drum rack.
- `canonical_parent` `Track.Track`† (r): Get the canonical parent of the Device.
- `class_display_name` `str`† (r): Return const access to the name of the device's class name as displayed in Live's browser and device chain
- `class_name` `str`† (r): Return const access to the name of the device's class.
- `is_active` `bool`† (r, listenable): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` `bool`† (rw, listenable): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float`† (r, listenable): Returns the latency of the device in ms.
- `latency_in_samples` `int`† (r, listenable): Returns the latency of the device in samples.
- `name` `str`† (rw, listenable): Return access to the name of the device.
- `parameters` `Device.ATimeableValueVector`† (r, listenable): Const access to the list of available automatable parameters for this device.
- `type` `Device.DeviceType`† (r): Return the type of the device.
- `view` `Device.Device.View`† (r): Representing the view aspects of a device.

Methods:

- `save_preset_to_compare_ab_slot() -> None`: Saves the current state of the device to the compare AB slot. Only relevant if can_compare_ab, otherwise throws.
- `store_chosen_bank(arg2: int, arg3: int) -> None`: Set the selected bank in the device for persistency.

## Device.ATimeableValueVector

Not constructable from Python. Iterable.

## Device.Device.View

Representing the view aspects of a device.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Device.Device`† (r): Get the canonical parent of the View.
- `is_collapsed` `bool`† (rw, listenable): Get/Set/Listen if the device is shown collapsed in the device chain.

## Enums

- `DeviceType`: undefined=0, instrument=1, audio_effect=2, midi_effect=4
