# Live.GroovePool

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## GroovePool.GroovePool

This class represents the groove pool in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Song.Song`† (r): Get the canonical parent of the groove pool.
- `grooves` `Base.Vector[Groove.Groove]`† (r, listenable): Access to the list of grooves
