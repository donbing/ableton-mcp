# Live.Listener

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Listener.ListenerHandle

This class represents a Python listener when connected to a Live property.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `listener_func` (r): Returns the original function
- `listener_self` (r): Returns the weak reference to original self, if it was a bound method
- `name` (r): Prints the name of the property that this listener is connected to

Methods:

- `disconnect() -> None`: Disconnects the listener from its property

## Listener.ListenerVector

A read only container for accessing a list of listeners.

Not constructable from Python. Iterable.
