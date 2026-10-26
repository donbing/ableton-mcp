# Live.Clip

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Clip.Clip

This class represents a Clip in Live. It can be either an Audio Clip or a MIDI Clip, in an Arrangement or the Session, depending on the Track (Slot) it lives in.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `automation_envelopes` `Base.Vector[Envelope.Envelope]`† (r): Const access to a list of all automation envelopes for this clip.
- `available_warp_modes` `Base.IntVector`† (r): Available for AudioClips only. Get/Set the available warp modes, that can be used.
- `canonical_parent` `ClipSlot.ClipSlot`† (r): Get the canonical parent of the Clip.
- `color` `int`† (rw, listenable): Get/set access to the color of the Clip (RGB).
- `color_index` `int`† (rw, listenable): Get/set access to the color index of the Clip.
- `end_marker` `float`† (rw, listenable): Get/Set the Clips end marker pos in beats/seconds (unit depends on warping).
- `end_time` `float`† (r, listenable): Get the clip's end time.
- `file_path` `str`† (r, listenable): Get the path of the file represented by the Audio Clip.
- `gain` `float`† (rw, listenable): Available for AudioClips only. Read/write access to the gain setting of the Audio Clip
- `gain_display_string` `str`† (r): Return a string with the gain as dB value
- `groove` (rw, listenable): Get the groove associated with this clip.
- `has_envelopes` `bool`† (r, listenable): Will notify if the clip gets his first envelope or the last envelope is removed.
- `has_groove` `bool`† (r): Returns true if a groove is associated with this clip.
- `is_arrangement_clip` `bool`† (r): return true if this Clip is an Arrangement Clip. A Clip can be either a Session or Arrangement Clip.
- `is_audio_clip` `bool`† (r): Return true if this Clip is an Audio Clip. A Clip can be either an Audioclip or a MIDI Clip.
- `is_midi_clip` `bool`† (r): return true if this Clip is a MIDI Clip. A Clip can be either an Audioclip or a MIDI Clip.
- `is_overdubbing` `bool`† (r, listenable): returns true if the Clip is recording overdubs
- `is_playing` `bool`† (rw): Get/Set if this Clip is currently playing. If the Clips trigger mode is set to a quantization value, the Clip will not start playing immediately. If you need to know wether the Clip was triggered, use the is_triggered property.
- `is_recording` `bool`† (r, listenable): returns true if the Clip was triggered to record or is recording.
- `is_session_clip` `bool`† (r): return true if this Clip is a Session Clip. A Clip can be either a Session or Arrangement Clip.
- `is_take_lane_clip` `bool`† (r): return true if this Clip is a Take Lane Clip. A Take Lane Clip is also always an Arrangement Clip.
- `is_triggered` `bool`† (r): returns true if the Clip was triggered or is playing.
- `launch_mode` `int`† (rw, listenable): Get/Set access to the launch mode setting of the Clip.
- `launch_quantization` `int`† (rw, listenable): Get/Set access to the launch quantization setting of the Clip.
- `legato` `bool`† (rw, listenable): Get/Set access to the legato setting of the Clip
- `length` `float`† (r): Get to the Clips length in beats/seconds (unit depends on warping).
- `loop_end` `float`† (rw, listenable): Get/Set the loop end pos of this Clip in beats/seconds (unit depends on warping).
- `loop_start` `float`† (rw, listenable): Get/Set the Clips loopstart pos in beats/seconds (unit depends on warping).
- `looping` `bool`† (rw, listenable): Get/Set the Clips 'loop is enabled' flag .Only Warped Audio Clips or MIDI Clip can be looped.
- `muted` `bool`† (rw, listenable): Read/write access to the mute state of the Clip.
- `name` `str`† (rw, listenable): Read/write access to the name of the Clip.
- `pitch_coarse` `int`† (rw, listenable): Available for AudioClips only. Read/write access to the pitch (in halftones) setting of the Audio Clip, ranging from -48 to 48
- `pitch_fine` `float`† (rw, listenable): Available for AudioClips only. Read/write access to the pitch fine setting of the Audio Clip, ranging from -500 to 500
- `playing_position` `float`† (r, listenable): Constant access to the current playing position of the clip. The returned value is the position in beats for midi and warped audio clips, or in seconds for unwarped audio clips. Stopped clips will return 0.
- `position` `float`† (rw, listenable): Get/Set the loop position of this Clip in beats/seconds (unit depends on warping).
- `ram_mode` `bool`† (rw, listenable): Available for AudioClips only. Read/write access to the Ram mode setting of the Audio Clip
- `sample_length` `int`† (r): Available for AudioClips only. Get the sample length in sample time or -1 if there is no sample available.
- `sample_rate` `float`† (r): Available for AudioClips only. Read-only access to the Clip's sampling rate.
- `signature_denominator` `int`† (rw, listenable): Get/Set access to the global signature denominator of the Clip.
- `signature_numerator` `int`† (rw, listenable): Get/Set access to the global signature numerator of the Clip.
- `start_marker` `float`† (rw, listenable): Get/Set the Clips start marker pos in beats/seconds (unit depends on warping).
- `start_time` `float`† (r, listenable): Get the clip's start time offset. For Session View clips, this is the time the clip was started. For Arrangement View clips, this is the offset within the arrangement.
- `velocity_amount` `float`† (rw, listenable): Get/Set access to the velocity to volume amount of the Clip.
- `view` `Clip.Clip.View`† (r): Get the view of the Clip.
- `warp_markers` `Clip.WarpMarkerVector`† (r, listenable): Available for AudioClips only. Get the warp markers for this audio clip.
- `warp_mode` `int`† (rw, listenable): Available for AudioClips only. Get/Set the warp mode for this audio clip.
- `warping` `bool`† (rw, listenable): Available for AudioClips only. Get/Set if this Clip is timestreched.
- `will_record_on_start` `bool`† (r): returns true if the Clip will record on being started.
- `loop_jump` (r, listenable)
- `notes` (r, listenable)
- `playing_status` (r, listenable)

