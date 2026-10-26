# Live.ClipSlot

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## ClipSlot.ClipSlot

This class represents an entry in Lives Session view matrix.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Track.Track`† (r): Get the canonical parent of the ClipSlot.
- `clip` `Clip.Clip`† (r): Returns the Clip which this clipslots currently owns. Might be None.
- `color` `int`† (r, listenable): Returns the canonical color for the clip slot or None if it does not exist.
- `color_index` `int`† (r, listenable): Returns the canonical color index for the clip slot or None if it does not exist.
- `controls_other_clips` `bool`† (r, listenable): Returns true if firing this slot will fire clips in other slots. Can only be true for slots in group tracks.
- `has_clip` `bool`† (r, listenable): Returns true if this Clipslot owns a Clip.
- `has_stop_button` `bool`† (rw, listenable): Get/Set if this Clip has a stop button, which will, if fired, stop any other Clip that is currently playing the Track we do belong to.
- `is_group_slot` `bool`† (r): Returns whether this clip slot is a group track slot (group slot).
- `is_playing` `bool`† (r): Returns whether the clip associated with the slot is playing.
- `is_recording` `bool`† (r): Returns whether the clip associated with the slot is recording.
- `is_triggered` `bool`† (r, listenable): Const access to the triggering state of the clip slot.
- `playing_status` `ClipSlot.ClipSlotPlayingState`† (r, listenable): Const access to the playing state of the clip slot. Can be either stopped, playing, or recording.
- `will_record_on_start` `bool`† (r): returns true if the clip slot will record on being fired.

Methods:

- `create_audio_clip(arg2: str) -> Clip.Clip`: Creates an audio clip referencing the file at the given absolute path in the slot. Throws an error when called on non-empty slots or slots in non-audio or frozen tracks, or when the path doesn't point at a valid audio file.
- `create_clip(arg2: float) -> Clip.Clip`: Creates an empty clip with the given length in the slot. Throws an error when called on non-empty slots or slots in non-MIDI tracks.
- `delete_clip() -> None`: Removes the clip contained in the slot. Raises an exception if the slot was empty.
- `duplicate_clip_to(arg2: ClipSlot.ClipSlot) -> None`: Duplicates the slot's clip to the passed in target slot. Overrides the target's clip if it's not empty. Raises an exception if the (source) slot itself is empty, or if source and target have different track types (audio vs. MIDI). Also raises if the source or target slot is in a group track (so called group slot).
- `fire() -> None`: Fire a Clip if this Clipslot owns one, else trigger the stop button, if we have one.
- `set_fire_button_state(arg2: bool) -> None`: Set the clipslot's fire button state directly. Supports all launch modes.
- `stop() -> None`: Stop playing the contained Clip, if there is a Clip and its currently playing.

## Enums

- `ClipSlotPlayingState`: stopped=0, started=1, recording=2
