# About this fork

This is a community-maintained fork of [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) (MIT, © Siddharth Ahuja). It exists because a lot of useful work is sitting in open pull requests upstream and the project's `main` has not moved since 2026-09-22. We want that work tested, reviewed and usable now, **without replacing or competing with upstream**: everything here is kept in small, separable branches so it can go back upstream, and we will converge with upstream if and when it becomes active again. See [upstream issue #142](https://github.com/ahujasid/ableton-mcp/issues/142) for the coverage map that started this.

Maintainer: [@vittorfp](https://github.com/vittorfp). One person, hobby time, tested on **Ableton Live 12 Lite (macOS)** only. Please read the limits below.

## What is in `main` of this fork

`main` = upstream `main` (`9dddc7b`) + the pieces below. Remote Script **1.10.3**, **80 MCP tools** (upstream: 37), 911 tests (all pass, all against a mocked Live Object Model).

| Added | Tools / change | Origin |
|---|---|---|
| Mixer | `get_mixer`, `set_track_volume`, `set_track_panning`, `set_send` (tracks, returns, master; dB or raw; display strings) | upstream PR #122 by Jorge Nunes (@staminna), original commits kept; we added the version handshake / capability list / bundled-copy sync, pan parsed as pan (not dB), no `-Infinity` in JSON, and mocked-LOM tests |
| Track state | `set_track_mute`, `set_track_solo`, `set_track_arm` (optional `expected_name` guard against shifted indices) | new, branch `feat/track-mute-solo-arm` |
| Safe delete | `delete_track` with preview by default; deletes only with `confirm=true` and a matching `expected_name`; refuses return/master/last track | new, `feat/delete-track-guarded` |
| Meters | `get_meters(seconds, hz)`: windowed per-track peak/mean from `output_meter_left/right`, with the measured dB scale (the raw value is dB-linear, not amplitude) | new, `feat/get-meters` |
| Parameter reads | `get_device_parameters` gains Live's display strings, `name_contains`, `limit` and a rack guard (racks returned 58-433 KB) | new, `feat/param-display-strings` |
| Undo / redo | `undo`, `redo` guarded by `can_undo/can_redo` and `confirm=true` (Live merges every API edit into ONE undo step, so one undo can revert several changes) | new, `feat/undo-redo` |

**Verification status.** Release `v1.9.1-fork.1` and the slices ported in `v1.10.0-fork.1` were run on a real Live 12 Lite set (2026-10-22, results in [issue #1](https://github.com/vittorfp/ableton-mcp/issues/1)). Run and working: scenes (create, rename, duplicate, delete, fire), stop_all_clips, time signature, metronome, arrangement loop, return device load/delete, clip loop, quantize, note remove, note edit, arrangement clip delete, audio-clip info/warp/gain/pitch, guarded delete_track, undo preview. One bug found and fixed in 1.10.1: `apply_note_modifications` was rejected by Live in every direct argument shape, so it now falls back to remove + `set_notes` (note ids change; verified by value; the reply says `method`). `create_locator` was rewritten in 1.10.2 and run on Live (it now moves the playhead, waits for Live to apply it, toggles the cue, reads it back and restores the playhead; it refuses while the transport plays; Live puts locators on whole beats), and `jump_to_cue` was run with real cue points. Still NOT run on Live: `undo`/`redo` with `confirm=true`, group-track delete, Arrangement-clip audio properties, upstream PR #143 export. Every destructive tool previews by default.

| Ported in 1.10.0 (run on a real Live 12 Lite on 2026-10-22, see status) | Tools | Origin |
|---|---|---|
| Delete Arrangement clips | `delete_arrangement_clips(track_index, expected_name, start_time, end_time, confirm)`: clips that START in [start, end), refuses more than 64 matches | upstream #110 (Leo) and #119 (mateogon), authorship kept |
| Delete device | `delete_device(track_index, device_index, expected_name, expected_device_name, confirm, track_type)` | upstream #23 (zzstoatzz), authorship kept |
| Scenes | `get_scenes`, `create_scene`, `delete_scene` (guarded), `duplicate_scene`, `fire_scene`, `set_scene_name`, `stop_all_clips` | upstream #99 (Zachary May), adapted |
| Returns and transport | `create_return_track`, `load_device_on_return`, `set_time_signature`, `set_metronome`, `get_arrangement_loop`, `set_arrangement_loop`, `get_cue_points`, `jump_to_cue` | upstream #99, adapted (no locator create/delete: that is a known race, see [issue #4](https://github.com/vittorfp/ableton-mcp/issues/4)) |
| Audio clip properties | `get_audio_clip_info`, `set_audio_clip_warp`, `set_audio_clip_gain`, `set_audio_clip_pitch` (Session slot or Arrangement clip): lets you read and change the warp that `create_audio_clip` turns on and rounds | upstream #99 / #119, adapted |
| Note editing | `get_clip_info`, `set_clip_loop`, `remove_notes_from_clip` and `apply_note_modifications` and `quantize_clip` (all three preview by default) | upstream #99, #84, #119, adapted |

| Added in 1.10.3, written here (run on a real Live 12 Lite, 2026-10-23) | Tools | Notes |
|---|---|---|
| Arrangement clip editing | `clear_arrangement_range`, `trim_arrangement_clip`, `split_arrangement_clip`, `move_arrangement_clip` (also copy), `create_arrangement_clip` (MIDI with notes, or audio from a file) | all preview by default, need `expected_name` and `confirm=true`. Live has no setter for a clip's start or end, so these are built on what it does: a clip placed over others overwrites them like a paste (tail shortened, head starts later with its content offset kept, a middle splits), and `duplicate_clip_to_arrangement` keeps extent and offset. Audio tracks need one empty Session slot (a silent clip is used for a moment). Same track only. |
| Locators | `delete_locator` (guarded) | same stepwise playhead move as `create_locator` |

Each `feat/*` branch is also pushed on its own, so it can be reviewed or sent upstream separately.

## Install

```json
{ "mcpServers": { "AbletonMCP": { "command": "uvx",
  "args": ["--from", "git+https://github.com/vittorfp/ableton-mcp", "ableton-mcp"] } } }
```

```bash
uvx --from git+https://github.com/vittorfp/ableton-mcp ableton-mcp-install-script --list-targets   # preview
uvx --from git+https://github.com/vittorfp/ableton-mcp ableton-mcp-install-script
```

Then restart Live and re-select the AbletonMCP control surface. Use **either** this fork **or** upstream, not both. Pin a release tag (for example `@v1.10.0-fork.1`) if you want a stable install.

## What we commit to

- **A first response to every issue and pull request within 7 days.** Even if it is only "seen, here is when we will look" or "we won't take this, because ...".
- **Small PRs first.** Anything under ~250 lines with tests is reviewed first; big ones get a request to split, with concrete suggestions.
- **Real-Live checks where we can.** New behaviour is run on a real Live 12 Lite set, not only against mocks, and the results are written in the PR. What we could not run is labelled "not run on Live".
- **Credit.** Work from upstream PRs is brought in with the original authorship (cherry-pick / merge, never a squash that hides authors) and a link to the PR.
- **Honest changelog.** Every release says what was verified on real Live and what was not.
- **A monthly sync with upstream `main`**, kept visible in the branch `upstream-main` (a pure mirror).

## Limits

Single maintainer on spare time; tested on one edition of Live (Lite, 8 tracks) and one OS (macOS); no promise about response time beyond the 7-day first reply; features implemented in open upstream PRs that we have not yet reproduced on Live are listed in the roadmap, not shipped.

## Roadmap (from the coverage map in upstream #142)

Brought in with 1.10.0 (mocked-LOM tests, real-Live run pending): scenes, return tracks, transport, audio-clip warp, note editing (#99), delete Arrangement clips (#110, #119), delete device (#23). Still to do from open upstream PRs: routing (#99), automation envelopes (#23), real-time audio export by resample capture (#143, needs a real-Live run first), record/analyze audio (#133, needs BlackHole and ffmpeg so probably not).

Not implemented anywhere we found, planned by us: moving a clip to ANOTHER track; return/master device parameters; device reorder; browser search and preview.

## Reconciling with upstream

If upstream merges a piece we ship, we drop our copy at the next sync. If upstream becomes active and wants any branch here, we will send it as PRs. If the maintainers of the open PRs would rather their work land through this fork (or want to review how we adapted it), say so on the PR or open an issue here.

## Reporting problems

Open an issue here for anything specific to this fork. For behaviour shared with upstream, an upstream issue is still welcome; mention the version (`get_remote_script_info`).
