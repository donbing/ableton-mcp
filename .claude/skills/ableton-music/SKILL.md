---
name: ableton-music
description: Make music in Ableton Live on the user's Push 3 through the ableton-push MCP server - beats, basslines, chords, arrangement, automation (filter sweeps), mixing and recording vocals. Use whenever the user wants to create or change anything in their Live set, record into it, check mic levels, light the FP-10's LED strip, or asks whether the Ableton connection works. Covers the fork with recording tools (record_into_slot, start_arrangement_record, stop_recording). Not for developing the MCP server itself.
---

# Making music on the Push 3

The user's Push 3 runs standalone Live 12.4.15. The `ableton-push` MCP server runs ON the Push over SSH (see `doctor.md`). Everything happens through MCP tools; this skill is how to use them well.

## Before anything: is it connected, and is the tool list current?

Call `get_remote_script_info`. It should say `up_to_date: true` (`script_version` equals `expected_version`); if not, the Push runs a different Remote Script than the server expects: tell the user. If the tool list in this session lacks `record_into_slot` / `set_clip_envelope`, the session loaded an old list: tell the user a new session will have them, and use the socket fallback in `doctor.md` meanwhile. Then read the set: `get_tracks_overview` (compact) or `get_session_info`.

## Rules that protect the user's work

