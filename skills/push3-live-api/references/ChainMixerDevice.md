# Live.ChainMixerDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## ChainMixerDevice.ChainMixerDevice

This class represents a Chain's Mixer Device in Live, which gives you access to the Volume, Panning, and Send properties of a Chain.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` (r): Get the canonical parent of the mixer device.
- `chain_activator` (r): Const access to the Chain's Activator Device Parameter.
- `panning` (r): Const access to the Chain's Panning Device Parameter.
- `sends` (r, listenable): Const access to the Chain's list of Send Amount Device Parameters.
- `volume` (r): Const access to the Chain's Volume Device Parameter.
