# Recipe: a drum beat

Worked example: the 90 BPM boom bap beat built on 2026-10-26.

## 1. Tempo, track, kit

```
set_tempo(tempo=90)
create_midi_track(index=-1)
search_browser_items(query="boom bap kit", category="drums", loadable_only=true)
load_instrument_or_effect(track_index=1, uri="query:Drums#FileId_5369")   # Boom Bap Kit (uri from the search)
set_track_name(track_index=1, name="2-Boom Bap Kit")
get_drum_pads(track_index=1, device_index=0)   # confirm which note is which sound
```

Kits differ, so always read the pads with `get_drum_pads` and write to what is there. The Boom Bap Kit (read 2026-10-27): 36 kick, 37 rim, 38 snare, 39 clap, 40 second snare, 41 second kick, 42 closed hat, 43/45/47 toms, 44 second closed hat (no pedal hat), 46 open hat, 48 brass stab, 49 crash, 50 bass chop, 51 ride.

## 2. A 2-bar pattern (8 beats)

```
create_clip(track_index=1, clip_index=0, length=8)
set_clip_name(track_index=1, clip_index=0, name="Boom Bap 90")
add_notes_to_clip(track_index=1, clip_index=0, notes=[...])
```

Boom bap shape, per bar (beats 0-4, repeat at +4 for bar 2 with small changes):
- **Kick** 36: 0, 2.5 (bar 2: 0, 1.75, 2.5) - velocity 110-120
- **Snare** 38: 1, 3 - velocity 115; a ghost at 3.75 velocity 40
- **Hats** 42: every 0.5 beat, velocities alternating 85 / 60 for swing feel; nudge offbeats +0.03-0.06 beat for laid-back timing
- Duration 0.25 for hits

Humanize by varying velocity +-10 and a few starts by 0.01-0.03 beats; leave the kick and snare on the grid.

## 3. Variations in more slots

- Slot 1 **fill** (8 beats): the main bar, then bar 2 with snare 16ths from beat 3 (`38` at 3, 3.25, 3.5, 3.75, rising velocity 70 to 120).
- Slot 2 **pickup roll** (4 beats): snare 16ths across the last beat only.
- Slot 3 **B section** (8 beats): crash `49` at 0, open hat `46` on the 'and' of 4.

Name every clip (`set_clip_name`). Preview a slot with `fire_clip`, then `stop_clip` - and `back_to_arrangement` before Arrangement playback.

## Checks

The `add_notes_to_clip` reply says how many notes the clip holds and lists refused notes (start at or after the clip end). If the count is short, fix those notes rather than retrying blindly.
