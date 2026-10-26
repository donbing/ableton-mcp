# Changes from Live 12.3.6 to 12.4.6

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Added (12)

- `Live.Envelope.Envelope.create_event()`
- `Live.Envelope.Envelope.parameter`
- `Live.Licensing.PythonLicensingBridge.invoke_promotions_callback()`
- `Live.Licensing.PythonLicensingBridge.store_session_identifiers()`
- `Live.MaxDevice.MaxDevice.is_using_compare_preset_b`
- `Live.PluginDevice.PluginDevice.is_editor_open`
- `Live.PluginDevice.PluginDevice.is_using_compare_preset_b`
- `Live.RackDevice.RackDevice.is_using_compare_preset_b`
- `Live.SimplerDevice.SimplerDevice.replace_sample()`
- `Live.Song.Song.View.mod_mapping_device`
- `Live.Song.Song.View.mod_mapping_parameter`
- `Live.Song.Song.sync_parameter_changes()`

## Changed (1)

- `Live.WavetableDevice.VoiceCount`: was `enum two=0, three=1, four=2, five=3, six=4, seven=5, eight=6`, now `enum two=0, three=1, four=2, five=3, six=4, seven=5, eight=6, sixteen=7`

## Missing from this capture (13)

A raw capture skips the property probe, so some of these are gaps in the capture rather than API
removals. Treat each one as unverified until a full probe confirms it.

- `Live.Base.Timer.__init__()`
- `Live.Clip.MidiNoteSpecification.__init__()`
- `Live.Clip.WarpMarker.__init__()`
- `Live.Envelope.EnvelopeEvent.__init__()`
- `Live.Eq8Device.Eq8Device.View.canonical_parent`
- `Live.Eq8Device.Eq8Device.view`
- `Live.Licensing.PythonLicensingBridge.store_session_id()`
- `Live.RackDevice.RackDevice.View.canonical_parent`
- `Live.RackDevice.RackDevice.view`
- `Live.SimplerDevice.SimplerDevice.View.canonical_parent`
- `Live.SimplerDevice.SimplerDevice.view`
- `Live.TuningSystem.PitchClassAndOctave.__init__()`
- `Live.TuningSystem.ReferencePitch.__init__()`
