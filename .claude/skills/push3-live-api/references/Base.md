# Live.Base

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Base.FloatVector

A simple container for returning floats from Live.

Not constructable from Python. Iterable.

## Base.IntU64Vector

A simple container for returning unsigned long integers from Live.

Not constructable from Python. Iterable.

## Base.IntVector

A simple container for returning integers from Live.

Not constructable from Python. Iterable.

## Base.LimitationError

Base: Exception. Not constructable from Python.

## Base.ObjectVector

A simple read only container for returning python objects.

Not constructable from Python. Iterable.

## Base.StringVector

A simple container for returning strings from Live.

Not constructable from Python. Iterable.

## Base.Text

A translatable, immutable string.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `text` (r)

## Base.Timer

A timer that will trigger a callback after a certain inverval. The timer can be repeated and will trigger the callback every interval. Errors in the callback will stop the timer.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `running` `bool`† (r)

Methods:

- `restart() -> None`
- `start() -> None`
- `stop() -> None`

## Base.Vector

A simple read only container for returning objects from Live.

Not constructable from Python. Iterable.

## Functions

- `get_text(classname: str, textname: str) -> Base.Text`: Retrieves the (translated) Text identified by `classname` and `textname`.
- `log(arg1: str) -> None`
- `subst_args(text: Base.Text, arg1: str, arg2: str, arg3: str, arg4: str, arg5: str) -> str`
