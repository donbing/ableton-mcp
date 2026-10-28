# Live.Track

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Track.Track

This class represents a track in Live. It can be either an Audio track, a MIDI Track, a Return Track or the Main track. The Main Track and at least one Audio or MIDI track will be always present. Return Tracks are optional.

Base: Track.DeviceContainer, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `arm` `bool`† (rw, listenable): Arm the track for recording. Not available for Main- and Send Tracks.
- `arrangement_clips` `Base.Vector[Clip.Clip]`† (r, listenable): const access to the list of clips in arrangement viewThe list will be empty for the main, send and group tracks.
- `available_input_routing_channels` `Track.RoutingChannelVector`† (r, listenable): Return a list of source channels for input routing.
- `available_input_routing_types` `Track.RoutingTypeVector`† (r, listenable): Return a list of source types for input routing.
- `available_output_routing_channels` `Track.RoutingChannelVector`† (r, listenable): Return a list of destination channels for output routing.
- `available_output_routing_types` `Track.RoutingTypeVector`† (r, listenable): Return a list of destination types for output routing.
- `back_to_arranger` `bool`† (rw, listenable): Indicates if it's possible to go back to playing back the clips in the Arranger.Setting a value 0 will go back to the Arranger playback. Setting on grouptracks will go back to the Arranger on all grouped tracks.
- `can_be_armed` `bool`† (r): return True, if this Track has a valid arm property. Not all tracks can be armed (for example return Tracks or the Main Tracks).
- `can_be_frozen` `bool`† (r): return True, if this Track can be frozen.
- `can_show_chains` `bool`† (r): return True, if this Track contains a rack instrument device that is capable of showing its chains in session view.
- `canonical_parent` `Song.Song`† (r): Get the canonical parent of the track.
- `clip_slots` `Base.Vector[ClipSlot.ClipSlot]`† (r, listenable): const access to the list of clipslots (see class AClipSlot) for this track. The list will be empty for the main and sendtracks.
- `color` `int`† (rw, listenable): Get/set access to the color of the Track (RGB).
- `color_index` `int`† (rw, listenable): Get/Set access to the color index of the track. Can be None for no color.
- `current_input_routing` `str`† (rw, listenable): Get/Set the name of the current active input routing. When setting a new routing, the new routing must be one of the available ones.
- `current_input_sub_routing` `str`† (rw, listenable): Get/Set the current active input sub routing. When setting a new routing, the new routing must be one of the available ones.
- `current_monitoring_state` `int`† (rw, listenable): Get/Set the track's current monitoring state.
- `current_output_routing` `str`† (rw, listenable): Get/Set the current active output routing. When setting a new routing, the new routing must be one of the available ones.
- `current_output_sub_routing` `str`† (rw, listenable): Get/Set the current active output sub routing. When setting a new routing, the new routing must be one of the available ones.
- `devices` `Base.Vector[Device.Device]`† (r, listenable): Return const access to all available Devices that are present in the Tracks Devicechain. This tuple will also include the 'mixer_device' that every Track always has.
- `fired_slot_index` `int`† (r, listenable): const access to the index of the fired (and thus blinking) clipslot in this track. This index is -1 if no slot is fired and -2 if the track's stop button has been fired.
- `fold_state` `bool`† (rw): Get/Set whether the track is folded or not. Only available if is_foldable is True.
- `group_track` `Track.Track`† (r): return the group track if is_grouped.
- `has_audio_input` `bool`† (r, listenable): return True, if this Track can be feed with an Audio signal. This is true for all Audio Tracks.
- `has_audio_output` `bool`† (r, listenable): return True, if this Track sends out an Audio signal. This is true for all Audio Tracks, and MIDI tracks with an Instrument.
- `has_midi_input` `bool`† (r, listenable): return True, if this Track can be feed with an Audio signal. This is true for all MIDI Tracks.
- `has_midi_output` `bool`† (r, listenable): return True, if this Track sends out MIDI events. This is true for all MIDI Tracks with no Instruments.
- `implicit_arm` `bool`† (rw, listenable): Arm the track for recording. When The track is implicitly armed, it showsin a weaker color in the live GUI and is not saved in the set.
- `input_meter_left` `float`† (r, listenable): Momentary value of left input channel meter, 0.0 to 1.0. For Audio Tracks only.
- `input_meter_level` `float`† (r, listenable): Return the MIDI or Audio meter value of the Tracks input, depending on the type of the Track input. Meter values (MIDI or Audio) are always scaled from 0.0 to 1.0.
- `input_meter_right` `float`† (r, listenable): Momentary value of right input channel meter, 0.0 to 1.0. For Audio Tracks only.
- `input_routing_channel` `Track.RoutingChannel`† (rw, listenable): Get and set the current source channel for input routing. Raises ValueError if the type isn't one of the current values in available_input_routing_channels.
- `input_routing_type` `Track.RoutingType`† (rw, listenable): Get and set the current source type for input routing. Raises ValueError if the type isn't one of the current values in available_input_routing_types.
- `input_routings` `Base.StringVector`† (r, listenable): Const access to the list of available input routings.
- `input_sub_routings` `Base.StringVector`† (r, listenable): Return a list of all available input sub routings.
- `is_foldable` `bool`† (r): return True if the track can be (un)folded to hide/reveal contained tracks.
- `is_frozen` `bool`† (r, listenable): return True if this Track is currently frozen. No changes should be applied to the track's devices or clips while it is frozen.
- `is_grouped` `bool`† (r): return True if this Track is current part of a group track.
- `is_part_of_selection` `bool`† (r): return False if the track is not selected.
- `is_showing_chains` `bool`† (rw, listenable): Get/Set whether a track with a rack device is showing its chains in session view.
- `is_visible` `bool`† (r): return False if the track is hidden within a folded group track.
- `mixer_device` `MixerDevice.MixerDevice`† (r): Return access to the special Device that every Track has: This Device contains the Volume, Pan, Sendamounts, and Crossfade assignment parameters.
- `mute` `bool`† (rw, listenable): Mute/unmute the track.
- `muted_via_solo` `bool`† (r, listenable): Returns true if the track is muted because another track is soloed.
- `name` `str`† (rw, listenable): Read/write access to the name of the Track, as visible in the track header.
- `output_meter_left` `float`† (r, listenable): Momentary value of left output channel meter, 0.0 to 1.0. For tracks with audio output only.
- `output_meter_level` `float`† (r, listenable): Return the MIDI or Audio meter value of the Track output (behind the mixer_device), depending on the type of the Track input, this can be a MIDI or Audio meter. Meter values (MIDI or Audio) are always scaled from 0.0 to 1.0.
- `output_meter_right` `float`† (r, listenable): Momentary value of right output channel meter, 0.0 to 1.0. For tracks with audio output only.
- `output_routing_channel` `Track.RoutingChannel`† (rw, listenable): Get and set the current destination channel for output routing. Raises ValueError if the channel isn't one of the current values in available_output_routing_channels.
- `output_routing_type` `Track.RoutingType`† (rw, listenable): Get and set the current destination type for output routing. Raises ValueError if the type isn't one of the current values in available_output_routing_types.
- `output_routings` `Base.StringVector`† (r, listenable): Const access to the list of all available output routings.
- `output_sub_routings` `Base.StringVector`† (r, listenable): Return a list of all available output sub routings.
- `performance_impact` `float`† (r, listenable): Reports the performance impact of this track.
- `playing_slot_index` `int`† (r, listenable): const access to the index of the currently playing clip in the track. Will be -1 when no clip is playing.
- `solo` `bool`† (rw, listenable): Get/Set the solo status of the track. Note that this will not disable the solo state of any other track. If you want exclusive solo, you have to disable the solo state of the other Tracks manually.
- `take_lanes` `Base.Vector[TakeLane.TakeLane]`† (r, listenable): returns the take lanes.
- `view` `Track.Track.View`† (r): Representing the view aspects of a Track.
- `data` (r, listenable)

