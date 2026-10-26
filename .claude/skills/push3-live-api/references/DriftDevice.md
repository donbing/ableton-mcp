# Live.DriftDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## DriftDevice.DriftDevice

This class represents a Drift device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `mod_matrix_filter_source_1_index` (rw, listenable): Return the filter mod source 1 index
- `mod_matrix_filter_source_1_list` (r): Return the filter mod source 1 list
- `mod_matrix_filter_source_2_index` (rw, listenable): Return the filter mod source 2 index
- `mod_matrix_filter_source_2_list` (r): Return the filter mod source 2 list
- `mod_matrix_lfo_source_index` (rw, listenable): Return the lfo mod source index
- `mod_matrix_lfo_source_list` (r): Return the lfo mod source list
- `mod_matrix_pitch_source_1_index` (rw, listenable): Return the pitch mod source 1 index
- `mod_matrix_pitch_source_1_list` (r): Return the pitch mod source 1 list
- `mod_matrix_pitch_source_2_index` (rw, listenable): Return the pitch mod source 2 index
- `mod_matrix_pitch_source_2_list` (r): Return the pitch mod source 2 list
- `mod_matrix_shape_source_index` (rw, listenable): Return the shape mod source index
- `mod_matrix_shape_source_list` (r): Return the shape mod source list
- `mod_matrix_source_1_index` (rw, listenable): Return the custom mod source 1 index
- `mod_matrix_source_1_list` (r): Return the custom mod source 1 list
- `mod_matrix_source_2_index` (rw, listenable): Return the custom mod source 2 index
- `mod_matrix_source_2_list` (r): Return the custom mod source 2 list
- `mod_matrix_source_3_index` (rw, listenable): Return the custom mod source 3 index
- `mod_matrix_source_3_list` (r): Return the custom mod source 3 list
- `mod_matrix_target_1_index` (rw, listenable): Return the custom mod target 1 index
- `mod_matrix_target_1_list` (r): Return the custom mod target 1 list
- `mod_matrix_target_2_index` (rw, listenable): Return the custom mod target 2 index
- `mod_matrix_target_2_list` (r): Return the custom mod target 2 list
- `mod_matrix_target_3_index` (rw, listenable): Return the custom mod target 3 index
- `mod_matrix_target_3_list` (r): Return the custom mod target 3 list
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `pitch_bend_range` (rw, listenable): Return the Pitch Bend Range
- `voice_count_index` (rw, listenable): Return the voice count index
- `voice_count_list` (r): Return the voice count list
- `voice_mode_index` (rw, listenable): Return the voice mode index
- `voice_mode_list` (r): Return the voice mode list
