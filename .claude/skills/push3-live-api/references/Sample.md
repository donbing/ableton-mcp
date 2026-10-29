# Live.Sample

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Sample.Sample

This class represents a sample file loaded into a Simpler instance.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `beats_granulation_resolution` `int` (rw, listenable): Access to the Granulation Resolution parameter in Beats Warp Mode.
- `beats_transient_envelope` `float` (rw, listenable): Access to the Transient Envelope parameter in Beats Warp Mode.
- `beats_transient_loop_mode` `int` (rw, listenable): Access to the Transient Loop Mode parameter in Beats Warp Mode.
- `canonical_parent` `SimplerDevice.SimplerDevice` (r): Access to the sample's canonical parent.
- `complex_pro_envelope` `float` (rw, listenable): Access to the Envelope parameter in Complex Pro Mode.
- `complex_pro_formants` `float` (rw, listenable): Access to the Formants parameter in Complex Pro Warp Mode.
- `end_marker` `int` (rw, listenable): Access to the position of the sample's end marker.
- `file_path` `str` (r, listenable): Get the path of the sample file.
- `gain` `float` (rw, listenable): Access to the sample gain.
- `length` `int` (r): Get the length of the sample file in sample frames.
- `sample_rate` `float` (r): Access to the audio sample rate of the sample.
- `slices` `tuple` (r, listenable): Access to the list of slice points in sample time in the sample.
- `slicing_beat_division` `int` (rw, listenable): Access to sample's slicing step size.
- `slicing_region_count` `int` (rw, listenable): Access to sample's slicing split count.
- `slicing_sensitivity` `float` (rw, listenable): Access to sample's slicing sensitivity whose sensitivity is in between 0.0 and 1.0. The higher the sensitivity, the more slices will be available.
- `slicing_style` `int` (rw, listenable): Access to sample's slicing style.
- `start_marker` `int` (rw, listenable): Access to the position of the sample's start marker.
- `texture_flux` `float` (rw, listenable): Access to the Flux parameter in Texture Warp Mode.
- `texture_grain_size` `float` (rw, listenable): Access to the Grain Size parameter in Texture Warp Mode.
- `tones_grain_size` `float` (rw, listenable): Access to the Grain Size parameter in Tones Warp Mode.
- `warp_markers` `Clip.WarpMarkerVector` (r, listenable): Get the warp markers for this sample.
- `warp_mode` `int` (rw, listenable): Access to the sample's warp mode.
- `warping` `bool` (rw, listenable): Access to the sample's warping property.

Methods:

- `beat_to_sample_time(beat_time: float) -> float`: Converts the given beat time to sample time. Raises an error if the sample is not warped.
- `clear_slices() -> None`: Clears all slices created in Simpler's manual mode.
- `gain_display_string() -> str`: Get the gain's display value as a string.
- `insert_slice(slice_time: int) -> None`: Add a slice point at the provided time if there is none.
- `move_slice(old_time: int, new_time: int) -> int`: Move the slice point at the provided time.
- `remove_slice(slice_time: int) -> None`: Remove the slice point at the provided time if there is one.
- `reset_slices() -> None`: Resets all edited slices to their original positions.
- `sample_to_beat_time(sample_time: float) -> float`: Converts the given sample time to beat time. Raises an error if the sample is not warped.

## Enums

- `SlicingBeatDivision`: sixteenth=0, sixteenth_triplett=1, eighth=2, eighth_triplett=3, quarter=4, quarter_triplett=5, half=6, half_triplett=7, one_bar=8, two_bars=9, four_bars=10
- `SlicingStyle`: transient=0, beat=1, region=2, manual=3
- `TransientLoopMode`: off=0, forward=1, alternate=2
