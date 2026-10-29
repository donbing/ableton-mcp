# Live.Eq8Device

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Eq8Device.Eq8Device

This class represents an Eq8 device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `edit_mode` `bool`† (rw, listenable): Access to Eq8's edit mode.
- `global_mode` `int`† (rw, listenable): Access to Eq8's global mode.
- `oversample` `bool`† (rw, listenable): Access to Eq8's oversample value.

## Eq8Device.Eq8Device.View

Representing the view aspects of an Eq8 device.

Base: Device.Device.View, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `selected_band` `int`† (rw, listenable): Access to the selected filter band.

## Enums

- `EditMode`: a=0, b=1
- `GlobalMode`: stereo=0, left_right=1, mid_side=2
