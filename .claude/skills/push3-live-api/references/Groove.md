# Live.Groove

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Groove.Groove

This class represents a groove in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `base` `Groove.Base`† (rw): Get/set the groove's base grid.
- `canonical_parent` `GroovePool.GroovePool`† (r): Get the canonical parent of the groove.
- `name` `str`† (rw, listenable): Read/write/listen access to the groove's name
- `quantization_amount` `float`† (rw, listenable): Read/write/listen access to the groove's quantization amount.
- `random_amount` `float`† (rw, listenable): Read/write/listen access to the groove's random amount.
- `timing_amount` `float`† (rw, listenable): Read/write/listen access to the groove's timing amount.
- `velocity_amount` `float`† (rw, listenable): Read/write/listen access to the groove's velocity amount.

## Enums

- `Base`: gb_four=0, gb_eight=1, gb_eight_triplet=2, gb_sixteen=3, gb_sixteen_triplet=4, gb_thirtytwo=5, count=6
