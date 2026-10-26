# Live.LooperDevice

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## LooperDevice.LooperDevice

This class represents a Looper device.

Base: Device.Device, LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `is_active` `bool`† (r): Return const access to whether this device is active. This will be false bothwhen the device is off and when it's inside a rack device which is off.
- `is_using_compare_preset_b` `bool`† (rw): Returns whether the Device has loaded the preset in compare slot B. Only relevant if can_compare_ab, otherwise errors.
- `latency_in_ms` `float`† (r): Returns the latency of the device in ms.
- `latency_in_samples` `int`† (r): Returns the latency of the device in samples.
- `loop_length` `float`† (r, listenable): The length of Looper's buffer.
- `name` `str`† (rw): Return access to the name of the device.
- `overdub_after_record` `bool`† (rw, listenable): If true, Looper will switch to overdub after recording, when recording a fixed number of bars. Otherwise, the switch will be to playback without overdubbing.
- `parameters` `Device.ATimeableValueVector`† (r): Const access to the list of available automatable parameters for this device.
- `record_length_index` `int`† (rw, listenable): Access to the Record Length chooser entry index.
- `record_length_list` `Base.StringVector`† (r): Read-only access to the list of Record Length chooser entry strings.
- `tempo` `float`† (r, listenable): The tempo of Looper's buffer.

Methods:

- `clear() -> None`: Erase Looper's recorded content.
- `double_length() -> None`: Double the length of Looper's buffer.
- `double_speed() -> None`: Double the speed of Looper's playback.
- `export_to_clip_slot(arg2: ClipSlot.ClipSlot) -> None`: Export Looper's content to a Session Clip Slot.
- `half_length() -> None`: Halve the length of Looper's buffer.
- `half_speed() -> None`: Halve the speed of Looper's playback.
- `overdub() -> None`: Play back while adding additional layers of incoming audio.
- `play() -> None`: Play back without overdubbing.
- `record() -> None`: Record incoming audio.
- `stop() -> None`: Stop Looper's playback.
- `undo() -> None`: Erase everything that was recorded since the last time Overdub was enabled. Calling a second time will restore the material erased by the previous undooperation.
