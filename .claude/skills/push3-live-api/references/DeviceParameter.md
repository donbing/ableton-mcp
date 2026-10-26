# Live.DeviceParameter

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## DeviceParameter.DeviceParameter

This class represents a (automatable) parameter within a MIDI or Audio DSP-Device.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `automation_state` (r, listenable): Returns state of type AutomationState.
- `canonical_parent` (r): Get the canonical parent of the device parameter.
- `default_value` (r): Return the default value for this parameter. A Default value is only available for non-quantized parameter types (see 'is_quantized').
- `display_value` (rw, listenable): Get/Set the current value (as visible in the GUI) this parameter. The value must be inside the min/max properties of this device.
- `is_enabled` (r): Returns false if the parameter has been macro mapped or disabled by Max.
- `is_quantized` (r): Returns True, if this value is a boolean or integer like switch. Non quantized values are continues float values.
- `max` (r): Returns const access to the upper value of the allowed range for this parameter
- `min` (r): Returns const access to the lower value of the allowed range for this parameter
- `name` (r, listenable): Returns const access the name of this parameter, as visible in Lives automation choosers.
- `original_name` (r): Returns const access the original name of this parameter, unaffected of any renamings.
- `short_value_items` (r): Return the list of possible values for this parameter. Like value_items, but prefers short value names if available. Raises an error if 'is_quantized' is False.
- `state` (r, listenable): Returns the state of the parameter: - enabled - the parameter's value can be changed, - irrelevant - the parameter is enabled, but value changes will not take any effect until it gets enabled, - disabled - the parameter's value cannot be changed.
- `value` (rw, listenable): Get/Set the current internal value of this parameter. The value must be inside the min/max properties of this device.
- `value_items` (r): Return the list of possible values for this parameter. Raises an error if 'is_quantized' is False.

Methods:

- `begin_gesture() -> None`: Notify the begin of a modification of the parameter, when a sequence of modifications have to be consider a consistent group -- for Sexample, when recording automation.
- `end_gesture() -> None`: Notify the end of a modification of the parameter. See begin_gesture.
- `re_enable_automation() -> None`: Reenable automation for this parameter.
- `str_for_value(arg2: float) -> str`: Return a string representation of the given value. To be used for display purposes only. This value can include characters like 'db' or 'hz', depending on the type of the parameter.

## Enums

- `AutomationState`: none=0, playing=1, overridden=2
- `ParameterState`: enabled=0, irrelevant=1, disabled=2
