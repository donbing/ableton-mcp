# Recipe: recording vocals

The user sings; you set up, start and stop takes, and measure them. You cannot hear the take: ask the user, and measure levels.

Setup on this Push (2026-10-26): a wireless mic receiver on **Ext. In 1**. Quiet singing peaked around -38 dBFS, too low; aim for peaks of about -12 to -6 dBFS (raise the transmitter/receiver gain first, a Utility gain on the track last). On 2026-10-29, with the receiver at max and the handheld having no gain control, talking loudly peaked at -32 dBFS (a clean voice in the spectrogram, nothing wrong but level): a Utility at +24 dB (Mono on) as the Vox track's first device brings it to about -8. The file stays at the raw level (24-bit, so that is fine); the Utility only sets what is heard. If the receiver has a mic/line switch, "line" is the fix. Later the same day the user found the mic's preamp setting and put it on "high": about +30 dB, loud singing then peaked at 0.0 dBFS (clipped) with most phrases at -5 to -12. So "high" is a notch too hot for loud singing; with it, no Utility boost is needed. The settings are Line / Inst / High. **Use Inst**: loud singing peaked at -17.5 dBFS (phrases -22 to -33), silence near -76 dBFS, so lots of headroom and a quiet floor; a Utility at about +10 dB makes the headphone level right.

Test before the singer arrives: arm with monitoring OFF, record 8 bars into a Session slot while the user talks loudly (have them reply "go" with the mic in hand, then start at once), measure it with analyze_audio_clip (spectrogram_max_hz=8000 shows whether it is a voice), delete the test clip.

## 0. Headphones only (ask the user to switch the speakers off)

Vocals are recorded with the singer on headphones and the room speakers OFF: with monitoring on, a mic near live speakers feeds back (worse with a gain boost on the track), and even with monitoring off the mic picks the backing up (bleed you can't remove).

Live cannot split the two on this Push (tested 2026-10-29): the headphones carry the same signal as the speakers, AFTER Live's Main fader. Main out to Ext. Out 3/4 silenced both; Main fader at -inf silenced both. The Push's volume knob is Live's Main fader too. So:

- Ask the user to switch the speakers (or their amp) off and to confirm, before turning monitoring on or recording a vocal take. Never pull Main down for this: the singer would hear nothing.
- Keep the Main output on Ext. Out 1/2.
- Afterwards remind them to switch the speakers back on.
- For the singer to hear themselves use monitoring **"in"**: on 2026-10-29 an armed track with "auto" passed nothing to the headphones during Arrangement playback; "in" worked at once. Put it back to "off" when done.

## 1. Prepare the track (ask before arming)

```
create_audio_track(index=-1)
set_track_name(track_index=4, name="Vox")
set_track_routing(track_index=4, expected_name="Vox", direction="input", routing_type="Ext. In", routing_channel="1")
set_track_monitoring(track_index=4, state="off", expected_name="Vox")   # no feedback; user monitors on headphones if needed
set_track_arm(track_index=4, arm=true, expected_name="Vox")             # only after the user agreed
```

## 2. Level check

Timing matters: the user must be singing WHILE you sample. Tell them first, wait for their "go", then:

```
get_meters(seconds=4, hz=20, source="input")   # read the Vox row; dB is rough for inputs
```

For an exact number, record a short test take (step 3) and measure the WAV (step 5).

## 3. Record

Into a Session slot (good for stacking takes):

```
record_into_slot(track_index=4, clip_index=0, expected_name="Vox", length_bars=4)          # preview
record_into_slot(track_index=4, clip_index=0, expected_name="Vox", length_bars=4, confirm=true)
```

Starts at the next launch quantization (default one bar), stops by itself after `length_bars`, then the clip loops. It refuses a slot that already has a clip. Without `length_bars`, end it with `stop_recording`.

Into the Arrangement (a verse at bars 5-13 = beats 16-48):

```
back_to_arrangement()
start_arrangement_record(start_time=16, end_time=48)                 # preview: lists clips it records over
start_arrangement_record(start_time=16, end_time=48, confirm=true)
```

Recording turns off by itself at `end_time` (measured ~15 ms late); playback continues. Give the user a bar or two of pre-roll by starting earlier and trimming later, since count-in through the API is untested.

While a long take runs, don't wait a fixed time: the user may stop early on the Push. Poll `is_playing` (get_tracks_overview or get_meters) every few seconds and move on as soon as it is false or the playhead passes end_time.

## 4. Stop and tidy

```
stop_recording(stop_transport=true)
set_track_arm(track_index=4, arm=false, expected_name="Vox")
set_track_monitoring(track_index=4, state="auto", expected_name="Vox")
```

## 5. Measure the take (exact levels)

Recordings land in the project's `Samples/Recorded/` on the Push (an unsaved set uses `/data/Music/Ableton/Live Recordings/<date> Temp Project/`). Wait a few seconds after the take ends (the file is finalized late), then over SSH (see `doctor.md`) parse the WAV by hand (it has a JUNK chunk before fmt/data; 24-bit mono, 44.1 kHz) and report peak and RMS in dBFS plus a per-second peak list, so silence between phrases is visible.

Suggest Utility gain to the target, or a re-take with more gain if the take is below about -30 dBFS peak (noise floor was about -82 dBFS).
