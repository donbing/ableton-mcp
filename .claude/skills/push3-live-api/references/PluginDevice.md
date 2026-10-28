# Live.PluginDevice

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## PluginDevice.PluginDevice

This class represents a plugin device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_active` `bool`† (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_editor_open` (rw, listenable) *(new)*: Access to the opened state of the plugin's editor window.
- `is_using_compare_preset_b` (rw) *(new)*: Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float`† (r): Returns the latency of the device in ms.
- `latency_in_samples` `int`† (r): Returns the latency of the device in samples.
- `name` `str`† (rw): Return access to the name of the device.
- `parameters` `Device.ATimeableValueVector`† (r): Const access to the list of available automatable parameters for this device.
- `presets` `Base.StringVector`† (r, listenable): Get the list of presets the plugin offers.
- `selected_preset_index` `int`† (rw, listenable): Access to the index of the currently selected preset.

Methods:

- `get_parameter_names(begin: int, end: int) -> Base.StringVector`: Get the range of plugin parameter names, bound by begin and end. If end is smaller than 0 it is interpreted as the parameter count.
