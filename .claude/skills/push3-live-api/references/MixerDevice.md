# Live.MixerDevice

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## MixerDevice.MixerDevice

This class represents a Mixer Device in Live, which gives you access to the Volume and Panning properties of a Track.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Track.Track`† (r): Get the canonical parent of the mixer device.
- `crossfade_assign` `int`† (rw, listenable): Player- and ReturnTracks only: Access to the Track's Crossfade Assign State.
- `crossfader` `DeviceParameter.DeviceParameter`† (r): MainTrack only: Const access to the Crossfader.
- `cue_volume` `DeviceParameter.DeviceParameter`† (r): MainTrack only: Const access to the Cue Volume Parameter.
- `left_split_stereo` `DeviceParameter.DeviceParameter`† (r): Const access to the Track's Left Split Stereo Panning Device Parameter.
- `panning` `DeviceParameter.DeviceParameter`† (r): Const access to the Tracks Panning Device Parameter.
- `panning_mode` `int`† (rw, listenable): Access to the Track's Panning Mode.
- `right_split_stereo` `DeviceParameter.DeviceParameter`† (r): Const access to the Track's Right Split Stereo Panning Device Parameter.
- `sends` `Base.Vector[DeviceParameter.DeviceParameter]`† (r, listenable): Const access to the Tracks list of Send Amount Device Parameters.
- `song_tempo` `DeviceParameter.DeviceParameter`† (r): MainTrack only: Const access to the Song's Tempo.
- `track_activator` `DeviceParameter.DeviceParameter`† (r): Const access to the Tracks Activator Device Parameter.
- `volume` `DeviceParameter.DeviceParameter`† (r): Const access to the Tracks Volume Device Parameter.

## Enums

- `crossfade_assignments`: A=0, NONE=1, B=2
- `panning_modes`: stereo=0, stereo_split=1
