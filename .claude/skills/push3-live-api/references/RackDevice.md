# Live.RackDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## RackDevice.RackDevice

This class represents a Rack device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `can_show_chains` (r): return True, if this Rack contains a rack instrument device that is capable of showing its chains in session view.
- `chain_selector` (r): Const access to the chain selector parameter.
- `chains` (r, listenable): Return const access to the list of chains in this device. Throws an exception if can_have_chains is false.
- `drum_pads` (r, listenable): Return const access to the list of drum pads in this device. Throws an exception if can_have_drum_pads is false.
- `has_drum_pads` (r, listenable): Returns true if the device is a drum rack which has drum pads. Throws an exception if can_have_drum_pads is false.
- `has_macro_mappings` (r, listenable): Returns true if any of the rack's macros are mapped to a parameter.
- `is_active` (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_showing_chains` (rw, listenable): Returns True, if it is showing chains.
- `is_using_compare_preset_b` (rw) *(new)*: Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` (r): Returns the latency of the device in ms.
- `latency_in_samples` (r): Returns the latency of the device in samples.
- `macros_mapped` (r, listenable): A list of booleans, one for each macro parameter, which is True iffthat macro is mapped to something
- `name` (rw): Return access to the name of the device.
- `parameters` (r): Const access to the list of available automatable parameters for this device.
- `return_chains` (r, listenable): Return const access to the list of return chains in this device. Throws an exception if can_have_chains is false.
- `selected_variation_index` (rw): Access to the index of the currently selected macro variation.Throws an exception if the index is out of range.
- `variation_count` (r, listenable): Access to the number of macro variations currently stored.
- `visible_drum_pads` (r, listenable): Return const access to the list of visible drum pads in this device. Throws an exception if can_have_drum_pads is false.
- `visible_macro_count` (r, listenable): Access to the number of macros that are currently visible.

Methods:

- `add_macro() -> None`: Increases the number of visible macro controls in the rack. Throws an exception if the maximum number of macro controls is reached.
- `copy_pad(arg2: int, arg3: int) -> None`: Copies all contents of a drum pad from a source pad into a destination pad. copy_pad(source_index, destination_index) where source_index and destination_index correspond to the note number/index of the drum pad in a drum rack. Throws an exception when the source pad is empty, or when the source or destination indices are not between 0 - 127.
- `delete_selected_variation() -> None`: Deletes the currently selected macro variation.Does nothing if there is no selected variation.
- `insert_chain(index: int) -> LomObject.LomObject`: Inserts a new chain, either at the specified index or, if not index was specified, at the end of the chain sequence.
- `randomize_macros() -> None`: Randomizes the values for all macro controls not excluded from randomization.
- `recall_last_used_variation() -> None`: Recalls the macro variation that was recalled most recently.Does nothing if no variation has been recalled yet.
- `recall_selected_variation() -> None`: Recalls the currently selected macro variation.Does nothing if there are no variations.
- `remove_macro() -> None`: Decreases the number of visible macro controls in the rack. Throws an exception if the minimum number of macro controls is reached.
- `store_variation() -> None`: Stores a new variation of the values of all currently mapped macros

## RackDevice.RackDevice.View

Representing the view aspects of a rack device.

Base: Device.Device.View, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `drum_pads_scroll_position` (rw, listenable): Access to the index of the lowest visible row of pads. Throws an exception if can_have_drum_pads is false.
- `is_collapsed` (rw): Get/Set/Listen if the device is shown collapsed in the device chain.
- `is_showing_chain_devices` (rw, listenable): Return whether the devices in the currently selected chain are visible. Throws an exception if can_have_chains is false.
- `selected_chain` (rw, listenable): Return access to the currently selected chain.
- `selected_drum_pad` (rw, listenable): Return access to the currently selected drum pad. Throws an exception if can_have_drum_pads is false.
