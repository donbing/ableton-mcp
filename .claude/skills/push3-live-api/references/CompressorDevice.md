# Live.CompressorDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## CompressorDevice.CompressorDevice

This class represents a Compressor device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `available_input_routing_channels` (r, listenable): Return a list of source channels for input routing in the sidechain.
- `available_input_routing_types` (r, listenable): Return a list of source types for input routing in the sidechain.
- `input_routing_channel` (rw, listenable): Get and set the current source channel for input routing in the sidechain. Raises ValueError if the channel isn't one of the current values in available_input_routing_channels.
- `input_routing_type` (rw, listenable): Get and set the current source type for input routing in the sidechain. Raises ValueError if the type isn't one of the current values in available_input_routing_types.
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
