# Live.Chain

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Chain.Chain

This class represents a group device chain in Live.

Base: Track.DeviceContainer, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `RackDevice.RackDevice` (r): Get the canonical parent of the chain.
- `color` `int` (rw, listenable): Access the color index of the Chain.
- `color_index` `int` (rw, listenable): Access the color index of the Chain.
- `devices` `Base.Vector[RackDevice.RackDevice]` (r, listenable): Return const access to all available Devices that are present in the chains
- `has_audio_input` `bool` (r): return True, if this Chain can be feed with an Audio signal. This is true for all Audio Chains.
- `has_audio_output` `bool` (r): return True, if this Chain sends out an Audio signal. This is true for all Audio Chains, and MIDI chains with an Instrument.
- `has_midi_input` `bool` (r): return True, if this Chain can be feed with an Audio signal. This is true for all MIDI Chains.
- `has_midi_output` `bool` (r): return True, if this Chain sends out MIDI events. This is true for all MIDI Chains with no Instruments.
- `is_auto_colored` `bool` (rw, listenable): Get/set access to the auto color flag of the Chain. If True, the Chain will always have the same color as the containing Track or Chain.
- `mixer_device` `ChainMixerDevice.ChainMixerDevice` (r): Return access to the mixer device that holds the chain's mixer parameters: the Volume, Pan, and Sendamounts.
- `mute` `bool` (rw, listenable): Mute/unmute the chain.
- `muted_via_solo` `bool` (r, listenable): Return const access to whether this chain is muted due to some other chain being soloed.
- `name` `str` (rw, listenable): Read/write access to the name of the Chain, as visible in the track header.
- `solo` `bool` (rw, listenable): Get/Set the solo status of the chain. Note that this will not disable the solo state of any other Chain in the same rack. If you want exclusive solo, you have to disable the solo state of the other Chains manually.

Methods:

- `delete_device(arg2: int) -> None`: Remove a device identified by its index from the chain. Throws runtime error if bad index.
- `duplicate_device(arg2: int) -> None`: Duplicate the device at the given index in the chain.
- `insert_device(device_name: str, device_index: int) -> LomObject.LomObject`: Add a device at a given index in the chain. At end if -1.
