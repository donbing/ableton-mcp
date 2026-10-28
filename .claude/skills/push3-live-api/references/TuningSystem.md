# Live.TuningSystem

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## TuningSystem.TuningSystem

Represents a Tuning System and its properties.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Song.Song`† (r): Get the canonical parent of the TuningSystem.
- `highest_note` `TuningSystem.PitchClassAndOctave`† (rw, listenable): Get/Set the highest note of the current tuning system, where the first entry is the index within the pseudo octave and the second entry is the octave.
- `lowest_note` `TuningSystem.PitchClassAndOctave`† (rw, listenable): Get/Set the lowest note of the current tuning system, where the first entry is the index within the pseudo octave and the second entry is the octave.
- `name` `str`† (rw, listenable): Get/Set the name of the currently active tuning system.
- `note_tunings` `list[float]`† (rw, listenable): Get/Set the currently active tuning system's note tunings, specified in Cents, where 100 Cents is one semi-tone in equal temperament.
- `number_of_notes_in_pseudo_octave` `int`† (r): Get the number of notes in the pseudo octave.
- `pseudo_octave_in_cents` `float`† (r): Get the pseudo octave in cents for the currently active tuning system.
- `reference_pitch` `TuningSystem.ReferencePitch`† (rw, listenable): Get/Set the reference pitch the currently active tuning system.

## TuningSystem.PitchClassAndOctave

This class represents a PitchClassAndOctave type.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `index_in_octave` `int`† (r): A PitchClassAndOctave's index within the pseudo octave.
- `octave` `int`† (r): A PitchClassAndOctave's octave.

## TuningSystem.ReferencePitch

This class represents a ReferencePitch type.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `frequency` `float`† (r): A ReferencePitch's frequency in Hz.
- `index_in_octave` `int`† (r): A ReferencePitch's index within the pseudo octave.
- `octave` `int`† (r): A ReferencePitch's octave.