1. **Saving and opening go through the Push's buttons.** Live's API cannot save or open a set, but `save_set` and `load_set(name)` (server on `main` since 2026-10-29) press Save / the Sets browser on the Push and check the file or Live's log. Both preview first; `confirm=true` acts. Loading closes the open set and interrupts the user: ask first. If the open set has unsaved changes, `load_set` stops by default (`unsaved="ask"`); pass `unsaved="save"` or `"discard"` only with the user's answer. Only say a set is saved when `save_set` returned "Saved: <file> written". `new_set` starts an empty set from the default template (same `unsaved` answer; it has no name until `save_set`). `list_sets` shows the sets, `which_set` the open one. If those tools are missing from this session, the old tool list is loaded: ask the user to save on the Push. **Recovered sets:** after a power cut the Push reopens `<Name> [Autosave].als`, and Save then writes THAT file, not `<Name>.als` (2026-10-29). After saving such a set, copy the autosave file over the real one over SSH, keeping the old real file in the project's Backup/ folder, and tell the user.
2. **Ask before arming a track.** Arming opens the input; with monitoring "in" or "auto" that can feed back through speakers. Arm only when the user said so, and prefer monitoring "off" for level checks and test takes. **Vocals: headphones only.** Live can't silence the speakers and keep the headphones on this Push (both sit after the Main fader), so before monitoring a mic or recording a vocal take, ask the user to switch the speakers off and wait for their confirmation (`recipes/vocal-take.md` step 0).
3. **Preview, then confirm.** Many tools preview with `confirm=false` (the default) and need `confirm=true`. Show the user what the preview says when it deletes, overwrites, or records; small creative writes inside what they asked for can go straight through.
4. **Names guard indices.** Pass `expected_name` (the track's exact current name) where a tool takes it. Indices shift after creating or deleting tracks: re-read before acting.
5. **You cannot hear, but you can measure.** Say what you wrote (pitches, bars, devices) and ask the user how it sounds. For levels, use meters, `listen` or measure the recorded file (`recipes/vocal-take.md`), never guess. `listen` needs a scratch audio track (input Resampling, monitoring off) and records the mix before the Main fader, so it works with Main turned down; pass `quiet=True` when the user is not listening (it drops Main for the take and puts it back), and `source="<track>"` for one part. Ableton's own .aif samples can't be read by ffmpeg: to find a sample's pitch, play it through Simpler and `listen(source=...)`.
6. **Session overrides Arrangement.** After `fire_clip` / `fire_scene`, tracks stop following the Arrangement until `back_to_arrangement` (or the Push's Back to Arrangement). Do it before Arrangement playback or recording.
7. **Placing in the Arrangement overwrites** whatever is already at that spot on that track, like a paste.
8. **Jump the playhead only while playing.** With the transport stopped, `set_arrangement_time` does not hold: Play then starts from bar 1 (2026-10-29: this made every "drums are silent at the Drop" meter check read the organ-only intro). Start playback first, then jump, then measure; and check `current_song_time` before trusting a reading.

## Units and the grid

- Time is in **beats** (quarter notes). A bar = `numerator * 4 / denominator` beats: 4 in 4/4, 3 in 3/4, 3 in 6/8.
- Arrangement beat for bar N (4/4): `(N - 1) * 4`. Bar 5 = beat 16.
- Seconds per bar = `bar_beats * 60 / tempo`. At 90 BPM a 4/4 bar is 2.67 s.
- MIDI: C3 = 60 in Live's naming (so C1 = 36). Drum Rack pads start at 36 (first pad) and go up by one per pad; confirm with `get_drum_pads`.
- Notes: `{"pitch", "start_time", "duration", "velocity", "mute"}`, times in beats from the clip start; a note at or after the clip end is refused.

## Quick reference: which tool for what

| Want | Tools |
|---|---|
| See the set | `get_tracks_overview`, `get_session_info`, `get_track_info`, `get_session_snapshot` |
| Tempo, key | `set_tempo`, `get_song_scale`, `set_song_scale`, `set_time_signature` |
| Tracks | `create_midi_track`, `create_audio_track`, `set_track_name`, `set_color`, `duplicate_track`, `delete_track` (guarded) |
| Find sounds | `search_browser_items` (then `load_instrument_or_effect` with its uri), `load_drum_kit`, `get_browser_items_at_path` |
| Devices | `insert_device` (native, by name), `get_device_parameters`, `set_device_parameter` (`display_value` in Hz/dB/ms/%), `get_drum_pads` |
| MIDI clips | `create_clip`, `add_notes_to_clip`, `replace_clip_notes`, `get_clip_notes`, `quantize_clip`, `set_clip_name`, `set_clip_loop` |
| Play | `fire_clip`, `fire_scene`, `stop_clip`, `stop_all_clips`, `start_playback`, `stop_playback`, `back_to_arrangement` |
| Arrangement | `duplicate_to_arrangement`, `create_arrangement_clip`, `move_arrangement_clip`, `trim_arrangement_clip`, `split_arrangement_clip`, `clear_arrangement_range`, `get_arrangement_clips`, `check_arrangement_sync`, `create_locator` |
| Automation | `set_clip_envelope` (points or shapes), `get_clip_envelope`, `clear_clip_envelope` |
| Mix | `get_mixer`, `set_track_volume` (dB), `set_track_panning`, `set_send`, `set_track_mute/solo`, `get_meters` |
| Hear it | `listen` (whole mix or `source=` one track, `quiet=True` for silent checks, `spectrogram_max_hz`), `analyze_audio_clip` |
| Record | `set_track_routing` (input), `set_track_monitoring`, `set_track_arm`, `record_into_slot`, `start_arrangement_record`, `stop_recording`, `set_transport_options` |
| Piano lights | `recipes/fp10-lights.md`: empty MIDI track, input FP-10, monitoring in, output FP10 Lights Ch. 1 |
| Undo | `undo` / `redo` (preview first; one tool call is normally one undo step) |

## Recipes

Worked sequences with real arguments. Read the one you need:

- `recipes/beat.md` - drums: kit, pad map, a 90 BPM boom bap pattern, fills and variations
- `recipes/bass-and-chords.md` - bassline and chord voicings over a progression, lo-fi keys chain
- `recipes/arrange.md` - Session clips to an Arrangement with sections and locators
- `recipes/automation.md` - filter sweep, volume fades, pan movement
- `recipes/vocal-take.md` - level check, then record into a slot or the Arrangement, then measure the take
- `recipes/fp10-lights.md` - the LED strip over the FP-10: light the keys as the user plays (a lights track routed to FP10 Lights), and hints on channel 2
- `doctor.md` - checks when something does not respond, and the SSH socket fallback
- For a build in the style of a reference, genre profiles, progressions, voicings and changing the key, use the `ableton-track-from-reference` skill
- `devices/at-a-glance.md` - every instrument and effect on this Push in a line or two: modes, key controls, what to use it for. Read it when choosing devices
- `devices/` - what the controls do on Drift, Drum Sampler, Auto Filter, Auto Pan-Tremolo, Auto Shift, Erosion, LFO, Expression Control and MPE Control; read the device's page before shaping its sound (`devices/README.md` says why only these)

## Export an MP3

Live's API can't export. `render_song(confirm=true)` records the Arrangement's mix to a WAV on the Push (quiet, deletes its take clip, prints `File: <path>`). Then on the PC, in the repo: `python tools/push_mp3.py "<that path>" "~/Music/<Song>.mp3"` (needs `pip install lameenc`; on Tiamat there is a venv with it in an old session scratchpad, otherwise make one). It copies the WAV over SSH, cuts the silent tail, fades 1.5 s and writes 320 kbps. Then send the MP3 to the user (SendUserFile). The Push's ffmpeg has no MP3 encoder, so the encoding can't run there.

## Known gaps

Save/open only by pressing the Push's buttons (`save_set`/`load_set`; the API route failed: `Browser.load_item` on a set silently does nothing, `Licensing.save_current_set` is unreachable); no hearing (meters and files only; input meter dB readings are rough); clip automation only on Session clips (copy to the Arrangement afterwards); `create_locator` needs the transport stopped; Drift's voice mode (Mono/Poly...), Legato/Glide behaviour and its mod-source choosers are device properties, not parameters, so the tools can't set them (write a glide or scoop as fast notes, or ask the user to set it on the Push); some devices are not in this Live edition (Vinyl Distortion was missing; Redux + Auto Filter stood in) - search before promising a device.
