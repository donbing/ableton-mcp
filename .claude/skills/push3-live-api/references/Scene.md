# Live.Scene

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Scene.Scene

This class represents an series of ClipSlots in Lives Sessionview matrix.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Song.Song`† (r): Get the canonical parent of the scene.
- `clip_slots` `Base.Vector[ClipSlot.ClipSlot]`† (r, listenable): return a list of clipslots (see class AClipSlot) that this scene covers.
- `color` `int`† (rw, listenable): Get/set access to the color of the scene (RGB).
- `color_index` (rw, listenable): Get/set access to the color index of the scene. Can be None for no color.
- `is_empty` `bool`† (r): Returns True if all clip slots of this scene are empty.
- `is_triggered` `bool`† (r, listenable): Const access to the scene's trigger state.
- `name` `str`† (rw, listenable): Get/Set the name of the scene.
- `tempo` `float`† (rw, listenable): Get/Set the tempo value of the scene. The song will use the scene's tempo as soon as the scene is fired. Returns -1 if the scene has no tempo property.
- `tempo_enabled` `bool`† (rw, listenable): Get/Set the active state of the scene tempo. When disabled, the scene will use the song's tempo,and the tempo value returned will be -1Returns a bool indicating the state of the scene's tempo
- `time_signature_denominator` `int`† (rw, listenable): Get/Set the scene's time signature denominator. The song will use the scene's time signature as soon as the scene is fired. Returns -1 if the scene has no time signature property.
- `time_signature_enabled` `bool`† (rw, listenable): Get the active state of the scene time signature. When disabled, the scene will use the song's time signature,and the time signature values returned will be -1Returns a bool indicating the state of the scene's time signature
- `time_signature_numerator` `int`† (rw, listenable): Get/Set the scene's time signature numerator. The song will use the scene's time signature as soon as the scene is fired. Returns -1 if the scene has no time signature property.

Methods:

- `fire(force_legato: bool, can_select_scene_on_launch: bool) -> None`: Fire the scene directly. Will fire all clipslots that this scene owns and select the scene itself.
- `fire_as_selected(force_legato: bool) -> None`: Fire the selected scene. Will fire all clipslots that this scene owns and select the next scene if necessary.
- `set_fire_button_state(arg2: bool) -> None`: Set the scene's fire button state directly. Supports all launch modes.
