# Recipe: Session clips to an Arrangement

Plan first, write second. Agree the structure with the user before placing anything.

## 1. Plan in bars, convert to beats

Example (4/4, 24 bars):

| Section | Bars | Beats | Keys | Bass | Drums |
|---|---|---|---|---|---|
| Intro | 1-4 | 0-16 | A | - | - |
| Verse 1 | 5-12 | 16-48 | A | A | A, A, A, Fill |
| Break | 13-14 | 48-56 | A | A | Pickup at 52 |
| Verse 2 | 15-22 | 56-88 | A | A, B, A, B | B, A, B, Fill |
| Outro | 23-24 | 88-96 | A | - | - |

An 8-beat clip covers 2 bars, so a section of N bars needs N/2 placements.

## 2. Place

```
duplicate_to_arrangement(track_index=3, clip_index=0, destination_time=0)    # repeat every 8 beats
duplicate_to_arrangement(track_index=1, clip_index=1, destination_time=40)   # the fill
```

Each call is one placement and overwrites what is there on that track. For long runs prefer fewer calls by planning, and check with `get_arrangement_clips(track_index)` and `check_arrangement_sync()` (off-grid clips, overlaps, gaps).

Editing after placement: `move_arrangement_clip`, `trim_arrangement_clip`, `split_arrangement_clip`, `clear_arrangement_range` (all preview first and need `expected_name`).

## 3. Locators

```
stop_playback()
create_locator(name="Verse 1", time=16)
```

The transport must be stopped; Live snaps locators to whole beats.

## 4. Hand back

`back_to_arrangement()` then `switch_to_arrangement_view()`, and tell the user the section map in bars. Remind them to save on the Push.
