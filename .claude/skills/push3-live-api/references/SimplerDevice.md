# Live.SimplerDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## SimplerDevice.SimplerDevice

This class represents a Simpler device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `can_warp_as` (r, listenable): Returns true if warp_as is available.
- `can_warp_double` (r, listenable): Returns true if warp_double is available.
- `can_warp_half` (r, listenable): Returns true if warp_half is available.
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `multi_sample_mode` (r, listenable): Returns whether Simpler is in mulit-sample mode.
- `name` (rw): Return access to the name of the device.
- `note_pitch_bend_range` (rw, listenable): Access to the Note Pitch Bend Range in Simpler.
- `pad_slicing` (rw, listenable): When set to true, slices can be added in slicing mode by playing notes .that are not assigned to slices, yet.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `pitch_bend_range` (rw, listenable): Access to the Pitch Bend Range in Simpler.
- `playback_mode` (rw, listenable): Access to Simpler's playback mode.
- `playing_position` (r, listenable): Constant access to the current playing position in the sample. The returned value is the normalized position between sample start and end.
- `playing_position_enabled` (r, listenable): Returns whether Simpler is showing the playing position. The returned value is True while the sample is played back
- `retrigger` (rw, listenable): Access to Simpler's retrigger mode.
- `sample` (r, listenable): Get the loaded Sample.
- `slicing_playback_mode` (rw, listenable): Access to Simpler's slicing playback mode.
- `voices` (rw, listenable): Access to the number of voices in Simpler.

Methods:

- `crop() -> None`: Crop the loaded sample to the active area between start- and end marker. Calling this method on an empty simpler raises an error.
- `guess_playback_length() -> float`: Return an estimated beat time for the playback length between start- and end-marker. Calling this method on an empty simpler raises an error.
- `replace_sample(file_path: str) -> None` *(new)*: Replaces the loaded samples with the one at the provided path.
- `reverse() -> None`: Reverse the loaded sample. Calling this method on an empty simpler raises an error.
- `warp_as(beat_time: float) -> None`: Warp the playback region between start- and end-marker as the given length. Calling this method on an empty simpler raises an error.
- `warp_double() -> None`: Doubles the tempo for region between start- and end-marker.
- `warp_half() -> None`: Halves the tempo for region between start- and end-marker.

## SimplerDevice.SimplerDevice.View

Representing the view aspects of a simpler device.

Base: Device.Device.View, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_collapsed` (rw): Get/Set/Listen if the device is shown collapsed in the device chain.
- `sample_end` (r, listenable): Access to the modulated samples end position in samples. Returns -1 in case there is no sample loaded.
- `sample_env_fade_in` (r, listenable): Access to the envelope fade-in time in samples. Returned value is only in use when Simpler is in one-shot mode. Returns -1 in case there is no sample loaded.
- `sample_env_fade_out` (r, listenable): Access to the envelope fade-out time in samples. Returned value is only in use when Simpler is in one-shot mode. Returns -1 in case there is no sample loaded.
- `sample_loop_end` (r, listenable): Access to the modulated samples loop end position in samples. Returns -1 in case there is no sample loaded.
- `sample_loop_fade` (r, listenable): Access to the modulated samples loop fade position in samples. Returns -1 in case there is no sample loaded.
- `sample_loop_start` (r, listenable): Access to the modulated samples loop start position in samples. Returns -1 in case there is no sample loaded.
- `sample_start` (r, listenable): Access to the modulated samples start position in samples. Returns -1 in case there is no sample loaded.
- `selected_slice` (rw, listenable): Access to the selected slice.

## Functions

- `get_available_voice_numbers() -> Base.IntVector`: Get a vector of valid Simpler voice numbers.

## Enums

- `PlaybackMode`: classic=0, one_shot=1, slicing=2
- `SlicingPlaybackMode`: mono=0, poly=1, thru=2
