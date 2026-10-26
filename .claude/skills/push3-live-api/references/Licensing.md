# Live.Licensing

> Generated from a raw capture: Live 12.4.6, Intro, Push 3 standalone, AbletonOS x86_64 v3.21, Python 3.11.6, captured 2026-10-26. Do not edit; regenerate with `tools/gen_live_api_skill.py`.

## Licensing.ProgressDialog

A modal dialog showing a message and a progress animation.

Not constructable from Python.

Methods:

- `end_modal_loop() -> None`
- `run_in_modal_loop() -> None`
- `set_status_message(msg: str) -> None`

## Licensing.PythonLicensingBridge

Interface to the internal licensing services.

Not constructable from Python.

Properties (r = read-only, rw = settable):

- `base_product_id` (r): Returns Live's current base product ID.
- `in_sassafras_mode` (r)
- `license_must_match_variant` (r): Returns a bool indicating if we require the license information returned by the server to match the variant of Live.
- `random_number_for_trial_authorization` (r): Returns the integer to send along with the Trial authorization request. This same integer will be checked for in `process_trial_response` (and then changed).
- `set_has_unsaved_changes` (r): Returns true if the set has unsaved changes.

Methods:

- `authorize_with_sassafras() -> None`
- `create_new_live_set() -> None`: Creates a new live set and discards unsaved changes.
- `deauthenticate_user() -> None`: Deletes the current session ID.
- `get_progress_dialog() -> Licensing.ProgressDialog`: Retrieves an instance of ProgressDialog.
- `get_session_id() -> str`: Retrieve stored session ID.
- `get_startup_dialog(authorize_callable: object, authorize_later_callable: object) -> Licensing.StartupDialog`: Retrieves an instance of the startup dialog with the passed callables connected to its buttons.
- `get_trial_time_left() -> str`: Returns remaining time on a trial as a formatted string.
- `invoke_pack_installation_callback() -> None`: Call package installation callback.
- `invoke_promotions_callback(arg2: str) -> None` *(new)*: Call promotions callback.
- `load_and_convert_legacy_unlock_cfg() -> dict`: Loads the Unlock.cfg file and returns either an empty dict or one that can be converted to an UnlockData object.
- `process_license_response(license_response_lines: list) -> Licensing.UnlockStatus`: Processes a list of strings, each representing a server response to a product authorization.
- `process_trial_response(trial_response_line: str) -> bool`: Process the server's response to a Trial authorization.
- `request_exit(exit_code: int) -> None`
- `save_current_set() -> None`: Saves the current Live session.
- `set_network_timer(callback: object, interval_in_ms: int) -> None`: Starts or stops a timer meant for driving network operations. Pass None as callback to stop the timer. If any callback invocation raises an exception, the timer is stopped.
- `store_session_identifiers(session_id: str, external_session_id: str) -> None` *(new)*: Securely stores the user's session Identifiers (aka credentials).

## Licensing.StartupDialog

Serves as an entry point for the user to authorize Live on first launch.

Not constructable from Python.

Methods:

- `end_modal_loop() -> None`
- `run_in_modal_loop(show_only_offline_auth_instructions: bool) -> None`
- `set_notification_message(notification_text: str, show_progress_bar: bool) -> None`

## Licensing.UnlockStatus

Returns relevant information after unlock

Properties (r = read-only, rw = settable):

- `authorization_deactivated` (r)
- `authorization_expired` (r)
- `has_max_unlock_products` (r)
- `temp_demo_mode` (r)
- `time_limited` (r)
- `unlock_error` (r)
- `unlocked` (r)

Methods:

- `__init__() -> None`

## Functions

- `authorization_clock_days_ahead() -> int`: Advances the current date by the number of days specified by _AuthClockDaysAhead
- `get_authorization_page_url(reauthorize: bool, is_trial: bool) -> str`: Retrieves the appopriate URL on ableton.com where the unser can initiate the authorization.
- `get_purchase_live_url() -> str`: Returns the environment-aware purchase URL for purchasing Live licenses
- `get_services_url() -> str`: Returns the URL against which service calls (e.g. for authorization) can be performed.
- `get_unlock_dir() -> tuple`: Returns a tuple containing the unlock file directory and a flag indicating if the unlock file is in the system domain.
- `launch_web_browser(url: str) -> None`: Opens a web browser at the specified URL on the user's computer.

## Enums

- `TrialContext`: SAVE=0, FORCE_UPDATE=2, STARTUP=3
