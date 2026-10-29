# Live.DeviceIO

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## DeviceIO.DeviceIO

This class represents a specific input or output bus of a device.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `available_routing_channels` `Track.RoutingChannelVector` (r, listenable): Return a list of channels for this IO endpoint.
- `available_routing_types` `Track.RoutingTypeVector` (r, listenable): Return a list of available routing types for this IO endpoint.
- `canonical_parent` `MaxDevice.MaxDevice` (r): Get the canonical parent of the device IO.
- `default_external_routing_channel_is_none` `bool` (rw): Get and set whether the default routing channel for External routing types is none.
- `routing_channel` `Track.RoutingChannel` (rw, listenable): Get and set the current routing channel. Raises ValueError if the channel isn't one of the current values in available_routing_channels.
- `routing_type` `Track.RoutingType` (rw, listenable): Get and set the current routing type. Raises ValueError if the type isn't one of the current values in available_routing_types.
