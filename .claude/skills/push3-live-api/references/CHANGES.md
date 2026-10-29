# Changes from Live 12.3.6 to 12.4.15

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Added (13)

- `Live.Clip.Clip.root_note`
- `Live.Clip.Clip.scale_intervals`
- `Live.Clip.Clip.scale_mode`
- `Live.Clip.Clip.scale_name`
- `Live.Envelope.Envelope.create_event()`
- `Live.Envelope.Envelope.parameter`
- `Live.Licensing.PythonLicensingBridge.invoke_promotions_callback()`
- `Live.Licensing.PythonLicensingBridge.store_session_identifiers()`
- `Live.PluginDevice.PluginDevice.is_editor_open`
- `Live.SimplerDevice.SimplerDevice.replace_sample()`
- `Live.Song.Song.View.mod_mapping_device`
- `Live.Song.Song.View.mod_mapping_parameter`
- `Live.Song.Song.sync_parameter_changes()`

## Changed (1)

- `Live.WavetableDevice.VoiceCount`: was `enum two=0, three=1, four=2, five=3, six=4, seven=5, eight=6`, now `enum two=0, three=1, four=2, five=3, six=4, seven=5, eight=6, sixteen=7`

## Missing from this capture (1)

Members still inherited from a base class are not counted as missing.

- `Live.Licensing.PythonLicensingBridge.store_session_id()`