Methods:

- `add_new_notes(arg2: object) -> Base.IntU64Vector`: Expects a Python iterable holding a number of Live.Clip.MidiNoteSpecification objects. The objects will be used to construct new notes in the clip.
- `add_warp_marker(warp_marker: object) -> None`: Available for AudioClips only. Adds the specified warp marker, if possible.
- `apply_note_modifications(arg2: Clip.MidiNoteVector) -> None`: Expects a list of notes as returned from get_notes_extended. The content of the list will be used to modify existing notes in the clip, based on matching note IDs. This function should be used when modifying existing notes, e.g. changing the velocity or start time. The function ensures that per-note events attached to the modified notes are preserved. This is NOT the case when replacing notes via a combination of remove_notes_extended and add_new_notes. The given list can be a subset of the notes in the clip, but it must not contain any notes that are not present in the clip.
- `automation_envelope(arg2: DeviceParameter.DeviceParameter) -> Envelope.Envelope`: Return the envelope for the given parameter.Returns None if the envelope doesn't exist.Returns None for Arrangement clips.Returns None for parameters from a different track.
- `beat_to_sample_time(beat_time: float) -> float`: Available for AudioClips only. Converts the given beat time to sample time. Raises an error if the sample is not warped.
- `clear_all_envelopes() -> None`: Clears all envelopes for this clip.
- `clear_envelope(arg2: DeviceParameter.DeviceParameter) -> None`: Clears the envelope of this clips given parameter.
- `create_automation_envelope(arg2: DeviceParameter.DeviceParameter) -> Envelope.Envelope`: Creates an envelope for a given parameter and returns it.This should only be used if the envelope doesn't exist.Raises an error if the envelope can't be created.
- `crop() -> None`: Crops the clip. The region that is cropped depends on whether the clip is looped or not. If looped, the region outside of the loop is removed. If not looped, the region outside the start and end markers is removed.
- `deselect_all_notes() -> None`: De-selects all notes present in the clip.
- `duplicate_loop() -> None`: Make the loop two times longer and duplicates notes and envelopes. Duplicates the clip start/end range if the clip is not looped.
- `duplicate_notes_by_id(note_ids: object, destination_time: object | None, transposition_amount: int) -> Base.IntU64Vector`: Duplicate all notes matching the given note IDs. If the optional destination_time is not provided, new notes will be inserted after the last selected note. This behavior can be observed when duplicating notes in the Live GUI. If the transposition_amount is specified, the notes in the region will be transposed by the number of semitones. Raises an error on audio clips.
- `duplicate_region(region_start: float, region_length: float, destination_time: float, pitch: int, transposition_amount: int) -> None`: Duplicate the notes in the specified region to the destination_time. Only notes of the specified pitch are duplicated or all if pitch is -1. If the transposition_amount is not 0, the notes in the region will be transposed by the transpose_amount of semitones.Raises an error on audio clips.
- `fire() -> None`: (Re)Start playing this Clip.
- `get_all_notes_extended() -> Clip.MidiNoteVector`: Returns a list of all MIDI notes from the clip, regardless of their position relative to the start and end markers/loop start and loop end. Each note is represented by a Live.Clip.MidiNote object. The returned list can be modified freely, but modifications will not be reflected in the MIDI clip until apply_note_modifications is called.
- `get_notes(from_time: float, from_pitch: int, time_span: float, pitch_span: int) -> tuple`: Returns a tuple of tuples where each inner tuple represents a note starting in the given pitch- and time range. The inner tuple contains pitch, time, duration, velocity, and mute state.
- `get_notes_by_id(note_ids: object) -> Clip.MidiNoteVector`: Return a list of MIDI notes matching the given note IDs.
- `get_notes_extended(from_pitch: int, pitch_span: int, from_time: float, time_span: float) -> Clip.MidiNoteVector`: Returns a list of MIDI notes from the given pitch and time range. Each note is represented by a Live.Clip.MidiNote object. The returned list can be modified freely, but modifications will not be reflected in the MIDI clip until apply_note_modifications is called.
- `get_selected_notes() -> tuple`: Returns a tuple of tuples where each inner tuple represents a selected note. The inner tuple contains pitch, time, duration, velocity, and mute state.
- `get_selected_notes_extended() -> Clip.MidiNoteVector`: Returns a list of all MIDI notes from the clip that are currently selected. Each note is represented by a Live.Clip.MidiNote object. The returned list can be modified freely, but modifications will not be reflected in the MIDI clip until apply_note_modifications is called.
- `move_playing_pos(arg2: float) -> None`: Jump forward or backward by the specified relative amount in beats. Will do nothing, if the Clip is not playing.
- `move_warp_marker(marker_beat_time: float, beat_time_distance: float) -> None`: Available for AudioClips only. Moves the specified warp marker by the specified beat time amount, if possible.
- `note_number_to_name(midi_pitch: int) -> str`: Return a human-readable name for the given MIDI note number. Takes into account the scale and tonal spelling settings of the clip, as well as the current tuning system (if any)
- `quantize(arg2: int, arg3: float) -> None`: Quantize all notes in a clip or align warp markers.
- `quantize_pitch(arg2: int, arg3: int, arg4: float) -> None`: Quantize all the notes of a given pitch. Raises an error on audio clips.
- `remove_notes(arg2: float, arg3: int, arg4: float, arg5: int) -> None`: Delete all notes starting in the given pitch- and time range.
- `remove_notes_by_id(arg2: object) -> None`: Delete all notes matching the given note IDs. This function should NOT be used to implement modification of existing notes (i.e. in combination with add_new_notes), as that leads to loss of per-note events. apply_note_modifications must be used instead for modifying existing notes.
- `remove_notes_extended(from_pitch: int, pitch_span: int, from_time: float, time_span: float) -> None`: Delete all notes starting in the given pitch and time range. This function should NOT be used to implement modification of existing notes (i.e. in combination with add_new_notes), as that leads to loss of per-note events. apply_note_modifications must be used instead for modifying existing notes.
- `remove_warp_marker(beat_time: float) -> None`: Available for AudioClips only. Removes the specified warp marker, if possible.
- `replace_selected_notes(arg2: tuple) -> None`: Called with a tuple of tuples where each inner tuple represents a note in the same format as returned by get_selected_notes. The notes described that way will then be used to replace the old selection.
- `sample_to_beat_time(sample_time: float) -> float`: Available for AudioClips only. Converts the given sample time to beat time. Raises an error if the sample is not warped.
- `scrub(scrub_position: float) -> None`: Scrubs inside a clip. scrub_position defines the position in beats that the scrub will start from. The scrub will continue until stop_scrub is called. Global quantization applies to the scrub's position and length.
- `seconds_to_sample_time(seconds: float) -> float`: Available for AudioClips only. Converts the given seconds to sample time. Raises an error if the sample is warped.
- `select_all_notes() -> None`: Selects all notes present in the clip.
- `select_notes_by_id(arg2: object) -> None`: Selects all notes matching the given note IDs.
- `set_fire_button_state(arg2: bool) -> None`: Set the clip's fire button state directly. Supports all launch modes.
- `set_notes(arg2: tuple) -> None`: Called with a tuple of tuples where each inner tuple represents a note in the same format as returned by get_notes. The notes described that way will then be added to the clip.
- `stop() -> None`: Stop playing this Clip.
- `stop_scrub() -> None`: Stops the current scrub.

