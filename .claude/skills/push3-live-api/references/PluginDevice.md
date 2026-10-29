# Live.PluginDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## PluginDevice.PluginDevice

This class represents a plugin device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_editor_open` (rw, listenable) *(new)*: Access to the opened state of the plugin's editor window.
- `presets` `Base.StringVector`† (r, listenable): Get the list of presets the plugin offers.
- `selected_preset_index` `int`† (rw, listenable): Access to the index of the currently selected preset.

Methods:

- `get_parameter_names(begin: int, end: int) -> Base.StringVector`: Get the range of plugin parameter names, bound by begin and end. If end is smaller than 0 it is interpreted as the parameter count.
