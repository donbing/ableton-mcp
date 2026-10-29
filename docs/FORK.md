# About this fork

This is a community-maintained fork of [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp) (MIT, © Siddharth Ahuja). It exists because a lot of useful work is sitting in open pull requests upstream and the project's `main` has not moved since 2026-09-22. We want that work tested, reviewed and usable now, **without replacing or competing with upstream**: everything here is kept in small, separable branches so it can go back upstream, and we will converge with upstream if and when it becomes active again. See [upstream issue #142](https://github.com/ahujasid/ableton-mcp/issues/142) for the coverage map that started this.

Maintainer: [@vittorfp](https://github.com/vittorfp). One person, hobby time, tested on **Ableton Live 12 Lite (macOS)** only. Please read the limits below.

## What is in `main` of this fork

`main` = upstream `main` (`9dddc7b`) + the pieces below. Remote Script **1.10.25**, **144 MCP tools** (upstream: 37), 1487 tests (all pass, all against a mocked Live Object Model).

| Added | Tools / change | Origin |
|---|---|---|
| Mixer | `get_mixer`, `set_track_volume`, `set_track_panning`, `set_send` (tracks, returns, master; dB or raw; display strings) | upstream PR #122 by Jorge Nunes (@staminna), original commits kept; we added the version handshake / capability list / bundled-copy sync, pan parsed as pan (not dB), no `-Infinity` in JSON, and mocked-LOM tests |
| Track state | `set_track_mute`, `set_track_solo`, `set_track_arm` (optional `expected_name` guard against shifted indices) | new, branch `feat/track-mute-solo-arm` |
| Safe delete | `delete_track` with preview by default; deletes only with `confirm=true` and a matching `expected_name`; refuses return/master/last track | new, `feat/delete-track-guarded` |
| Meters | `get_meters(seconds, hz)`: windowed per-track peak/mean from `output_meter_left/right`, with the measured dB scale (the raw value is dB-linear, not amplitude) | new, `feat/get-meters` |
| Parameter reads | `get_device_parameters` gains Live's display strings, `name_contains`, `limit` and a rack guard (racks returned 58-433 KB) | new, `feat/param-display-strings` |
| Undo / redo | `undo`, `redo` guarded by `can_undo/can_redo` and `confirm=true` (Live merges every API edit into ONE undo step, so one undo can revert several changes) | new, `feat/undo-redo` |

**Verification status.** Release `v1.9.1-fork.1` and the slices ported in `v1.10.0-fork.1` were run on a real Live 12 Lite set (2026-10-22, results in [issue #1](https://github.com/vittorfp/ableton-mcp/issues/1)). Run and working: scenes (create, rename, duplicate, delete, fire), stop_all_clips, time signature, metronome, arrangement loop, return device load/delete, clip loop, quantize, note remove, note edit, arrangement clip delete, audio-clip info/warp/gain/pitch, guarded delete_track, undo preview. One bug found and fixed in 1.10.1: `apply_note_modifications` was rejected by Live in every direct argument shape, so it now falls back to remove + `set_notes` (note ids change; verified by value; the reply says `method`). `create_locator` was rewritten in 1.10.2 and run on Live (it now moves the playhead, waits for Live to apply it, toggles the cue, reads it back and restores the playhead; it refuses while the transport plays; Live puts locators on whole beats), and `jump_to_cue` was run with real cue points. Still NOT run on Live:  group-track delete, Arrangement-clip audio properties, upstream PR #143 export. Every destructive tool previews by default.

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
| Arrangement clip editing | `clear_arrangement_range`, `trim_arrangement_clip`, `split_arrangement_clip`, `move_arrangement_clip` (also copy), `create_arrangement_clip` (MIDI with notes, or audio from a file) | all preview by default, need `expected_name` and `confirm=true`. Live has no setter for a clip's start or end, so these are built on what it does: a clip placed over others overwrites them like a paste (tail shortened, head starts later with its content offset kept, a middle splits), and `duplicate_clip_to_arrangement` keeps extent and offset. Audio tracks need one empty Session slot (a silent clip is used for a moment). Same track, or another track of the same kind since 1.10.13 (`to_track_index`). |
| Locators | `delete_locator` (guarded) | same stepwise playhead move as `create_locator` |

| Taken from open upstream PRs in 1.10.4, authorship kept | What | Origin |
|---|---|---|
| Timeouts and sockets | each command keeps its own timeout (a 65 s audio import no longer fails after 15 s), responses split inside a UTF-8 character are completed, failed sockets are closed. Also our upstream issue #136. | upstream #139 (Parker Rex) |
| Quiet logs | expected errors (bad index, out-of-range value) log one line instead of a traceback. Also our upstream issue #135. | upstream #141 (Muhtasim Munif Fahim) |
| Terms | `TERMS.md` now says dataset recording starts off | upstream #147 (dajiaohuang) |

| Added in 1.10.5 (run on a real Live 12 Lite, 2026-10-23) | Tools | Origin |
|---|---|---|
| Back to Arrangement | `back_to_arrangement`: hand playback back to the Arrangement after `fire_clip` / `fire_scene` took tracks off it | adapted from upstream #119 (mateogon) |
| Track routing | `get_track_routing` (current and available type and channel, for tracks, returns and master), `set_track_routing` (type and/or channel, input or output; needs `expected_name`; waits for Live to list the channels of a new type) | adapted from upstream #99 (Zachary May), extended with channels, `track_type` and the name check. Two tracks with the same name cannot be chosen by name (the error says so). |

| Added in 1.10.6 (run on a real Live 12 Lite, 2026-10-24) | Tools | Notes |
|---|---|---|
| Notes | `add_notes_to_clip` now validates, writes with `Clip.add_new_notes` (so `probability`, `velocity_deviation`, `release_velocity` work), reads the clip back and reports how many notes it really holds and which it refused (a note starting at or after the clip end would never play). `apply_note_modifications` now edits **in place** (note ids and extra fields kept) and can change those three fields | our upstream issue #138. Root cause of the old failure: Live only accepts the `MidiNoteVector` that `get_notes_by_id` / `get_notes_extended` return, never a Python list or tuple made from it. |
| Sidechain | `get_device_routing`, `set_device_routing`: the "Audio From" (type and tap) of Compressor, Gate, Glue Compressor etc., and "S/C On" | the ducking setup (kick into the bass compressor). A bad channel after a good type puts the type back. Also done for `set_track_routing`. |
| Automation | `get_clip_envelope` (samples), `set_clip_envelope` (steps or ramp, preview by default), `clear_clip_envelope` | idea from upstream #23 (zzstoatzz), written from scratch. Session clips only: Live gives the API no envelope for an Arrangement clip, but a Session clip copied into the Arrangement keeps its automation (`get_arrangement_clips` shows `has_envelopes`). Parameters: volume, pan, send A/B, or a device parameter by name. Values in the parameter's own units. |

| Fixed in 1.10.7 (our upstream issues #134 and #137; run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Replies that read Live too early | `load_instrument_or_effect` now settles, then lists the devices Live really added (`devices_before`, `devices_after`, `new_devices`); `set_arrangement_time` reports where the playhead really is and warns if it did not move | upstream issue #134: Live applies the change a moment later, so the same-tick read showed an empty chain and the old position |
| Auto-warp on import | `create_audio_clip` reports `warping`, the file's own length and what that is in beats at the set's tempo, and warns when Live's auto-warp changed the length; `warping=false` keeps the file's own timing | upstream issue #137 |

| Added in 1.10.8 (run on a real Live 12 Lite, 2026-10-24) | Tools | Origin |
|---|---|---|
| Overview and check | `get_tracks_overview` (every track, return and master in one compact read), `check_arrangement_sync` (clips off the grid, overlaps, gaps) | adapted from upstream #110 (M4x28) |
| Replace notes | `replace_clip_notes`: all notes of a Session MIDI clip swapped for new ones; validated before anything is removed, the old notes put back if the write fails; preview by default | adapted from upstream #119 (mateogon) |
| Colours | `set_color` for a track, a Session clip or a scene (palette index 0-69) | adapted from upstream #99 (Zachary May), merged into one tool |

`create_volume_fade` from #110 is not ported: `set_clip_envelope` in ramp mode already writes a fade (on a Session clip, which keeps it when copied to the Arrangement).

| Added in 1.10.9 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Notes in Arrangement MIDI clips | `get_clip_notes`, `get_clip_info`, `add_notes_to_clip`, `clear_notes_from_clip`, `remove_notes_from_clip`, `apply_note_modifications`, `quantize_clip` and `replace_clip_notes` take an optional `clip_start_time` (the clip's start beat) to work on an Arrangement MIDI clip instead of a Session slot | measured: the note API works on Arrangement clips (the old claim that they are read-only for notes was wrong). Times are in the clip's content; a clip trimmed or split at its head keeps all its notes and starts at `start_marker`. |

| Added in 1.10.10 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Devices on returns and the master | `get_track_info`, `get_device_parameters` and `set_device_parameter` take `track_type` ("track", "return", "master") | closes the old gap "return-track and master device parameters cannot be written": the reverb and delay on the returns can now be read and set |
| Monitoring | `set_track_monitoring` ("in", "auto", "off"); `get_tracks_overview` shows it | useful before recording a guitar or a mic |
| Duplicate a track | `duplicate_track`: devices, clips and mixer, copy placed after the original; refused cleanly at Live Lite's 8-track limit | from upstream #94 (Luke Gimza) |

| Added in 1.10.11 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Browser search | `search_browser_items(query, category, max_results, loadable_only, max_seconds)`: items whose name (or folders below the category root) contain every word, with the uri `load_instrument_or_effect` takes | idea from upstream #97 (vanjaoljaca). Breadth first with a time budget; `truncated` says when to narrow it. On the real browser: about 300 to 2500 items a second. |
| Sound tags | `list_sound_tags(prefix)`, `search_sounds_by_tags(tags, query, kind, max_results, available_only, max_seconds)`: Live 12's browser tags (Character\|Soft, Sounds\|Pad, Type\|One Shot...), read by the server from the libraries' `Ableton Folder Info/*.xmp` files, since Live's API has no tags | Each hit is looked up in Live's browser for its uri, and what the edition hides (Suite presets on Intro) is left out; a device the browser lacks rules out its presets in one lookup. Libraries: `/data/Music/Ableton`, `~/Music/Ableton`, `~/Documents/Ableton`, or `ABLETON_LIBRARY_ROOTS`. On a Push 3 (Intro): 7,000 tagged Core Library items; 2 to 4 s for a first search, under 0.1 s repeated. |

| Changed in 1.10.12 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Automation with real breakpoints and wave shapes | `set_clip_envelope` now writes REAL breakpoints (mode `linear`, the default: a fade is two points) and takes `shape`: `sine`, `triangle`, `saw_up`, `saw_down`, `square`, `random_steps`, `random_smooth`, `curve`, with `period` or `cycles`, `min`/`max`, `phase`, `points_per_cycle`, `duty`, `seed`, `exponent`, `invert` | measured: `Envelope.create_event(Live.Envelope.EnvelopeEvent(time, value))` makes a breakpoint and Live draws straight lines between breakpoints; a zero-length `insert_step` is only a spike, and the Bezier control coefficients are ignored. A sine is `points_per_cycle` breakpoints per cycle (16: within 2% of the amplitude; 32: within 0.5%). `ramp` still works (same as linear); `steps` still holds each value. |

| Added in 1.10.13 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Move or copy an Arrangement clip to another track | `move_arrangement_clip` takes `to_track_index` and `to_expected_name`; `new_start_time` defaults to the same beat | measured: `Track.duplicate_clip_to_arrangement` accepts a clip from another track of the same kind (MIDI to MIDI, audio to audio; Live answers "Incompatible track types" for the rest) and keeps its extent, content offset and notes. The preview lists what the destination loses. |

| Fixed in 1.10.14 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Deleting a group track | `delete_track` on a group now deletes the group first, which takes its members with it | found on a real group: deleting the members one by one fails on the last one ("Couldn't delete track.") and left the set half deleted. If Live stops partway the error now says how many tracks are left and how to undo. A real delete of a group with 3 members, then one undo, brought all 7 tracks back. |
| `get_tracks_overview` with a group | the monitoring state is read defensively (a group track raises when it is read); each member shows its `group` | |

| Added in 1.10.15 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| One undo step per tool call | every state-changing tool runs between `Song.begin_undo_step` and `end_undo_step` | measured: without them Live merged every API edit into one undo step; with them three tool calls took three undos, each reverting exactly one, and three redos restored them. Tools that work in several ticks (`create_locator`, `set_track_routing`, `set_device_routing`) are not wrapped: a step left open across ticks would swallow the user's own edits. The `undo` warning says so. |
| Live's health | `get_live_status`: version and edition, CPU average and peak, performance impact per track (heaviest first), features the edition lacks, open dialog | |
| Modal dialogs | `press_dialog_button(button_index, expected_message)`: Live reports the dialog's text and how many buttons it has, not their labels. The "number of tracks is limited to 8" box has 2 buttons and index 0 closes it | the Remote Script keeps answering while a dialog is open, so the dialog can be read and pressed from the tool |

| Added in 1.10.16 (found by dumping Live's own API and crossing it with what the script uses; all run on a real Live 12 Lite, 2026-10-24) | Tools | Notes |
|---|---|---|
| Devices by name | `insert_device` (a native device by name at a chain position, no browser), `move_device` (inside the chain or to another track), `duplicate_device` | Live Lite answers "not available" for EQ Eight and Glue Compressor |
| Key and scale | `get_song_scale`, `set_song_scale` | Live does NOT raise for an unknown scale name, it falls back to Major: the tool reads it back and puts the old scale back |
| Scene tempo | `set_scene_tempo` (tempo, time signature, or clear) | launching the scene changes the set's tempo |
| Grooves | `get_grooves`, `set_groove` (amounts and the global amount), `set_clip_groove` | the API cannot take a groove away from a clip (it refuses None) |
| Warp markers | `edit_warp_marker` (add, move, remove) | `Clip.WarpMarker(seconds_in_file, beat)`: seconds first |
| Clip copies | `duplicate_clip_loop` (double a MIDI loop with its notes), `copy_note_region` (repeat a stretch, transposed), `copy_clip_to_slot` | |
| Parameters | `get_device_parameters` now returns `items` (the choices) for quantized parameters and `default` for the others | |
| `get_live_status` | features this edition lacks come by name: Live Lite lacks `note_velocity_ranges_and_probabilities` | so the `probability` of a note may be stored but not played on Lite |

| Added in 1.10.17 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| A recording of your own as an instrument | `configure_simpler`: replace a Simpler's sample with any audio file on disk, set `playback_mode` (classic, one-shot, slicing), `retrigger`, `slicing_playback_mode` | measured: loading a sample from the browser onto a MIDI track already creates a Simpler (class `OriginalSimpler`); `Simpler.replace_sample(path)` swaps the file, and Live renames the device and the track after the file, so later calls need the new names (the name guard refuses the old ones) |

| Added in 1.10.18 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Parameters in the unit Live shows | `set_device_parameter(display_value=...)`: say 80 (Hz), -6 (dB), 250 (ms) instead of a raw 0..1 value. `get_device_parameters` returns `display_value` for every non-choice parameter, plus the device's `is_active` and `latency_ms` | measured: Live limits a number outside the range WITHOUT an error (a -100 dB threshold becomes -inf), so the reply says `clamped`; times are in ms (1456 = "1.46 s"), frequencies in Hz (1000 = "1.00 kHz"); a choice parameter takes its position in `value` |
| Automation in display units | `set_clip_envelope(value_unit="display")`: points and shape min/max in Hz, ms, dB or %, converted by Live itself (the parameter is set and put back) | a filter sweep is `min: 80, max: 10000`; the shape still runs between the two raw ends |
| Input level | `get_meters(source="input")`: the level arriving at each track's input (audio tracks left/right, MIDI one value) | the level to check before recording; the dB conversion was calibrated on outputs only |
| A/B compare | `compare_device_ab` (status, save, switch, use_a, use_b) | `save` copies the CURRENT settings into the other slot; Live's own devices only (a VST/AU plug-in has none) |
| Clip automation | `list_clip_envelopes` (which parameters, owner), `clear_all_clip_envelopes`, `crop_clip` (both preview first) | `crop_clip` on an audio clip writes a new, shorter file |
| Take lanes | `get_take_lanes`, `create_take_lane` | the API cannot pick the active take: the comp is chosen in Live |
| Groups | `set_track_fold` | `fold_state` is true when folded |
| What the user is looking at | `get_ui_state` (focused view, open panels, selected track, scene, clip, device, parameter), `show_in_ui` (select a track, scene, clip or device, focus a view, show a clip's envelope parameter) | nothing in the Set changes. `Application.show_on_the_fly_message` is NOT offered: it opens a modal dialog that blocks Live's main thread until someone clicks it |
| Song state | `get_live_status` adds `last_event_time`, `can_capture_midi`, `automation_overridden`, punch in/out, overdub, record mode, count-in; `re_enable_automation`; `capture_midi` | `capture_midi` refusal run on Live; the capture itself NOT run (it needs MIDI played) |

| Added in 1.10.19 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Recording and launch options | `set_transport_options`: punch in/out, Arrangement overdub, clip launch quantization, MIDI recording quantization (no arguments = read). It never starts recording | measured: Live applies these flags on the NEXT tick, so the tool waits and reads back (`not_applied` lists any that did not land); a bad name changes nothing |
| Return tracks | `delete_return_track` (preview, then `confirm=true`) | Live Lite holds 2 returns: this is how to swap one |
| Drum Racks | `get_drum_pads` (note, name, mute, solo, chains, devices), `set_drum_pad` (mute/solo by MIDI note) | an empty pad cannot be muted or soloed: the tool says so |
| Rack macro variations | `rack_variations`: status, store, recall, delete, randomize (delete and randomize preview first) | `store` on a rack with no mapped macro works but holds nothing audible: the reply warns |
| Previews | `preview_browser_item`, `stop_browser_preview` (the headphone button of the browser) | the user hears it; nothing enters the Set |
| Plug-in windows | `set_plugin_window` (open or close AmpliTube, Analog Lab and other VST/AU windows) | Live's own devices have no window |

| Added in 1.10.20 (run on a real Live 12 Lite, 2026-10-24) | What | Notes |
|---|---|---|
| Clip launch settings | `set_clip_launch` (launch quantization, launch mode trigger/gate/toggle/repeat, legato); `get_clip_info` now returns them | Session clips only; they apply at once |
| Why a track is silent | `get_tracks_overview` rows carry `muted_via_solo` and `frozen`, only when true | measured: soloing one track marks every other track `muted_via_solo` |

| Added in 1.10.21 (run on Push 3 standalone, Live 12.4.6, 2026-10-26) | What | Notes |
|---|---|---|
| Start and end a take | `record_into_slot` (an armed track into one EMPTY Session slot, optional `length_bars`), `start_arrangement_record` (every armed track, optional `start_time` / `end_time`), `stop_recording` (Arrangement, Session and slot takes; optional `stop_transport`) | until now the tools could arm, route and monitor a track but never press record. Both starts preview by default (inputs, monitoring, launch quantization, the Arrangement clips a take records over, warnings for No Input, monitoring "in", Session playback and a loop that ends before `end_time`) and need `confirm=true`. Measured: `ClipSlot.fire(record_length=beats)` is accepted and the take stops at exactly that length, then loops (a plain fire is the fallback for a Live without the keyword); `Song.record_mode` plus `start_playing()`; the `end_time` auto-stop is polled once a tick (a 16-24 take ended at 24.03). A mic on Ext. In 1 was recorded both ways |

| Added in 1.10.22 (run on Push 3 standalone, Live 12.4.15, 2026-10-29: tree at depth 1 and 3, paging, kind filter, uris) | What | Notes |
|---|---|---|
| Browser overview | `get_browser_tree(category_type, depth, with_counts)`: 11 roots (the old 8 plus samples, clips, current_project; category names are an enum in the tool schemas), 1-3 levels, the loadable items below each folder (`item_count`), 50 children listed per folder with `total_children` and `truncated` | counts share a 5 second budget and are `approximate` when it runs out. Replaces the one-level, 64-child, five-root view |
| Browser paging | `get_browser_items_at_path(path, offset, limit, compact, kind)`: `total`, `offset`, `limit`, `next_offset`; compact items are `{name, type}` (folder, device, preset, sample) with `item_count` on folders; `compact=false` keeps the uri | `kind` filters before paging. `load_drum_kit` asks for 200 full items so it still finds every kit |

| Added in 1.10.23 (Live 12.4.15+; run on Push 3 standalone, Live 12.4.15, 2026-10-28) | What | Notes |
|---|---|---|
| Clip scales | `set_clip_scale` (a MIDI clip's own `root_note`, `scale_name`, `scale_mode`; Session or Arrangement); `get_clip_info` returns the clip's `scale`; notation writes scale degrees (`^1 ^3 ^5`, `^b7`, `^1:1` for octave 1) in the clip's scale, else the Set's; `get_clip_notes(format="text")` names the clip's scale | Clip.root_note / scale_name / scale_mode (settable) and scale_intervals (read-only) are new in Live 12.4.15, captured on the Push; an older Live gets a clear refusal. Song and clip share one validated writer, so an unknown scale name is put back as for `set_song_scale`. Measured: a new clip starts with the Set's scale; setting the clip's leaves the Set's alone; an unknown name makes Live answer Major, as for Song; `^1:1 ^1 ^3 ^5` in A minor wrote A1 A3 C4 E4 |

| Fixed in 1.10.24 (run on Push 3 standalone, Live 12.4.15, 2026-10-29) | What | Notes |
|---|---|---|
| Commands after loading another Set | `disconnect()` shuts down the open client sockets and a stopped instance closes a connection without answering, so the MCP server reconnects to the new instance | the old client thread sat in `recv()` across the Set load and served the next command with the destroyed Song: `get_tracks_overview` failed on the Push with `None.None(Song) did not match C++ signature: None(TPyHandle<ASong>)` (Live log: "Client thread still alive during disconnect"). Measured: with 1.10.23 the first `get_tracks_overview` after a Set load failed every time; with 1.10.24 the old connection closes during the load, the server reconnects and the first call works. A new Remote Script needs Live restarted; loading a Set keeps the old module |

| Changed in 1.10.25 (run on Push 3 standalone, Live 12.4.15, 2026-10-29: 3-bar passes on both scripts, both refusals) | What | Notes |
|---|---|---|
| Measured | 3 bars of "Arcing the Singularity" at 106 bpm ("bar" quantization, 6.8 s of audio): with 1.10.25 the whole call took 9.9 s and polled `get_slot_state` 14 times (`get_track_info` once, before recording); with 1.10.24 (the fallback) 11.5 s and 18 `get_track_info` polls. Live's CPU (`get_live_status`, every 2 s): 9.3 % average / 15.9 % peak before, 7.7-8.1 % / 14.1-21.1 % during, 7.5 % / 13.0 % after (fallback run: 7.3-8.2 % / 11.5-15.6 % during). Both takes about -29.3 LUFS, -12.4 dBTP. Launch quantization "quarter": refused in 0.75 s; 32 bars: refused in 0.85 s ("72 s of recording, plus up to 2 s ... at most 25 bars fit"); neither wrote a file | run with the installed server called directly on the Push (`asyncio.run(server.listen(...))`), as the MCP session predated the deploy |
| `listen` and `analyze_audio_clip` stay out of Live's way | ffmpeg runs under `nice -n 10` (where `nice` exists) with `-threads 1 -filter_threads 1 -filter_complex_threads 1`, and its timeout is 2 x the audio's length + 10 s instead of a flat 120 s | `listen` needs Live playing, and the music goes on after the take, so ffmpeg (a spectrogram takes about 1 s per second of audio on the Push) shared Live's 4 cores with its audio thread |
| A pass is capped by time | besides 32 bars, `listen` refuses a pass whose launch wait + take is over 60 s, and says how many bars fit at the current tempo (120 bpm with "bar": 29; 70 bpm: 16). `spectrogram=True` is refused for takes over 30 s; `analyze_audio_clip` returns the text without the image for files over 30 s | 32 bars at 70 bpm was about 110 s of recording plus up to 110 s of spectrogram: near the old ffmpeg timeout, and a 4-minute tool call is past some MCP clients' timeouts |
| Bars line up | `listen` reads the Set's launch quantization first (`set_transport_options` with no arguments) and refuses anything but "bar", "2 bars", "4 bars" or "8 bars", saying to set `clip_trigger_quantization="bar"` | at a beat, sub-beat or "none" the take starts mid-bar and every row of the per-bar table was silently shifted. An empty slot has no clip launch quantization of its own, so the Set's applies |
| Lighter polling | new Remote Script command `get_slot_state(track_index, clip_index)`: one slot's `has_clip`, `is_triggered`, `is_recording` and its clip's `is_recording`, `is_playing`, `length`. `listen` polls it every 0.5 s (was `get_track_info`, every slot, device and mixer of the track, every 0.25 s); against an older Remote Script it falls back to `get_track_info` | the take's deadline logic is unchanged |

| Added on the server only (no Remote Script change) | What | Notes |
|---|---|---|
| Notes as text | `add_notes_to_clip` and `replace_clip_notes` take `notation` instead of `notes`; `get_clip_notes(format="text")` reads a clip back the same way (`MCP_Server/notation.py`) | events (`1.1 C3 E3 G3 1/1 v90`) and step patterns (`C1 x...x...x...x... *4`), Live's positions and octave numbering, random velocity ranges, probability, release velocity, repeats; every line stands alone; any bad line means nothing is written. Any clip round-trips exactly, except a velocity range that reaches below 0, which is written ending at 0 and sounds the same |
| Listening | `listen(scratch_track_index, expected_name, bars)` records Live's own output on a scratch audio track and measures the take; `analyze_audio_clip(track_index, clip_index)` measures an existing audio clip's file (`MCP_Server/listen.py`) | both report integrated loudness, loudness range and true peak (ebur128), peak and RMS (astats), silent stretches (silencedetect) and a table with one row per bar: RMS, peak and low (<250 Hz) / mid / high (>4 kHz) band RMS, from one ffmpeg call on the machine the server runs on (the Push: ffmpeg 5.0.3, no Python dependencies); a spectrogram image only when asked. `listen` refuses unless the track's input is Live's output (Resampling, Main or a track) with monitoring off, and unless Live is playing; it only reroutes for `source` (below). It arms the track for the take, waits within launch wait + length + 3 s, stops and deletes the take's clip (`keep=true` keeps it; the WAV stays in the project) and restores every arm, including tracks Exclusive Arm disarmed. Run on Push 3, Live 12.4.15, 2026-10-29: 2 bars of "Hihat Clap House 120 bpm" resampled in 6.5 s measured −21.3 LUFS, −3.0 dBTP, RMS −27.1 dB, the same per bar as the source file (−21.4 LUFS, −3.0, −27.1). Bars count from the start of the file at the set's tempo, so they line up for takes, not for samples at another tempo |
| Listening to one part | `listen(..., source="<track>")` points the scratch track's input at that track (or a return, or Main) on its Post Mixer tap for the take, then puts the input back as it was, also when no take comes; `source` must be one of the scratch track's offered inputs other than Ext. In and No Input, and monitoring must still be off | nothing the user hears changes (no solo). Post Mixer includes the track's fader and pan but not its sends, and comes before the Main fader, while Resampling comes after it: with Main at -9 dB a part reads about 9 dB hotter than it sounds in the mix. Run on Push 3, Live 12.4.15, 2026-10-29, 4 bars of "Arcing the Singularity" Drop B: pizz alone mid -27 dB, arp alone mid -35 dB, low -31 dB, the mix (Main -9 dB) mid -34 dB; input back on Resampling after each pass |
| Spectrograms of part of a take | `spectrogram_bars="13-16"` draws only those bars (seeking before `-i`, so a 16-bar take can still get a picture of 4 of them) and `spectrogram_max_hz=2000` draws up to that frequency by resampling to twice it first, on `listen` and `analyze_audio_clip`; either implies `spectrogram=True`. A spectrogram that fails no longer loses the measurement: the text comes back with "No spectrogram: ..." | the 30 s limit now applies to what is drawn. showspectrumpic's own `start`/`stop` frequency options took over 85 s for 9 s of audio on the Push (ffmpeg 5.0.3), against 7.2 s without them and 7.4 s with the resampling, so they are not used. A drawn image is about 600 tokens |
| Opening and saving Sets | `list_sets()` lists the Sets in the Push's Set-browser order and marks the open one; `which_set()` names the open Set; `load_set(name)`, `new_set()` and `save_set()` (preview, then `confirm=true`) press the Push 3's own buttons (`MCP_Server/push_ui.py`, `MCP_Server/push_midi.py`) | Live's API cannot open or save a Set. On the Push the server writes the bytes the hardware sends into the Push3 UI's ALSA input "Ableton Internal Input" (system `/usr/bin/python3` with python-rtmidi, run as a subprocess) and reads the lights it sends back on "Ableton Internal Output". Load: Sets (CC80; light 127 = the browser opened on its top entry, 14 = it was open and closed, so press again; no light = stop), the jog wheel (CC70 in touch note 11, 1 = one entry down) to the Set's position (project folders newest first, [Autosave] ones included), the jog press (CC94), then Live's Log.txt must say `Loading document` with that Set's file. If the open Set has unsaved changes the Push (not Live) asks "Save changes before closing?" and lights Don't Save CC24 and Cancel CC26 white (122) and Save CC27 green (126); `unsaved="ask"` (default) presses Cancel and closes the browser (pressing Sets until its light no longer says open), `"save"` / `"discard"` answer it (measured on the Push: Cancel is CC26 and returns to the browser). Save: CC82, then a Set file must be written within 8 s (its light goes off). New Set: Sets, then "+ New Set", the second button above the screen (CC103, lit 122 while the browser is open; captured on the Push 2026-10-29), which asks the same save question and then loads the default template (`unsaved` as in `load_set`); run on the Push: `unsaved="ask"` pressed Cancel and left the open Set, `unsaved="discard"` answered Don't Save and Live loaded DefaultLiveSet.als (120 bpm, 4 tracks). `which_set` reads the last `Loading document` line, skipping the default tracks Live also logs that way when a track is created (`.../Defaults/Creating Tracks/MIDI Track/Default MIDI Track.als`), so a new Set saved under a name for the first time still reads as the template. Steps measured by hand on Push 3, Live 12.4.15, 2026-10-29 (Set 12 loaded from Set 12-1). `save_set` run there: saved "Arcing the Singularity" at 106 bpm (light off, file rewritten, old one in Backup/); on a Set with nothing to save, Save is dark and the press does nothing, which it reports. `load_set` run there: loaded "Set 12" (entry 3) from "Arcing the Singularity", one Sets press and 2 jog steps, confirmed in Live's log. Also run there: `unsaved="ask"` twice (Cancel, browser closed, Set file untouched) and `unsaved="save"` (Arcing rewritten at 106 bpm, old copy in Backup/, then Set 12-1 opened). Missing media: a Set whose files Live cannot open makes the Push say "some referenced media files are missing" and wait for OK; about 2 s after the load turns every light off only OK (CC27) lights green (126), the Sets button gets no answer until OK is pressed, and Live logs `Exception: The file "<name>" could not be opened.` `load_set` waits up to 6 s after the jog press for that green, names the files from the log and leaves OK to the user, or with `missing_media="ok"` presses OK (CC27; the Push relights every button, Sets at 14); run on the Push: Set 12-1 reported "silence.wav" and the warning in 4.9 s, a clean load reported none, and `missing_media="ok"` closed the warning so Arcing loaded straight after |

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

Brought in with 1.10.0 (mocked-LOM tests, real-Live run pending): scenes, return tracks, transport, audio-clip warp, note editing (#99), delete Arrangement clips (#110, #119), delete device (#23). Still to do from open upstream PRs: routing (#99), automation envelopes (#23), real-time audio export by resample capture (#143, needs a real-Live run first), record/analyze audio (#133 needs BlackHole; on the Push, `listen` resamples Live's output and measures it with ffmpeg instead).

Not implemented anywhere we found, planned by us: return/master device parameters; device reorder; browser search and preview.

## Reconciling with upstream

If upstream merges a piece we ship, we drop our copy at the next sync. If upstream becomes active and wants any branch here, we will send it as PRs. If the maintainers of the open PRs would rather their work land through this fork (or want to review how we adapted it), say so on the PR or open an issue here.

## Reporting problems

Open an issue here for anything specific to this fork. For behaviour shared with upstream, an upstream issue is still welcome; mention the version (`get_remote_script_info`).
