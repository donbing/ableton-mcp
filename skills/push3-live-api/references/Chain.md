# Live.Chain

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Chain.Chain

This class represents a group device chain in Live.

Base: Track.DeviceContainer, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` (r): Get the canonical parent of the chain.
- `color` (rw, listenable): Access the color index of the Chain.
- `color_index` (rw, listenable): Access the color index of the Chain.
- `devices` (r, listenable): Return const access to all available Devices that are present in the chains
- `has_audio_input` (r): return True, if this Chain can be feed with an Audio signal. This is true for all Audio Chains.
- `has_audio_output` (r): return True, if this Chain sends out an Audio signal. This is true for all Audio Chains, and MIDI chains with an Instrument.
- `has_midi_input` (r): return True, if this Chain can be feed with an Audio signal. This is true for all MIDI Chains.
- `has_midi_output` (r): return True, if this Chain sends out MIDI events. This is true for all MIDI Chains with no Instruments.
- `is_auto_colored` (rw, listenable): Get/set access to the auto color flag of the Chain. If True, the Chain will always have the same color as the containing Track or Chain.
- `mixer_device` (r): Return access to the mixer device that holds the chain's mixer parameters: the Volume, Pan, and Sendamounts.
- `mute` (rw, listenable): Mute/unmute the chain.
- `muted_via_solo` (r, listenable): Return const access to whether this chain is muted due to some other chain being soloed.
- `name` (rw, listenable): Read/write access to the name of the Chain, as visible in the track header.
- `solo` (rw, listenable): Get/Set the solo status of the chain. Note that this will not disable the solo state of any other Chain in the same rack. If you want exclusive solo, you have to disable the solo state of the other Chains manually.

Methods:

- `delete_device(arg2: int) -> None`: Remove a device identified by its index from the chain. Throws runtime error if bad index.
- `duplicate_device(arg2: int) -> None`: Duplicate the device at the given index in the chain.
- `insert_device(device_name: str, device_index: int) -> LomObject.LomObject`: Add a device at a given index in the chain. At end if -1.
