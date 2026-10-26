# Live.MixerDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## MixerDevice.MixerDevice

This class represents a Mixer Device in Live, which gives you access to the Volume and Panning properties of a Track.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` (r): Get the canonical parent of the mixer device.
- `crossfade_assign` (rw, listenable): Player- and ReturnTracks only: Access to the Track's Crossfade Assign State.
- `crossfader` (r): MainTrack only: Const access to the Crossfader.
- `cue_volume` (r): MainTrack only: Const access to the Cue Volume Parameter.
- `left_split_stereo` (r): Const access to the Track's Left Split Stereo Panning Device Parameter.
- `panning` (r): Const access to the Tracks Panning Device Parameter.
- `panning_mode` (rw, listenable): Access to the Track's Panning Mode.
- `right_split_stereo` (r): Const access to the Track's Right Split Stereo Panning Device Parameter.
- `sends` (r, listenable): Const access to the Tracks list of Send Amount Device Parameters.
- `song_tempo` (r): MainTrack only: Const access to the Song's Tempo.
- `track_activator` (r): Const access to the Tracks Activator Device Parameter.
- `volume` (r): Const access to the Tracks Volume Device Parameter.

## Enums

- `crossfade_assignments`: A=0, NONE=1, B=2
- `panning_modes`: stereo=0, stereo_split=1
