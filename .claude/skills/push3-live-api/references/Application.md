# Live.Application

> Generated from a probe capture: Live 12.4.15, Intro, Push 3 standalone, AbletonOS x86_64 v3.23, Python 3.11.6, captured 2026-10-29. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Application.Application

This class represents the Live application.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `average_process_usage` `float` (r, listenable): Reports Live's average CPU load.
- `browser` `Browser.Browser` (r): Returns an interface to the browser.
- `canonical_parent` `None` (r): Returns the canonical parent of the application.
- `control_surfaces` `Base.Vector[object]` (r, listenable): Const access to a list of the control surfaces selected in preferences, in the same order. The list contains None if no control surface is active at that index.
- `current_dialog_button_count` `int` (r): Number of buttons on the current dialog.
- `current_dialog_message` `str` (r): Text of the last dialog that appeared; Empty if all dialogs just disappeared.
- `number_of_push_apps_running` `int` (r): Returns the number of connected Push apps.
- `open_dialog_count` `int` (r, listenable): The number of open dialogs in Live. 0 if not dialog is open.
- `peak_process_usage` `float` (r, listenable): Reports Live's peak CPU load.
- `unavailable_features` `Application.UnavailableFeatureVector` (r, listenable): List of features that are unavailable due to limitations of the current Live edition.
- `view` `Application.Application.View` (r): Returns the applications view component.

Methods:

- `get_bugfix_version() -> int`: Returns an integer representing the bugfix version of Live.
- `get_build_id() -> str`: Returns a string identifying the build.
- `get_document() -> Song.Song`: Returns the current Live Set.
- `get_major_version() -> int`: Returns an integer representing the major version of Live.
- `get_minor_version() -> int`: Returns an integer representing the minor version of Live.
- `get_variant() -> str`: Returns one of the strings in Live.Application.Variants.
- `get_version_string() -> str`: Returns the full version string of Live.
- `has_option(arg2: str) -> bool`: Returns True if the given entry exists in Options.txt, False otherwise.
- `press_current_dialog_button(arg2: int) -> None`: Press a button, by index, on the current message box.
- `show_message(text: Base.Text, buttons: Application.MessageButtons | int, enable_markup: bool, show_success_icon: bool) -> int`: Shows a message box, returning the position of the pressed button.
- `show_on_the_fly_message(message: str, buttons: Application.MessageButtons | int, enable_markup: bool, show_success_icon: bool, push_dialog_type: Application.PushDialogType | int) -> int`: Same as show_message, but for when there is no predefined Text object.

## Application.ControlDescription

Describes a control present in a control surface proxy

Properties (r = read-only, rw = settable):

- `id` `int` (r)
- `name` `str` (r)

Methods:

- `__init__() -> None`

## Application.ControlDescriptionVector

A container for returning control descriptions.

Not constructable from Python. Iterable.

## Application.ControlSurfaceProxy

Represents a control surface running in a different process. For use by M4L

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `control_descriptions` `Application.ControlDescriptionVector` (r)
- `pad_layout` `str` (r, listenable): The layout of pads on Push.
- `type_name` `str` (r)
- `control_values_arrived` (r, listenable)
- `midi_received` (r, listenable)

Methods:

- `enable_receive_midi(arg2: bool) -> None`
- `fetch_received_midi_messages() -> tuple`
- `fetch_received_values() -> tuple`
- `grab_control(arg2: int) -> None`
- `release_control(arg2: int) -> None`
- `send_midi(arg2: tuple) -> None`
- `send_value(arg2: tuple) -> None`
- `subscribe_to_control(arg2: int) -> None`
- `unsubscribe_from_control(arg2: int) -> None`

## Application.UnavailableFeatureVector

A container for returning unavailable features.

Not constructable from Python. Iterable.

## Application.Variants

Holds strings representing what type of Live is running.

Not constructable from Python.

## Application.Application.View

This class represents the view aspects of the Live application.

Base: LomObject.LomObject. Not constructable from Python.

Properties (r = read-only, rw = settable):

- `browse_mode` `bool` (r, listenable): Return true if HotSwap mode is active for any target.
- `canonical_parent` `Application.Application` (r): Get the canonical parent of the application view.
- `focused_document_view` `str` (r, listenable): Return the name of the document view ('Session' or 'Arranger') shown in the currently selected window.
- `view_focus_changed` (r, listenable)

Methods:

- `add_is_view_visible_listener(arg2: str, callback: Callable[[], None]) -> None`: Add a listener function or method, which will be called as soon as the property "is_view_visible" has changed.
- `available_main_views() -> Base.StringVector`: Return a list of strings with the available subcomponent views, which is to be specified, when using the rest of this classes functions. A 'subcomponent view' is a main view component of a document view, like the Session view, the Arranger or Detailview and so on...
- `focus_view(arg2: str) -> None`: Show and focus one through the identifier string specified view.
- `hide_view(arg2: str) -> None`: Hide one through the identifier string specified view.
- `is_view_visible(identifier: str, main_window_only: bool) -> bool`: Return true if the through the identifier string specified view is currently visible. If main_window_only is set to False, this will also check in second window. Notifications from the second window are not yet supported.
- `is_view_visible_has_listener(arg2: str, callback: Callable[[], None]) -> bool`: Returns true, if the given listener function or method is connected to the property "is_view_visible".
- `remove_is_view_visible_listener(arg2: str, callback: Callable[[], None]) -> None`: Remove a previously set listener function or method from property "is_view_visible".
- `scroll_view(arg2: int, arg3: str, arg4: bool) -> None`: Scroll through the identifier string specified view into the given direction, if possible. Will silently return if the specified view can not perform the requested action.
- `show_view(arg2: str) -> None`: Show one through the identifier string specified view. Will throw a runtime error if this is called in Live's initialization scope.
- `toggle_browse() -> None`: Reveals the device chain, the browser and starts hot swap for the selected device. Calling this function again stops hot swap.
- `zoom_view(arg2: int, arg3: str, arg4: bool) -> None`: Zoom through the identifier string specified view into the given direction, if possible. Will silently return if the specified view can not perform the requested action.

## Functions

- `combine_apcs() -> bool`: Returns true if multiple APCs should be combined.
- `encrypt_challenge(dongle1: int, dongle2: int, key_index: int) -> tuple`: Returns an encrypted challenge based on the TEA algortithm
- `encrypt_challenge2(arg1: int) -> int`: Returns the UMAC hash for the given challenge.
- `get_application() -> Application.Application`: Returns the application instance.
- `get_random_int(arg1: int, arg2: int) -> int`: Returns a random integer from the given range.

## Enums

- `MessageButtons`: OK_BUTTON=0, OK_NEW_SET_BUTTON=1, OK_RETRY_BUTTON=2, SAVE_DONT_SAVE_BUTTON=3, OK_ACCOUNT_BUTTON=4, OK_PURCHASE_BUTTON=5
- `PushDialogType`: MESSAGE_BOX=0, OUT_OF_UNLOCKS_DIALOG=5, RENT_TO_OWN_LICENSE_EXPIRED_DIALOG=7
- `UnavailableFeature`: note_velocity_ranges_and_probabilities=0
- `NavDirection`: up=0, down=1, left=2, right=3

## Constants

- `Variants.BETA` = 'Beta'
- `Variants.INTRO` = 'Intro'
- `Variants.LITE` = 'Lite'
- `Variants.STANDARD` = 'Standard'
- `Variants.SUITE` = 'Suite'
- `Variants.TRIAL` = 'Trial'
