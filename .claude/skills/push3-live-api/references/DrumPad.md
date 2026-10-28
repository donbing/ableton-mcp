# Live.DrumPad

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## DrumPad.DrumPad

This class represents a drum group device pad in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `RackDevice.RackDevice`† (r): Get the canonical parent of the drum pad.
- `chains` `Base.Vector`† (r, listenable): Return const access to the list of chains in this drum pad.
- `mute` `bool`† (rw, listenable): Mute/unmute the pad.
- `name` `str`† (r, listenable): Return const access to the drum pad's name. It depends on the contained chains.
- `note` `int`† (r): Get the MIDI note of the drum pad.
- `solo` `bool`† (rw, listenable): Solo/unsolo the pad.

Methods:

- `delete_all_chains() -> None`: Deletes all chains associated with a drum pad. This is equivalent to deleting a drum rack pad in Live.
