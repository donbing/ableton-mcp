# Live.SpectralResonatorDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## SpectralResonatorDevice.SpectralResonatorDevice

This class represents a Spectral Resonator device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `frequency_dial_mode` `int`† (rw, listenable): Return the current frequency dial mode index
- `frequency_dial_mode_list` `Base.StringVector`† (r, listenable): Return the current frequency dial mode list
- `midi_gate` `int`† (rw, listenable): Return the current midi gate index
- `midi_gate_list` `Base.StringVector`† (r, listenable): Return the current midi gate list
- `mod_mode` `int`† (rw, listenable): Return the current mod mode index
- `mod_mode_list` `Base.StringVector`† (r, listenable): Return the current mod mode list
- `mono_poly` `int`† (rw, listenable): Return the current mono poly mode index
- `mono_poly_list` `Base.StringVector`† (r, listenable): Return the current mono poly mode list
- `pitch_bend_range` `int`† (rw, listenable): Return the current pitch bend range
- `pitch_mode` `int`† (rw, listenable): Return the current pitch mode index
- `pitch_mode_list` `Base.StringVector`† (r, listenable): Return the current pitch mode list
- `polyphony` `int`† (rw, listenable): Return the current polyphony
