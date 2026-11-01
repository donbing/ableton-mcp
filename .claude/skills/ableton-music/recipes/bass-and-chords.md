# Recipe: bassline and chords

Worked example (2026-10-26): D minor, progression Dm9 - Bbmaj9 - A7b9 over 2 bars at 90 BPM.

## Bass

```
create_midi_track(index=-1)
search_browser_items(query="electric bass", category="sounds", loadable_only=true)
load_instrument_or_effect(track_index=2, uri="query:Sounds#Bass:FileId_5280")   # Electric Bass Soft
set_track_name(track_index=2, name="Bass")
create_clip(track_index=2, clip_index=0, length=8)
add_notes_to_clip(track_index=2, clip_index=0, notes=[
  {"pitch": 38, "start_time": 0,   "duration": 1.3, "velocity": 105},
  {"pitch": 38, "start_time": 1.8, "duration": 0.4, "velocity": 85},
  {"pitch": 41, "start_time": 2.5, "duration": 0.8, "velocity": 95},
  {"pitch": 38, "start_time": 3.5, "duration": 0.3, "velocity": 80},
  {"pitch": 36, "start_time": 3.8, "duration": 0.2, "velocity": 75},
  {"pitch": 34, "start_time": 4,   "duration": 1.3, "velocity": 105},
  {"pitch": 34, "start_time": 5.8, "duration": 0.4, "velocity": 85},
  {"pitch": 33, "start_time": 6.3, "duration": 0.2, "velocity": 80},
  {"pitch": 33, "start_time": 6.5, "duration": 0.8, "velocity": 95},
  {"pitch": 36, "start_time": 7.5, "duration": 0.3, "velocity": 80},
  {"pitch": 37, "start_time": 7.8, "duration": 0.2, "velocity": 85}])
```

Shape: root on the downbeat locked with the kick, a syncopated answer on the 'and', approach notes (C, C#) leading back to the root. A variation clip can jump roots up an octave (+12) on the offbeats.

## Chords (keys)

Voice chords in the C2-C4 range (48-72) so they sit between bass and vocal. Rootless voicings leave the root to the bass:

- Dm9: F A C E = 53 57 60 64
- Bbmaj9 (upper voicing, 3rd on top): F A C D = 53 57 60 62
- A7b9: E G Bb C# = 52 55 58 61

```
create_midi_track(index=-1)
search_browser_items(query="e-piano old school", category="sounds", loadable_only=true)
load_instrument_or_effect(track_index=3, uri="query:Sounds#Piano%20&%20Keys:FileId_4925")
create_clip(track_index=3, clip_index=0, length=8)
```

Place each chord as 4 notes with the same start: Dm9 at 0 (duration 2.3) and a re-hit at 2.5; Bbmaj9 at 4; A7b9 at 6.5 (anticipating bar 2's turnaround). Vary velocities 70-90 inside a chord so it does not sound stacked.

## Lo-fi keys chain

```
insert_device(track_index=3, expected_name="Keys", device_name="Redux")
insert_device(track_index=3, expected_name="Keys", device_name="Auto Filter")
get_device_parameters(track_index=3, device_index=1)   # find indices
```

Settings that worked: Redux bit depth 10, sample rate ~0.72 (raw), jitter 0.12, dry/wet 45%; Auto Filter frequency ~0.64 raw (about 2-3 kHz low-pass), resonance 0.15, drive 0.15, slow LFO (amount 0.08, rate 0.15). Use `set_device_parameter(..., display_value=...)` for Hz/dB/% values instead of raw numbers when the parameter shows units.
