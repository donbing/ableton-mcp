# Live.Conversions

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Functions

- `audio_to_midi_clip(song: Song.Song, audio_clip: Clip.Clip, audio_to_midi_type: int) -> None`: Creates a MIDI clip in a new MIDI track with the notes extracted from the given audio_clip. The `audio_to_midi_type` decides which algorithm is used in the process. Raises error when called with an inconvertible clip or invalid `audio_to_midi_type`.
- `create_drum_rack_from_audio_clip(song: Song.Song, audio_clip: Clip.Clip) -> None`: Creates a new track with a drum rack with a simpler on the first pad with the specified audio clip.
- `create_midi_track_from_drum_pad(song: Song.Song, drum_pad: DrumPad.DrumPad) -> None`: Creates a new Midi track containing the specified Drum Pad's device chain.
- `create_midi_track_with_simpler(song: Song.Song, audio_clip: Clip.Clip) -> None`: Creates a new Midi track with a simpler including the specified audio clip.
- `is_convertible_to_midi(song: Song.Song, audio_clip: Clip.Clip) -> bool`: Returns whether `audio_clip` can be converted to MIDI. Raises error when called with a MIDI clip
- `move_devices_on_track_to_new_drum_rack_pad(song: Song.Song, track_index: int) -> LomObject.LomObject`: Moves the entire device chain of the track according to the track index onto the C1 (note 36) drum pad of a new drum rack in a new track.If the track associated with the track index does not contain any devices nothing changes (i.e. a new track and new drum rack are not created).
- `sliced_simpler_to_drum_rack(song: Song.Song, simpler: SimplerDevice.SimplerDevice) -> None`: Converts the Simpler into a Drum Rack, assigning each slice to a drum pad. Calling it on a non-sliced simpler raises an error.

## Enums

- `AudioToMidiType`: harmony_to_midi=0, melody_to_midi=1, drums_to_midi=2
