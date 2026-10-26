---
name: push3-live-api
description: Reference for Ableton Live's Python API (the Live Object Model) as measured on the user's Push 3 standalone, Live 12.4.6 Intro. Use when writing or debugging Remote Script code in this repo (AbletonMCP_Remote_Script), adding a new MCP tool that needs a Live call, or checking whether a class, property, method or enum exists, is settable or is listenable on the Push. Not for making music through the MCP tools (that is ableton-music).
---

# Live's Python API on the Push 3

What the API looks like on the user's Push 3, from a capture taken on the device itself. The facts live in
`references/`, generated from LiveAPI's seed by `tools/gen_live_api_skill.py`; this file is hand-written.

## First: does the reference match the Push?

`references/INDEX.md` names the Live version it was captured from (12.4.6, Intro edition). Before relying on it,
call `get_remote_script_info` or `get_live_status` and compare the Live version. If they differ, say so and treat
the reference as a guide only: check anything important at runtime on the Push.

The current capture is a **raw** capture (no property probe):

- It has no property types of its own. Types marked † are borrowed from the Live 12.3.6 property probe (LiveAPI's
  committed seed) for properties that exist in both versions; they are very likely right but were not measured on
  the Push. Properties with no type are new in 12.4.6 or were never probed: check the value at runtime.
- `references/CHANGES.md` lists what differs from Live 12.3.6. Its "Missing from this capture" list is unverified:
  most entries are gaps in a raw capture, not real removals.
- Intro is a limited edition. A class being in the API does not mean its device is available on the Push.

## Finding things

- `references/INDEX.md`: every module, its classes and a member count. Start here.
- `references/<Module>.md`: one file per module (`Song.md`, `Track.md`, `Clip.md`, `Device.md`, ...). Each class
  lists its properties (`r` read-only, `rw` settable, `listenable`), methods with argument types, enums with their
  integer values, and functions. Members new since 12.3.6 are tagged *(new)*.
- Search instead of reading whole files, e.g. `grep -n "launch_quantization" references/*.md`.

Doc strings are Ableton's own, copied as-is. They are sometimes wrong about access ("Get/Set" on a read-only
property, e.g. `Clip.available_warp_modes`): trust the `r` / `rw` flag, which was read from the binding itself.

## Rules for calling the API

- **Main thread only.** Every read, write, method call and listener registration must run on Live's main thread:
  inside a Remote Script callback or a `schedule_message` callback. In this repo the socket thread hands work to the
  main thread with `self.schedule_message(0, task)` and waits on a `queue.Queue`, or uses `_call_on_main_thread`
  (`AbletonMCP_Remote_Script/__init__.py`); reuse that instead of touching the API from the socket thread.
- **Do not block.** The main thread is also Live's UI thread. No `sleep`,
  no blocking I/O, no long loops over big collections in one go; split work across ticks (about 100 ms each).
- **Positional arguments only.** Keyword arguments raise `TypeError` or worse. Argument names in the references
  (`arg2`, `index`) are labels, not keywords.
- **Optional arguments**: a type shown as `X | None` can be omitted.
- **Limits raise.** Creating tracks, scenes or clips past the edition's limits raises a limitation error; catch it
  and report it.

## Listeners

A property marked `listenable` has `add_<name>_listener(cb)`, `remove_<name>_listener(cb)` and
`<name>_has_listener(cb)`, even though the references list only the property.

- The callback gets no arguments; read the property inside it.
- Removal matches by identity: store the callback once (`self._on_x = self.on_x`) and pass that same object to add
  and remove. Unremoved listeners outlive a script reload.
- Live does not notify when the object is deleted; the listener just stops firing. Listen on the parent collection
  (e.g. `Song.tracks`) to notice deletions.

## Updating this skill

Do not edit `references/` by hand. After a new capture in LiveAPI, update `provenance.json` and run:

```bash
python tools/gen_live_api_skill.py --seed ../LiveAPI/probe/12.4.6/seed --baseline ../LiveAPI/probe/12.3.6/seed --provenance .claude/skills/push3-live-api/provenance.json --out .claude/skills/push3-live-api/references
```

The generator needs PyYAML. Rules and quirks learned on the Push go in this file, not in `references/`.
