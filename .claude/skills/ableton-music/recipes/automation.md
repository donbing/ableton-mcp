# Recipe: automation (filter sweep, fades, movement)

Clip automation only writes on **Session** clips. Write it there, then place the clip with `duplicate_to_arrangement`: the automation comes along.

## Filter sweep on the keys (the one we could not do before)

Find the parameter's exact name first (the example below assumes "Frequency"; Live 12's Auto Filter may name it differently, so use what this returns):

```
get_device_parameters(track_index=3, device_index=2, name_contains="freq")   # Auto Filter
```

Sweep the low-pass open over a dedicated 8-beat clip (copy the keys clip into an empty slot first with `copy_clip_to_slot`, so the main clip stays clean):

```
set_clip_envelope(track_index=3, expected_name="Keys", parameter="Frequency", device_index=2,
                  clip_index=1, value_unit="display",
                  shape={"type": "curve", "start": 0, "end": 8, "min": 300, "max": 12000, "exponent": 2})
```

Preview (default) shows point counts and whether it replaces automation; repeat with `confirm=true`. `value_unit="display"` means Hz here, so no need to know the curve; `exponent: 2` starts slow and opens late, like a build. Reverse (closing) with `"invert": true`.

## Fades

Two points are enough (Live draws straight lines):

```
set_clip_envelope(track_index=3, expected_name="Keys", parameter="volume", clip_index=0,
                  value_unit="display", points=[{"time": 0, "value": -40}, {"time": 8, "value": 0}])
```

## Movement

- Pan wobble: `shape={"type": "sine", "period": 4, "min": -0.6, "max": 0.6}` on `parameter="pan"`.
- Stutter gate on a send or volume: `shape={"type": "square", "period": 0.5, "duty": 0.5}`.
- Random filter drift for lo-fi wobble: `"random_smooth"` with a narrow min/max.

Read back with `get_clip_envelope`; list what a clip has with `list_clip_envelopes`; remove with `clear_clip_envelope`.
