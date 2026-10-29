# Live.WavetableDevice

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## WavetableDevice.WavetableDevice

This class represents a Wavetable device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `filter_routing` `int`† (rw, listenable): Return the current filter routing.
- `mono_poly` `int`† (rw, listenable): Return the current voicing mode.
- `oscillator_1_effect_mode` `int`† (rw, listenable): Return the current effect mode of the oscillator 1.
- `oscillator_1_wavetable_category` `int`† (rw, listenable): Return the current wavetable category of the oscillator 1.
- `oscillator_1_wavetable_index` `int`† (rw, listenable): Return the current wavetable index of the oscillator 1.
- `oscillator_1_wavetables` `Base.StringVector`† (r, listenable): Get a vector of oscillator 1's wavetable names.
- `oscillator_2_effect_mode` `int`† (rw, listenable): Return the current effect mode of the oscillator 2.
- `oscillator_2_wavetable_category` `int`† (rw, listenable): Return the current wavetable category of the oscillator 2.
- `oscillator_2_wavetable_index` `int`† (rw, listenable): Return the current wavetable index of the oscillator 2.
- `oscillator_2_wavetables` `Base.StringVector`† (r, listenable): Get a vector of oscillator 2's wavetable names.
- `oscillator_wavetable_categories` `Base.StringVector`† (r): Get a vector of the available wavetable categories.
- `poly_voices` `int`† (rw, listenable): Return the current number of polyphonic voices. Uses the VoiceCount enumeration.
- `unison_mode` `int`† (rw, listenable): Return the current unison mode.
- `unison_voice_count` `int`† (rw, listenable): Return the current number of unison voices.
- `visible_modulation_target_names` `Base.StringVector`† (r, listenable): Get the names of all the visible modulation targets.
- `modulation_matrix_changed` (r, listenable)

Methods:

- `add_parameter_to_modulation_matrix(parameter: DeviceParameter.DeviceParameter) -> int`: Add a non-pitch parameter to the modulation matrix.
- `get_modulation_target_parameter_name(target_index: int) -> str`: Get the parameter name of the modulation target at the given index.
- `get_modulation_value(target_index: int, source: int) -> float`: Get the value of a modulation amount for the given target-source connection.
- `is_parameter_modulatable(parameter: DeviceParameter.DeviceParameter) -> bool`: Indicate whether the parameter is modulatable. Note that pitch parameters only exist in python and must be handled there.
- `set_modulation_value(target_index: int, source: int, value: float) -> None`: Set the value of a modulation amount for the given target-source connection.

## Enums

- `EffectMode`: none=0, frequency_modulation=1, sync_and_pulse_width=2, warp_and_fold=3
- `FilterRouting`: serial=0, parallel=1, split=2
- `ModulationSource`: amp_envelope=0, envelope_2=1, envelope_3=2, lfo_1=3, lfo_2=4, midi_velocity=5, midi_note=6, midi_pitch_bend=7, midi_channel_pressure=8, midi_mod_wheel=9, midi_random=10
- `UnisonMode`: none=0, classic=1, slow_shimmer=2, fast_shimmer=3, phase_sync=4, position_spread=5, random_note=6
- `VoiceCount`: two=0, three=1, four=2, five=3, six=4, seven=5, eight=6, sixteen=7
- `Voicing`: mono=0, poly=1
