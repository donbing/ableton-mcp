# Live.Browser

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Browser.Browser

This class represents the live browser data base.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `audio_effects` (r): Returns a browser item with access to all the Audio Effects content.
- `clips` (r): Returns a browser item with access to all the Clips content.
- `colors` (r): Returns a list of browser items containing the configured colors.
- `current_project` (r): Returns a browser item with access to all the Current Project content.
- `drums` (r): Returns a browser item with access to all the Drums content.
- `filter_type` (rw, listenable): Bang triggered when the hotswap target has changed.
- `hotswap_target` (rw, listenable): Bang triggered when the hotswap target has changed.
- `instruments` (r): Returns a browser item with access to all the Instruments content.
- `legacy_libraries` (r): Returns a list of browser items containing the installed legacy libraries. The list is always empty as legacy library handling has been removed.
- `max_for_live` (r): Returns a browser item with access to all the Max For Live content.
- `midi_effects` (r): Returns a browser item with access to all the Midi Effects content.
- `packs` (r): Returns a browser item with access to all the Packs content.
- `plugins` (r): Returns a browser item with access to all the Plugins content.
- `samples` (r): Returns a browser item with access to all the Samples content.
- `sounds` (r): Returns a browser item with access to all the Sounds content.
- `user_folders` (r): Returns a list of browser items containing all the user folders.
- `user_library` (r): Returns a browser item with access to all the User Library content.
- `full_refresh` (r, listenable)

Methods:

- `load_item(arg2: Browser.BrowserItem) -> None`: Loads the provided browser item.
- `preview_item(arg2: Browser.BrowserItem) -> None`: Previews the provided browser item.
- `relation_to_hotswap_target(arg2: Browser.BrowserItem) -> Browser.Relation`: Returns the relation between the given browser item and the current hotswap target
- `stop_preview() -> None`: Stop the current preview.

## Browser.BrowserItem

This class represents an item of the browser hierarchy.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `children` (r): Const access to the descendants of this browser item.
- `is_device` (r): Indicates if the browser item represents a device.
- `is_folder` (r): Indicates if the browser item represents folder.
- `is_loadable` (r): True if item can be loaded via the Browser's 'load_item' method.
- `is_selected` (r): True if the item is ancestor of or the actual selection.
- `iter_children` (r): Const iterable access to the descendants of this browser item.
- `name` (r): Const access to the canonical display name of this browser item.
- `source` (r): Specifies where does item come from -- i.e. Live pack, user library...
- `uri` (r): The uri describes a unique identifier for a browser item.

## Browser.BrowserItemIterator

This class iterates over children of another BrowserItem.

Not constructable from Python.

## Browser.BrowserItemVector

A container for returning browser items from Live.

Not constructable from Python. Iterable.

## Enums

- `FilterType`: disabled=-1, hotswap_off=0, instrument_hotswap=1, audio_effect_hotswap=2, midi_effect_hotswap=3, drum_pad_hotswap=4, midi_track_devices=5, samples=6, count=7
- `Relation`: ancestor=0, equal=1, descendant=2, none=3
