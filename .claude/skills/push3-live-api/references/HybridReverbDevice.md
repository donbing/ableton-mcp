# Live.HybridReverbDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## HybridReverbDevice.HybridReverbDevice

This class represents a Hybrid Reverb device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `ir_attack_time` `float`† (rw, listenable): Return the current IrAttackTime
- `ir_category_index` `int`† (rw, listenable): Return the current IR category index
- `ir_category_list` `Base.StringVector`† (r): Return the current IR categories list
- `ir_decay_time` `float`† (rw, listenable): Return the current IrDecayTime
- `ir_file_index` `int`† (rw, listenable): Return the current IR file index
- `ir_file_list` `Base.StringVector`† (r, listenable): Return the current IR file list
- `ir_size_factor` `float`† (rw, listenable): Return the current IrSizeFactor
- `ir_time_shaping_on` `bool`† (rw, listenable): Return the current IrTimeShapingOn
