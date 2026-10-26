# Live.MaxDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## MaxDevice.MaxDevice

This class represents a Max for Live device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `audio_inputs` (r, listenable): Const access to a list of all audio inputs of the device.
- `audio_outputs` (r, listenable): Const access to a list of all audio outputs of the device.
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw) *(new)*: Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `midi_inputs` (r, listenable): Const access to a list of all midi outputs of the device.
- `midi_outputs` (r, listenable): Const access to a list of all midi outputs of the device.
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `bank_parameters_changed` (r, listenable)

Methods:

- `get_bank_count() -> int`: Get the number of parameter banks. This is related to hardware control surfaces.
- `get_bank_name(arg2: int) -> str`: Get the name of a parameter bank given by index. This is related to hardware control surfaces.
- `get_bank_parameters(arg2: int) -> list`: Get the indices of parameters of the given bank index. Empty slots are marked as -1. Bank index -1 refers to the best-of bank. This function is related to hardware control surfaces.
- `get_value_item_icons(arg2: DeviceParameter.DeviceParameter) -> list`: Get a list of icon identifier strings for a list parameter's values.An empty string is given where no icon should be displayed.An empty list is given when no icons should be displayed.This is related to hardware control surfaces.
