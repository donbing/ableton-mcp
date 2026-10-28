# Live.Browser

> Generated from a raw capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-28. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

Types marked † come from the Live 12.3.6 property probe, not this capture.

## Browser.Browser

This class represents the live browser data base.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `audio_effects` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Audio Effects content.
- `clips` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Clips content.
- `colors` `Browser.BrowserItemVector`† (r): Returns a list of browser items containing the configured colors.
- `current_project` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Current Project content.
- `drums` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Drums content.
- `filter_type` `int`† (rw, listenable): Bang triggered when the hotswap target has changed.
- `hotswap_target` (rw, listenable): Bang triggered when the hotswap target has changed.
- `instruments` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Instruments content.
- `legacy_libraries` `Browser.BrowserItemVector`† (r): Returns a list of browser items containing the installed legacy libraries. The list is always empty as legacy library handling has been removed.
- `max_for_live` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Max For Live content.
- `midi_effects` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Midi Effects content.
- `packs` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Packs content.
- `plugins` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Plugins content.
- `samples` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Samples content.
- `sounds` `Browser.BrowserItem`† (r): Returns a browser item with access to all the Sounds content.
- `user_folders` `Browser.BrowserItemVector`† (r): Returns a list of browser items containing all the user folders.
- `user_library` `Browser.BrowserItem`† (r): Returns a browser item with access to all the User Library content.
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

- `children` `Browser.BrowserItemVector`† (r): Const access to the descendants of this browser item.
- `is_device` `bool`† (r): Indicates if the browser item represents a device.
- `is_folder` `bool`† (r): Indicates if the browser item represents folder.
- `is_loadable` `bool`† (r): True if item can be loaded via the Browser's 'load_item' method.
- `is_selected` `bool`† (r): True if the item is ancestor of or the actual selection.
- `iter_children` `Browser.BrowserItemIterator`† (r): Const iterable access to the descendants of this browser item.
- `name` `str`† (r): Const access to the canonical display name of this browser item.
- `source` `str`† (r): Specifies where does item come from -- i.e. Live pack, user library...
- `uri` `str`† (r): The uri describes a unique identifier for a browser item.

## Browser.BrowserItemIterator

This class iterates over children of another BrowserItem.

Not constructable from Python.

## Browser.BrowserItemVector

A container for returning browser items from Live.

Not constructable from Python. Iterable.

## Enums

- `FilterType`: disabled=-1, hotswap_off=0, instrument_hotswap=1, audio_effect_hotswap=2, midi_effect_hotswap=3, drum_pad_hotswap=4, midi_track_devices=5, samples=6, count=7
- `Relation`: ancestor=0, equal=1, descendant=2, none=3
