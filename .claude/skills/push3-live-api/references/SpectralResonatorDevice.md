# Live.SpectralResonatorDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## SpectralResonatorDevice.SpectralResonatorDevice

This class represents a Spectral Resonator device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `frequency_dial_mode` (rw, listenable): Return the current frequency dial mode index
- `frequency_dial_mode_list` (r, listenable): Return the current frequency dial mode list
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `midi_gate` (rw, listenable): Return the current midi gate index
- `midi_gate_list` (r, listenable): Return the current midi gate list
- `mod_mode` (rw, listenable): Return the current mod mode index
- `mod_mode_list` (r, listenable): Return the current mod mode list
- `mono_poly` (rw, listenable): Return the current mono poly mode index
- `mono_poly_list` (r, listenable): Return the current mono poly mode list
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `pitch_bend_range` (rw, listenable): Return the current pitch bend range
- `pitch_mode` (rw, listenable): Return the current pitch mode index
- `pitch_mode_list` (r, listenable): Return the current pitch mode list
- `polyphony` (rw, listenable): Return the current polyphony