Methods:

- `create_audio_clip(arg2: str, arg3: float) -> Clip.Clip`: Creates an audio clip referencing the file at the given path and inserts it into the arrangement at the specified time. Throws an error when called on a non-audio or a frozen track, when the specified time is outside the [0., 1576800.] range, when the track is currently being recorded into, or when the path doesn't point to a valid audio file.
- `create_midi_clip(arg2: float, arg3: float) -> Clip.Clip`: Creates an empty MIDI clip and inserts it into the arrangement at the specified time. Throws an error when called on a non-MIDI track or a frozen track, when the specified time is outside the [0., 1576800.] range, or when the track is currently being recorded into.
- `create_take_lane() -> LomObject.LomObject`: Create a new TakeLane for this track.
- `delete_clip(arg2: Clip.Clip) -> None`: Delete the given clip. Raises a runtime error when the clip belongs to another track.
- `delete_device(arg2: int) -> None`: Delete a device identified by the index in the 'devices' list.
- `duplicate_clip_slot(arg2: int) -> int`: Duplicate a clip and put it into the next free slot and return the index of the destination slot. A new scene is created if no free slot is available. If creating the new scene would exceed the limitations, a runtime error is raised.
- `duplicate_clip_to_arrangement(clip: Clip.Clip, destination_time: float) -> Clip.Clip`: Duplicate the given clip into the arrangement of this track at the provided destination time and return it. When the type of the clip and the type of the track are incompatible, a runtime error is raised.
- `duplicate_device(arg2: int) -> None`: Duplicate a device at a given index in the 'devices' list.
- `get_data(key: str, default_value: object) -> object`: Get data for the given key, that was previously stored using set_data.
- `insert_device(device_name: str, device_index: int) -> LomObject.LomObject`: Add a device at a given index in the 'devices' list. At end if -1.
- `jump_in_running_session_clip(arg2: float) -> None`: Jump forward or backward in the currently running Sessionclip (if any) by the specified relative amount in beats. Does nothing if no Session Clip is currently running.
- `set_data(key: str, value: object) -> None`: Store data for the given key in this object. The data is persistent and will be restored when loading the Live Set.
- `stop_all_clips(quantized: bool) -> None`: Stop running and triggered clip and slots on this track.

