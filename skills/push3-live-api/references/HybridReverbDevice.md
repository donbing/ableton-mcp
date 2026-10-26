# Live.HybridReverbDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## HybridReverbDevice.HybridReverbDevice

This class represents a Hybrid Reverb device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `ir_attack_time` (rw, listenable): Return the current IrAttackTime
- `ir_category_index` (rw, listenable): Return the current IR category index
- `ir_category_list` (r): Return the current IR categories list
- `ir_decay_time` (rw, listenable): Return the current IrDecayTime
- `ir_file_index` (rw, listenable): Return the current IR file index
- `ir_file_list` (r, listenable): Return the current IR file list
- `ir_size_factor` (rw, listenable): Return the current IrSizeFactor
- `ir_time_shaping_on` (rw, listenable): Return the current IrTimeShapingOn
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
