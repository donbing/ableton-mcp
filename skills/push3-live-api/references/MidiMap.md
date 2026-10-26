# Live.MidiMap

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## MidiMap.CCFeedbackRule

Structure to define feedback properties of MIDI mappings.

Properties (r = read-only, rw = settable):

- `cc_no` (rw)
- `cc_value_map` (rw)
- `channel` (rw)
- `delay_in_ms` (rw)
- `enabled` (rw)

Methods:

- `__init__() -> None`

## MidiMap.NoteFeedbackRule

Structure to define feedback properties of MIDI mappings.

Properties (r = read-only, rw = settable):

- `channel` (rw)
- `delay_in_ms` (rw)
- `enabled` (rw)
- `note_no` (rw)
- `vel_map` (rw)

Methods:

- `__init__() -> None`

## MidiMap.PitchBendFeedbackRule

Structure to define feedback properties of MIDI mappings.

Properties (r = read-only, rw = settable):

- `channel` (rw)
- `delay_in_ms` (rw)
- `enabled` (rw)
- `value_pair_map` (rw)

Methods:

- `__init__() -> None`

## Functions

- `forward_midi_cc(arg1: int, arg2: int, arg3: int, arg4: int, should_consume_event: bool) -> bool`
- `forward_midi_note(arg1: int, arg2: int, arg3: int, arg4: int, should_consume_event: bool) -> bool`
- `forward_midi_pitchbend(arg1: int, arg2: int, arg3: int) -> bool`
- `map_midi_cc(midi_map_handle: int, parameter: DeviceParameter.DeviceParameter, midi_channel: int, controller_number: int, map_mode: MidiMap.MapMode | int, avoid_takeover: bool, sensitivity: float) -> bool`
- `map_midi_cc_with_feedback_map(midi_map_handle: int, parameter: DeviceParameter.DeviceParameter, midi_channel: int, controller_number: int, map_mode: MidiMap.MapMode | int, feedback_rule: MidiMap.CCFeedbackRule, avoid_takeover: bool, sensitivity: float) -> bool`
- `map_midi_note(arg1: int, arg2: DeviceParameter.DeviceParameter, arg3: int, arg4: int) -> bool`
- `map_midi_note_with_feedback_map(arg1: int, arg2: DeviceParameter.DeviceParameter, arg3: int, arg4: int, arg5: MidiMap.NoteFeedbackRule) -> bool`
- `map_midi_pitchbend(arg1: int, arg2: DeviceParameter.DeviceParameter, arg3: int, arg4: bool) -> bool`
- `map_midi_pitchbend_with_feedback_map(arg1: int, arg2: DeviceParameter.DeviceParameter, arg3: int, arg4: MidiMap.PitchBendFeedbackRule, arg5: bool) -> bool`
- `send_feedback_for_parameter(arg1: int, arg2: DeviceParameter.DeviceParameter) -> None`

## Enums

- `MapMode`: absolute=0, relative_signed_bit=1, relative_binary_offset=2, relative_two_compliment=3, relative_signed_bit2=4, absolute_14_bit=5, relative_smooth_signed_bit=6, relative_smooth_binary_offset=7, relative_smooth_two_compliment=8, relative_smooth_signed_bit2=9
