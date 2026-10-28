# Live.TakeLane

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## TakeLane.TakeLane

This class represents a take lane in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `arrangement_clips` `Base.Vector[Clip.Clip]`† (r, listenable): Read-only access to the arrangement clips in the take lane.
- `canonical_parent` `Track.Track`† (r): Get the canonical parent of the take lane.
- `name` `str`† (rw, listenable): Read/write access to the name of the TakeLane, as visible in the take lane header.

Methods:

- `create_audio_clip(arg2: str, arg3: float) -> Clip.Clip`: Creates an audio clip referencing the file at the given path and inserts it into the arrangement at the specified time. Throws an error when called on a non-audio or a frozen track, when the specified time is outside the [0., 1576800.] range, when the track is currently being recorded into, or when the path doesn't point to a valid audio file.
- `create_midi_clip(arg2: float, arg3: float) -> Clip.Clip`: Creates an empty MIDI clip and inserts it into the arrangement at the specified time. Throws an error when called on a non-MIDI track or a frozen track, when the specified time is outside the [0., 1576800.] range, or when the track is currently being recorded into.
