# Live.Envelope

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Envelope.Envelope

This class represents an automation or modulation envelope in Live.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Clip.Clip`† (r): Get the canonical parent of the envelope.
- `parameter` (r) *(new)*: Read-only access to the parameter controlled by the envelope.

Methods:

- `create_event(arg2: Envelope.EnvelopeEvent) -> None` *(new)*: Creates a new event at the specified time with the given value and, optionally, control coefficients.
- `delete_events_in_range(arg2: float, arg3: float) -> None`: Deletes the events in the specified time range.
- `events_in_range(arg2: float, arg3: float) -> Envelope.EnvelopeEventVector`: Returns the events in the specified time range.
- `insert_step(arg2: float, arg3: float, arg4: float) -> None`: Given a start time, a step length and a value, creates a step in the envelope.
- `value_at_time(arg2: float) -> float`: Returns the parameter value at the specified time.

## Envelope.EnvelopeEvent

This is a class that represents an envelope event.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `control_coefficients` `Envelope.EnvelopeEventControlCoefficients`† (rw)
- `time` `float`† (rw)
- `value` `float`† (rw)

## Envelope.EnvelopeEventControlCoefficients

This class represents the control coefficients of an envelope event.

Properties (r = read-only, rw = settable):

- `x1` `float`† (rw)
- `x2` `float`† (rw)
- `y1` `float`† (rw)
- `y2` `float`† (rw)

Methods:

- `__init__(x1: float, y1: float, x2: float, y2: float) -> None`

## Envelope.EnvelopeEventVector

A container for holding envelope events.

Not constructable from Python. Iterable.