## Clip.MidiNote

An object representing a MIDI Note

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `duration` `float`† (rw)
- `mute` `bool`† (rw)
- `note_id` `int`† (r): A numerical ID that's unique within the originating clip of the note. Not to be used directly, but important for other API calls, namely apply_note_modifications.
- `pitch` `int`† (rw)
- `probability` `float`† (rw)
- `release_velocity` `float`† (rw)
- `start_time` `float`† (rw)
- `velocity` `float`† (rw)
- `velocity_deviation` `float`† (rw)

## Clip.MidiNoteSpecification

An object specifying the data for creating a MIDI note. To be used with the add_new_notes function.

Not constructable from Python.

## Clip.MidiNoteVector

A container for holding MIDI notes from Live.

Not constructable from Python. Iterable.

## Clip.WarpMarker

This class represents a WarpMarker type.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `beat_time` `float`† (r): A WarpMarker's beat time.
- `sample_time` `float`† (r): A WarpMarker's sample time.

## Clip.WarpMarkerVector

A container for returning warp markers from Live.

Not constructable from Python. Iterable.

## Clip.Clip.View

Representing the view aspects of a Clip.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Clip.Clip`† (r): Get the canonical parent of the clip view.
- `grid_is_triplet` `bool`† (rw): Get/set wether the grid is showing in triplet mode.
- `grid_quantization` `Clip.GridQuantization`† (rw): Get/set clip grid quantization resolution.

Methods:

- `hide_envelope() -> None`: Hide the envelope view.
- `select_envelope_parameter(arg2: DeviceParameter.DeviceParameter) -> None`: Select the given device parameter in the envelope view.
- `show_envelope() -> None`: Show the envelope view.
- `show_loop() -> None`: Show the entire loop in the detail view.

## Enums

- `ClipLaunchQuantization`: q_global=0, q_none=1, q_8_bars=2, q_4_bars=3, q_2_bars=4, q_bar=5, q_half=6, q_half_triplet=7, q_quarter=8, q_quarter_triplet=9, q_eighth=10, q_eighth_triplet=11, q_sixteenth=12, q_sixteenth_triplet=13, q_thirtysecond=14
- `GridQuantization`: no_grid=0, g_8_bars=1, g_4_bars=2, g_2_bars=3, g_bar=4, g_half=5, g_quarter=6, g_eighth=7, g_sixteenth=8, g_thirtysecond=9, count=10
- `LaunchMode`: trigger=0, gate=1, toggle=2, repeat=3
- `WarpMode`: beats=0, complex=4, complex_pro=6, repitch=3, rex=5, texture=2, tones=1, count=7