## Track.DeviceContainer

This class is a common super class of Track and Chain

Base: LomObject.LomObject. Not constructable from Python.

## Track.RoutingChannel

This class represents a routing channel.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `display_name` `str`† (r): Display name of routing channel.
- `layout` `Track.RoutingChannelLayout`† (r): The routing channel's Layout, e.g., mono or stereo.

## Track.RoutingChannelVector

A container for returning routing channels from Live.

Not constructable from Python. Iterable.

## Track.RoutingType

This class represents a routing type.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `attached_object` `Track.Track`† (r): Live object associated with the routing type.
- `category` `int`† (r): Category of the routing type.
- `display_name` `str`† (r): Display name of routing type.

## Track.RoutingTypeVector

A container for returning routing types from Live.

Not constructable from Python. Iterable.

## Track.Track.View

Representing the view aspects of a Track.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `canonical_parent` `Track.Track`† (r): Get the canonical parent of the track view.
- `device_insert_mode` `bool`† (rw, listenable): Get/Listen the device insertion mode of the track. By default, it will insert devices at the end, but it can be changed to make it relative to current selection.
- `is_collapsed` `bool`† (rw, listenable): Get/Set/Listen if the track is shown collapsed in the arranger view.
- `selected_device` `Device.Device`† (r, listenable): Get/Set/Listen the insertion mode of the device. While in insertion mode, loading new devices from the browser will place devices at the selected position.

Methods:

- `select_instrument() -> bool`: Selects the track's instrument if it has one.

## Enums

- `DeviceInsertMode`: default=0, selected_left=1, selected_right=2, count=3
- `RoutingChannelLayout`: mono=1, stereo=2, midi=0
- `RoutingTypeCategory`: external=0, rewire=1, resampling=2, master=3, track=4, parent_group_track=5, none=6, invalid=7
- `monitoring_states`: IN=0, AUTO=1, OFF=2
