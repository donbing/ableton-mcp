# Live.DrumChain

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## DrumChain.DrumChain

This class represents a drum group device chain in Live.

Base: Chain.Chain, Track.DeviceContainer, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `choke_group` `int`† (rw, listenable): Access to the chain's choke group setting.
- `color` `int`† (rw): Access the color index of the Chain.
- `color_index` `int`† (rw): Access the color index of the Chain.
- `devices` `Base.Vector[RackDevice.RackDevice]`† (r): Return const access to all available Devices that are present in the chains
- `in_note` `int`† (rw, listenable): Access to the incoming MIDI note that will trigger this chain.
- `is_auto_colored` `bool`† (rw): Get/set access to the auto color flag of the Chain. If True, the Chain will always have the same color as the containing Track or Chain.
- `mute` `bool`† (rw): Mute/unmute the chain.
- `muted_via_solo` `bool`† (r): Return const access to whether this chain is muted due to some other chain being soloed.
- `name` `str`† (rw): Read/write access to the name of the Chain, as visible in the track header.
- `out_note` `int`† (rw, listenable): Access to the MIDI note sent to the devices in the chain.
- `solo` `bool`† (rw): Get/Set the solo status of the chain. Note that this will not disable the solo state of any other Chain in the same rack. If you want exclusive solo, you have to disable the solo state of the other Chains manually.
