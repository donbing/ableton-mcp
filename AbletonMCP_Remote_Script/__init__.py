# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import os
import socket
import json
import re
import math
import threading
import types
import collections
import time
import traceback

# Change queue import for Python 2
try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

# JSON strings arrive as unicode on Python 2 and str on Python 3.
try:
    _STRING_TYPES = (basestring,)  # noqa: F821  (Python 2)
except NameError:
    _STRING_TYPES = (str,)

# Constants for socket communication
DEFAULT_PORT = 9877
# Loopback, not 0.0.0.0. This socket takes unauthenticated commands that import
# arbitrary absolute paths, load browser items and drive the transport, so
# anything that can reach the port controls the DAW. Binding every interface
# exposed that to the whole local network — and to any network the machine is
# routable from.
#
# Running Live and the MCP server on different machines is the one legitimate
# reason to widen this; set ABLETON_MCP_HOST to do so deliberately, and put it
# behind a trusted network or an explicit relay.
HOST = os.environ.get("ABLETON_MCP_HOST", "127.0.0.1")

# A command that never completes must not grow the buffer without bound.
# Generous enough for a large add_notes_to_clip payload.
MAX_REQUEST_BYTES = 16 * 1024 * 1024

# Errors the command handlers raise on purpose for a bad request (an index out
# of range, a value outside a parameter's range, an unknown browser URI). The
# client already gets the message, so they are logged on one line; anything
# else is unexpected and is logged with its traceback.
EXPECTED_COMMAND_ERRORS = (ValueError, IndexError)

# Bumped whenever the TCP command surface changes; the MCP server compares
# this to EXPECTED_REMOTE_SCRIPT_VERSION.
SCRIPT_VERSION = "1.10.20"

# Shown on every undo / redo reply. Live merges edits made through the API into
# a single undo step, so one undo can revert several MCP changes.
UNDO_WARNING = (
    "WARNING: Live merges API-originated edits into ONE undo step, so a single "
    "undo/redo may revert SEVERAL MCP changes (everything since the user's last "
    "manual action) and also the user's own recent manual edits. Verify the "
    "session state afterwards. NOTE: since Remote Script 1.10.15 every MCP tool call "
    "is wrapped in its own undo step, so with a current script one undo normally "
    "reverts only the LAST tool call (tools that work in several steps, such as "
    "create_locator, set_track_routing and set_device_routing, can take more than one "
    "undo). Live's undo still reverts the user's own manual edits when no tool call "
    "came after them: read the session first.")
PROTOCOL_VERSION = 1

# get_meters sampling limits. The window is capped so a request can never tie
# up a client handler thread for long; the rate is capped because Live's meters
# refresh at roughly UI rate, so faster polling only re-reads the same value.
METER_MAX_SECONDS = 10.0
METER_MIN_HZ = 1.0
METER_MAX_HZ = 50.0
# Live's 0..1 meter reading is approximately LINEAR IN dB, not linear in
# amplitude (measured on Live 12 Lite: a constant synth through a fader at
# -36..-6 dB gave raw = 0.8281 + 0.01325 * dB, residuals < 0.014). So
# dB_approx = (raw - 0.85) / 0.01325, with 0.85 ~ 0 dBFS (the same fader-style
# scale: 0.85 = 0 dB, 0.4 = -18 dB, 1.0 = +6 dB). Values at or below
# METER_DB_FLOOR are treated as silence. Calibrated only for about -37..-7 dB.
METER_DB_REF = 0.85
METER_DB_SLOPE = 0.01325
METER_DB_FLOOR = 0.03
METER_SCALE = {
    "raw": ("Live's 0..1 meter reading, approximately linear in dB, "
            "NOT linear amplitude"),
    "db_approx": "(raw-0.85)/0.01325",
    "calibrated_range_db": [-37, -7],
    "accuracy_db": ("about +-1 dB (1 sigma), single readings up to about +-4 dB, inside the calibrated range; extrapolated "
                    "outside it (unverified)"),
}

# load_device_on_return waits this long after browser.load_item before it
# reads the return's device list back, so the list reflects the finished load.
LOAD_SETTLE_SECONDS = 0.3

# delete_arrangement_clips refuses (preview and delete alike) when more clips
# than this start inside the requested range: that is a sign of a wrong range,
# and a human cannot sensibly review a longer list.
MAX_ARRANGEMENT_CLIPS_PER_DELETE = 64
# Live.Clip.WarpMode integers (same numbers as the Live Object Model; 5 is
# unused). Names are what Live's clip view shows.
AUDIO_WARP_MODES = {
    0: "Beats",
    1: "Tones",
    2: "Texture",
    3: "Re-Pitch",
    4: "Complex",
    6: "Complex Pro",
}
AUDIO_CLIP_GAIN_RANGE = (0.0, 1.0)      # Clip.gain is a raw 0..1 value, not dB
AUDIO_CLIP_PITCH_COARSE_RANGE = (-48, 48)   # semitones
AUDIO_CLIP_PITCH_FINE_RANGE = (-50.0, 50.0)  # cents

SCRIPT_CAPABILITIES = [
    "get_session_info",
    "get_track_info",
    "get_script_info",
    "get_clip_notes",
    "get_device_parameters",
    "get_session_snapshot",
    "set_device_parameter",
    "drain_passive_events",
    "create_midi_track",
    "create_audio_track",
    "create_clip",
    "create_audio_clip",
    "add_notes_to_clip",
    "load_instrument_or_effect",
    "get_arrangement_clips",
    "duplicate_session_clip_to_arrangement",
    "create_locator",
    "delete_clip",
    "clear_notes_from_clip",
    "get_mixer",
    "set_track_volume",
    "set_track_panning",
    "set_send",
    "set_track_mute",
    "set_track_solo",
    "set_track_arm",
    "delete_track",
    "get_meters",
    "get_device_parameters_v2",
    "undo",
    "redo",
    # undo/redo take dry_run (default True): without it an undo would act at once
    "undo_confirm_guard",
    "get_clip_info",
    "set_clip_loop",
    "remove_notes_from_clip",
    "apply_note_modifications",
    "quantize_clip",
    "create_return_track",
    "load_device_on_return",
    "set_time_signature",
    "set_metronome",
    "get_arrangement_loop",
    "set_arrangement_loop",
    "get_cue_points",
    "jump_to_cue",
    "get_scenes",
    "create_scene",
    "duplicate_scene",
    "fire_scene",
    "set_scene_name",
    "stop_all_clips",
    "delete_scene",
    "delete_locator",
    "configure_simpler",
    "set_clip_launch",
    "set_transport_options",
    "delete_return_track",
    "get_drum_pads",
    "set_drum_pad",
    "rack_variations",
    "preview_browser_item",
    "stop_browser_preview",
    "set_plugin_window",
    "compare_device_ab",
    "list_clip_envelopes",
    "clear_all_clip_envelopes",
    "crop_clip",
    "get_take_lanes",
    "create_take_lane",
    "set_track_fold",
    "get_ui_state",
    "show_in_ui",
    "re_enable_automation",
    "capture_midi",
    "get_song_scale",
    "get_grooves",
    "insert_device",
    "move_device",
    "duplicate_device",
    "set_song_scale",
    "set_scene_tempo",
    "set_groove",
    "set_clip_groove",
    "edit_warp_marker",
    "duplicate_clip_loop",
    "copy_note_region",
    "copy_clip_to_slot",
    "undo_steps",
    "get_live_status",
    "press_dialog_button",
    "search_browser_items",
    "set_track_monitoring",
    "duplicate_track",
    "replace_clip_notes",
    "set_color",
    "get_tracks_overview",
    "check_arrangement_sync",
    "get_device_routing",
    "set_device_routing",
    "get_clip_envelope",
    "set_clip_envelope",
    "clear_clip_envelope",
    "back_to_arrangement",
    "get_track_routing",
    "set_track_routing",
    "clear_arrangement_range",
    "trim_arrangement_clip",
    "split_arrangement_clip",
    "move_arrangement_clip",
    "create_arrangement_clip",
    "delete_arrangement_clips",
    "delete_device",
    "get_audio_clip_info",
    "set_audio_clip_warp",
    "set_audio_clip_gain",
    "set_audio_clip_pitch",
]

def _finite_number(value, label):
    """Return value as a float, rejecting bool, non-numbers, NaN and infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("%s must be a number, got %r" % (label, value))
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise ValueError("%s must be finite, got %r" % (label, value))
    return number


# Grid name -> (Live RecordingQuantization value for Clip.quantize, grid in beats).
# 1, 2, 5 and 8 are confirmed by ahujasid/ableton-mcp#99 (quarter, eighth,
# sixteenth, thirty-second). 3 (eighth triplet) and 6 (sixteenth triplet)
# follow the same enum but are UNVERIFIED against a real Live.
QUANTIZE_GRIDS = {
    "1/4": (1, 1.0),
    "1/8": (2, 0.5),
    "1/8T": (3, 1.0 / 3.0),
    "1/16": (5, 0.25),
    "1/16T": (6, 1.0 / 6.0),
    "1/32": (8, 0.125),
}

# Fields apply_note_modifications may change on an existing note.
NOTE_EDIT_FIELDS = ("pitch", "start_time", "duration", "velocity", "mute")

# Per-note fields that only Live 11+ notes carry. Editable with apply_note_modifications
# and settable with add_notes_to_clip (through Clip.add_new_notes).
NOTE_EXTENDED_FIELDS = ("probability", "velocity_deviation", "release_velocity")

# How many notes a preview shows as a sample.
NOTE_SAMPLE_SIZE = 10


def _midi_int(value, label, low, high):
    """An int in [low, high]. Integral floats (60.0) are accepted; bool is not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("%s must be an integer, got %r" % (label, value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or value != int(value):
            raise ValueError("%s must be a whole number, got %r" % (label, value))
        value = int(value)
    if value < low or value > high:
        raise ValueError("%s must be between %d and %d, got %r" % (label, low, high, value))
    return value


def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""
    
    def __init__(self, c_instance):
        """Initialize the control surface"""
        ControlSurface.__init__(self, c_instance)
        self.log_message(
            "AbletonMCP Remote Script initializing... (script v%s)"
            % SCRIPT_VERSION
        )
        
        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        
        # Cache the song reference for easier access
        self._song = self.song()

        # Passive human-UI event queue (drained by MCP → Supabase)
        self._passive_events = []
        self._passive_lock = threading.Lock()
        self._passive_max = 500
        self._passive_track_count = None
        self._passive_track_bindings = []  # (track, [(add_name, callback), ...]) for cleanup
        self._song_passive_callbacks = []
        
        # Start the socket server
        self.start_server()

        # Register LOM listeners for passive capture (after song is ready)
        try:
            self._setup_passive_listeners()
        except Exception as e:
            self.log_message("Passive listener setup failed: " + str(e))
            self.log_message(traceback.format_exc())
        
        self.log_message("AbletonMCP initialized")
        
        # Show a message in Ableton
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))
    
    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False

        try:
            self._teardown_passive_listeners()
        except Exception as e:
            self.log_message("Passive listener teardown error: " + str(e))
        
        # Stop the server
        if self.server:
            try:
                self.server.close()
            except:
                pass
        
        # Wait for the server thread to exit
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)
            
        # Clean up any client threads
        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                # We don't join them as they might be stuck
                self.log_message("Client thread still alive during disconnect")
        
        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")
    
    def start_server(self):
        """Start the socket server in a separate thread"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)  # Allow up to 5 pending connections
            
            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.log_message("Server started on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))
            self.show_message("AbletonMCP: Error starting server - " + str(e))
    
    def _server_thread(self):
        """Server thread implementation - handles client connections"""
        try:
            self.log_message("Server thread started")
            # Set a timeout to allow regular checking of running flag
            self.server.settimeout(1.0)
            
            while self.running:
                try:
                    # Accept connections with timeout
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message("AbletonMCP: Client connected")
                    
                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                    # Keep track of client threads
                    self.client_threads.append(client_thread)
                    
                    # Clean up finished client threads
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]
                    
                except socket.timeout:
                    # No connection yet, just continue
                    continue
                except Exception as e:
                    if self.running:  # Only log if still running
                        self.log_message("Server accept error: " + str(e))
                    time.sleep(0.5)
            
            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message("Server thread error: " + str(e))
    
    def _handle_client(self, client):
        """Handle communication with a connected client"""
        self.log_message("Client handler started")
        client.settimeout(None)  # No timeout for client socket
        # Accumulate raw bytes, never per-chunk text. A multi-byte UTF-8
        # character (an accented clip name, an emoji) can straddle two recv()
        # boundaries; decoding each chunk on its own raises there, and the old
        # code answered that with an error frame pushed into a stream the
        # client was still reading a real response from — desynchronising the
        # connection for good.
        buffer = b''

        try:
            while self.running:
                try:
                    # Receive data
                    data = client.recv(8192)

                    if not data:
                        # Client disconnected
                        self.log_message("Client disconnected")
                        break

                    buffer += data

                    if len(buffer) > MAX_REQUEST_BYTES:
                        buffer = b''
                        raise ValueError(
                            "Request exceeded %d bytes without a complete JSON command"
                            % MAX_REQUEST_BYTES)

                    try:
                        # Only a fully received command decodes and parses.
                        # Either error means "not all here yet", so wait.
                        command = json.loads(buffer.decode('utf-8'))
                    except (ValueError, UnicodeDecodeError):
                        continue

                    buffer = b''  # Clear buffer after successful parse

                    self.log_message("Received command: " + str(command.get("type", "unknown")))

                    # Process the command and get response
                    response = self._process_command(command)

                    # Send the response with explicit encoding
                    client.sendall(json.dumps(response).encode('utf-8'))

                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())

                    # Every error that reaches here leaves the request/response
                    # stream in an unknown state, so report it and close rather
                    # than carry on out of step with the client.
                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except Exception:
                        pass
                    break
        except Exception as e:
            self.log_message("Error in client handler: " + str(e))
        finally:
            try:
                client.close()
            except:
                pass
            self.log_message("Client handler stopped")
    
    def _log_command_error(self, context, error):
        """Log a command error on one line, adding the traceback only when the
        error is not one of EXPECTED_COMMAND_ERRORS."""
        self.log_message("{0}: {1}".format(context, error))
        if not isinstance(error, EXPECTED_COMMAND_ERRORS):
            self.log_message(traceback.format_exc())

    def _process_command(self, command):
        """Process a command from the client and return a response"""
        command_type = command.get("type", "")
        params = command.get("params", {})
        
        # Initialize response
        response = {
            "status": "success",
            "result": {}
        }
        
        try:
            # Route the command to the appropriate handler
            if command_type == "get_script_info":
                response["result"] = self._get_script_info()
            elif command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index, params.get("track_type", "track"))
            elif command_type == "get_mixer":
                response["result"] = self._get_mixer(
                    params.get("track_index", 0), params.get("track_type", "track"))
            elif command_type == "get_arrangement_loop":
                response["result"] = self._get_arrangement_loop()
            elif command_type == "get_cue_points":
                response["result"] = self._get_cue_points()
            elif command_type == "get_scenes":
                response["result"] = self._get_scenes()
            elif command_type == "get_audio_clip_info":
                response["result"] = self._get_audio_clip_info(
                    params.get("track_index", 0), params.get("clip_index", 0),
                    params.get("arrangement", False))
            elif command_type == "get_meters":
                # Deliberately NOT scheduled on the main thread: it samples for
                # up to METER_MAX_SECONDS and must not block Live. See
                # _get_meters.
                response["result"] = self._get_meters(
                    params.get("seconds", 2.0), params.get("hz", 20),
                    params.get("source", "output"))
            elif command_type == "get_song_scale":
                response["result"] = self._get_song_scale()
            elif command_type == "get_ui_state":
                response["result"] = self._get_ui_state()
            elif command_type == "set_transport_options":
                # Socket thread: Live applies these flags on the next tick, so it waits and reads back.
                response["result"] = self._set_transport_options(
                    params.get("punch_in"), params.get("punch_out"), params.get("arrangement_overdub"),
                    params.get("clip_trigger_quantization"), params.get("midi_recording_quantization"))
            elif command_type == "get_drum_pads":
                response["result"] = self._get_drum_pads(
                    params.get("track_index", 0), params.get("device_index", 0),
                    params.get("track_type", "track"), params.get("include_empty", False))
            elif command_type == "get_take_lanes":
                response["result"] = self._get_take_lanes(params.get("track_index", 0))
            elif command_type == "list_clip_envelopes":
                response["result"] = self._list_clip_envelopes(
                    params.get("track_index", 0), params.get("clip_index", 0))
            elif command_type == "get_grooves":
                response["result"] = self._get_grooves()
            elif command_type == "get_live_status":
                response["result"] = self._get_live_status()
            elif command_type == "get_track_routing":
                response["result"] = self._get_track_routing(
                    params.get("track_index", 0), params.get("track_type", "track"))
            elif command_type == "set_track_routing":
                # Socket thread: Live updates the available channels a moment
                # after the routing type changes, so the steps wait. See
                # _set_track_routing.
                response["result"] = self._set_track_routing(
                    params.get("track_index", 0), params.get("track_type", "track"),
                    params.get("expected_name"), params.get("direction"),
                    params.get("routing_type"), params.get("routing_channel"))
            elif command_type == "get_tracks_overview":
                response["result"] = self._get_tracks_overview()
            elif command_type == "check_arrangement_sync":
                response["result"] = self._check_arrangement_sync(
                    params.get("grid_beats", 4.0), params.get("tolerance", 1e-3))
            elif command_type == "get_device_routing":
                response["result"] = self._get_device_routing(
                    params.get("track_index", 0), params.get("device_index", 0),
                    params.get("track_type", "track"))
            elif command_type == "set_device_routing":
                # Socket thread: Live lists the channels of a new routing type a moment later.
                response["result"] = self._set_device_routing(
                    params.get("track_index", 0), params.get("device_index", 0),
                    params.get("track_type", "track"), params.get("expected_name"),
                    params.get("expected_device_name"), params.get("routing_type"),
                    params.get("routing_channel"), params.get("sidechain_on"))
            elif command_type == "get_clip_envelope":
                response["result"] = self._get_clip_envelope(
                    params.get("track_index", 0), params.get("clip_index", 0),
                    params.get("parameter"), params.get("device_index"),
                    params.get("arrangement", False), params.get("clip_start_time"),
                    params.get("start"), params.get("end"), params.get("step", 0.25))
            elif command_type == "delete_locator":
                # Socket thread, like create_locator: it has to wait for Live.
                response["result"] = self._delete_locator(
                    params.get("time"), params.get("expected_name"),
                    params.get("dry_run", True))
            elif command_type == "create_locator":
                # Deliberately NOT one main-thread task: it moves the playhead,
                # waits for Live to apply it and only then toggles the cue. See
                # _create_locator.
                response["result"] = self._create_locator(
                    params.get("name", ""), params.get("time", 0.0))
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "create_audio_track", "set_track_name",
                                 "set_track_mute", "set_track_solo", "set_track_arm",
                                 "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
                                 "set_arrangement_clip_name",
                                 "set_audio_clip_warp", "set_audio_clip_gain",
                                 "set_audio_clip_pitch",
                                 "delete_clip",
                                 "delete_track",
                                 "delete_arrangement_clips", "delete_device",
                                 "press_dialog_button",
                                 "configure_simpler",
                                 "set_clip_launch",
                                 "delete_return_track", "set_drum_pad", "rack_variations",
                                 "preview_browser_item", "stop_browser_preview", "set_plugin_window",
                                 "compare_device_ab", "clear_all_clip_envelopes", "crop_clip",
                                 "create_take_lane", "set_track_fold", "show_in_ui",
                                 "re_enable_automation", "capture_midi",
                                 "insert_device",
                                 "move_device",
                                 "duplicate_device",
                                 "set_song_scale",
                                 "set_scene_tempo",
                                 "set_groove",
                                 "set_clip_groove",
                                 "edit_warp_marker",
                                 "duplicate_clip_loop",
                                 "copy_note_region",
                                 "copy_clip_to_slot",
                                 "set_track_monitoring", "duplicate_track",
                                 "replace_clip_notes", "set_color",
                                 "set_clip_envelope", "clear_clip_envelope",
                                 "back_to_arrangement",
                                 "clear_arrangement_range",
                                 "trim_arrangement_clip",
                                 "split_arrangement_clip",
                                 "move_arrangement_clip",
                                 "create_arrangement_clip",
                                 "clear_notes_from_clip",
                                 "set_clip_loop",
                                 "remove_notes_from_clip",
                                 "apply_note_modifications",
                                 "quantize_clip",
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback",
                                 "undo", "redo",
                                 "load_browser_item", "load_instrument_or_effect",
                                 # Arrangement view – must run on the main thread
                                 "switch_to_arrangement_view", "set_current_song_time",
                                 "duplicate_session_clip_to_arrangement",
                                 "map_rack_magnitude", "inspect_rack",
                                 # Mixer – must run on the main thread
                                 "set_track_volume", "set_track_panning", "set_send",
                                 # Session scenes – must run on the main thread
                                 "create_scene", "duplicate_scene", "fire_scene",
                                 "set_scene_name", "stop_all_clips", "delete_scene",
                                 # Return tracks
                                 "create_return_track", "load_device_on_return",
                                 # Transport
                                 "set_time_signature", "set_metronome",
                                 "set_arrangement_loop", "jump_to_cue"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()
                
                # Define a function to execute on the main thread
                def main_thread_task():
                    undo_open = self._begin_undo_step(command_type)
                    try:
                        result = None
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "create_audio_track":
                            index = params.get("index", -1)
                            result = self._create_audio_track(index)
                        elif command_type == "set_track_name":
                            track_index = params.get("track_index", 0)
                            name = params.get("name", "")
                            result = self._set_track_name(track_index, name)
                        elif command_type == "create_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            length = params.get("length", 4.0)
                            result = self._create_clip(track_index, clip_index, length)
                        elif command_type == "create_audio_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            path = params.get("path", "")
                            result = self._create_audio_clip(track_index, clip_index, path,
                                                             params.get("warping"))
                        elif command_type == "add_notes_to_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_clip(track_index, clip_index, notes,
                                                             params.get("clip_start_time"))
                        elif command_type == "clear_notes_from_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._clear_notes_from_clip(track_index, clip_index,
                                                                 params.get("clip_start_time"))
                        elif command_type == "remove_notes_from_clip":
                            result = self._remove_notes_from_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("from_time"),
                                params.get("time_span"),
                                params.get("from_pitch"),
                                params.get("pitch_span"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True),
                                params.get("clip_start_time"))
                        elif command_type == "apply_note_modifications":
                            result = self._apply_note_modifications(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("notes"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True),
                                params.get("clip_start_time"))
                        elif command_type == "quantize_clip":
                            result = self._quantize_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("grid"),
                                params.get("amount", 1.0),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True),
                                params.get("clip_start_time"))
                        elif command_type == "set_clip_loop":
                            result = self._set_clip_loop(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("loop_start"),
                                params.get("loop_end"),
                                params.get("looping"))
                        elif command_type == "set_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_clip_name(track_index, clip_index, name)
                        elif command_type == "set_arrangement_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_arrangement_clip_name(track_index, clip_index, name)
                        elif command_type == "set_audio_clip_warp":
                            result = self._set_audio_clip_warp(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("warping"),
                                params.get("warp_mode"),
                                params.get("arrangement", False))
                        elif command_type == "set_audio_clip_gain":
                            result = self._set_audio_clip_gain(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("gain"),
                                params.get("arrangement", False))
                        elif command_type == "set_audio_clip_pitch":
                            result = self._set_audio_clip_pitch(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("pitch_coarse"),
                                params.get("pitch_fine"),
                                params.get("arrangement", False))
                        elif command_type in ("set_track_mute", "set_track_solo", "set_track_arm"):
                            result = self._set_track_flag(
                                command_type[len("set_track_"):],
                                params.get("track_index", 0),
                                params.get("enabled"),
                                params.get("track_type", "track"),
                                params.get("expected_name"))
                        elif command_type == "set_tempo":
                            tempo = params.get("tempo", 120.0)
                            result = self._set_tempo(tempo)
                        elif command_type == "fire_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._fire_clip(track_index, clip_index)
                        elif command_type == "stop_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._stop_clip(track_index, clip_index)
                        elif command_type == "delete_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._delete_clip(track_index, clip_index)
                        elif command_type == "delete_track":
                            result = self._delete_track(
                                params.get("track_index", 0),
                                params.get("expected_name"),
                                params.get("track_type", "track"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True))
                        elif command_type == "delete_arrangement_clips":
                            result = self._delete_arrangement_clips(
                                params.get("track_index", 0),
                                params.get("expected_name"),
                                params.get("start_time"),
                                params.get("end_time"),
                                # Preview unless the caller explicitly opts in.
                                params.get("confirm", False))
                        elif command_type == "back_to_arrangement":
                            result = self._back_to_arrangement()
                        elif command_type == "set_clip_envelope":
                            result = self._set_clip_envelope(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_name"), params.get("parameter"),
                                params.get("device_index"), params.get("arrangement", False),
                                params.get("clip_start_time"), params.get("points"),
                                params.get("mode", "linear"), params.get("resolution", 0.125),
                                params.get("end"), params.get("confirm", False),
                                params.get("shape"), params.get("value_unit", "raw"))
                        elif command_type == "clear_clip_envelope":
                            result = self._clear_clip_envelope(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_name"), params.get("parameter"),
                                params.get("device_index"), params.get("arrangement", False),
                                params.get("clip_start_time"), params.get("confirm", False))
                        elif command_type == "replace_clip_notes":
                            result = self._replace_clip_notes(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_clip_name"), params.get("notes"),
                                params.get("confirm", False), params.get("clip_start_time"))
                        elif command_type == "set_color":
                            result = self._set_color(
                                params.get("kind"), params.get("color_index"),
                                params.get("track_index"), params.get("clip_index"),
                                params.get("scene_index"), params.get("track_type", "track"),
                                params.get("expected_name"))
                        elif command_type == "set_track_monitoring":
                            result = self._set_track_monitoring(
                                params.get("track_index", 0), params.get("state"),
                                params.get("expected_name"))
                        elif command_type == "duplicate_track":
                            result = self._duplicate_track(
                                params.get("track_index", 0), params.get("expected_name"))
                        elif command_type == "press_dialog_button":
                            result = self._press_dialog_button(
                                params.get("button_index"), params.get("expected_message"))
                        elif command_type == "insert_device":
                            result = self._insert_device(
                                params.get("track_index", 0), params.get("device_name"),
                                params.get("index", -1), params.get("track_type", "track"),
                                params.get("expected_name"))
                        elif command_type == "move_device":
                            result = self._move_device(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("new_index"), params.get("expected_name"),
                                params.get("expected_device_name"), params.get("track_type", "track"),
                                params.get("to_track_index"), params.get("to_track_type", "track"),
                                params.get("to_expected_name"))
                        elif command_type == "duplicate_device":
                            result = self._duplicate_device(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("track_type", "track"))
                        elif command_type == "set_song_scale":
                            result = self._set_song_scale(
                                params.get("root_note"), params.get("scale_name"), params.get("scale_mode"))
                        elif command_type == "set_scene_tempo":
                            result = self._set_scene_tempo(
                                params.get("scene_index"), params.get("tempo"), params.get("numerator"),
                                params.get("denominator"), params.get("clear", False),
                                params.get("expected_name"))
                        elif command_type == "set_groove":
                            result = self._set_groove(
                                params.get("groove_index"), params.get("timing_amount"),
                                params.get("quantization_amount"), params.get("random_amount"),
                                params.get("velocity_amount"), params.get("groove_amount"))
                        elif command_type == "set_clip_groove":
                            result = self._set_clip_groove(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("groove_index"), params.get("clip_start_time"))
                        elif command_type == "edit_warp_marker":
                            result = self._edit_warp_marker(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("action"), params.get("beat_time"), params.get("seconds"),
                                params.get("distance"), params.get("clip_start_time"))
                        elif command_type == "duplicate_clip_loop":
                            result = self._duplicate_clip_loop(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("clip_start_time"))
                        elif command_type == "copy_note_region":
                            result = self._copy_note_region(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("region_start"), params.get("region_length"),
                                params.get("destination_time"), params.get("pitch", -1),
                                params.get("transposition", 0), params.get("clip_start_time"))
                        elif command_type == "copy_clip_to_slot":
                            result = self._copy_clip_to_slot(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("to_track_index"), params.get("to_clip_index"),
                                params.get("overwrite", False))
                        elif command_type == "set_clip_launch":
                            result = self._set_clip_launch(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_name"), params.get("launch_quantization"),
                                params.get("launch_mode"), params.get("legato"))
                        elif command_type == "delete_return_track":
                            result = self._delete_return_track(
                                params.get("index"), params.get("expected_name"), params.get("confirm", False))
                        elif command_type == "set_drum_pad":
                            result = self._set_drum_pad(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("note"), params.get("mute"), params.get("solo"),
                                params.get("track_type", "track"))
                        elif command_type == "rack_variations":
                            result = self._rack_variations(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("action", "status"), params.get("index"),
                                params.get("confirm", False), params.get("track_type", "track"))
                        elif command_type == "preview_browser_item":
                            result = self._preview_browser_item(params.get("uri"))
                        elif command_type == "stop_browser_preview":
                            result = self._stop_browser_preview()
                        elif command_type == "set_plugin_window":
                            result = self._set_plugin_window(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("open"), params.get("track_type", "track"))
                        elif command_type == "compare_device_ab":
                            result = self._compare_device_ab(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("action", "status"), params.get("track_type", "track"))
                        elif command_type == "clear_all_clip_envelopes":
                            result = self._clear_all_clip_envelopes(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_name"), params.get("confirm", False))
                        elif command_type == "crop_clip":
                            result = self._crop_clip(
                                params.get("track_index", 0), params.get("clip_index", 0),
                                params.get("expected_name"), params.get("confirm", False),
                                params.get("clip_start_time"))
                        elif command_type == "create_take_lane":
                            result = self._create_take_lane(params.get("track_index", 0), params.get("expected_name"))
                        elif command_type == "set_track_fold":
                            result = self._set_track_fold(params.get("track_index", 0),
                                                          params.get("expected_name"), params.get("folded"))
                        elif command_type == "show_in_ui":
                            result = self._show_in_ui(
                                params.get("track_index"), params.get("track_type", "track"),
                                params.get("scene_index"), params.get("clip_index"),
                                params.get("device_index"), params.get("view_name"),
                                params.get("envelope_parameter"), params.get("envelope_device_index"))
                        elif command_type == "re_enable_automation":
                            result = self._re_enable_automation()
                        elif command_type == "capture_midi":
                            result = self._capture_midi(params.get("destination", "auto"))
                        elif command_type == "configure_simpler":
                            result = self._configure_simpler(
                                params.get("track_index", 0), params.get("device_index"),
                                params.get("expected_name"), params.get("expected_device_name"),
                                params.get("sample_path"), params.get("playback_mode"),
                                params.get("retrigger"), params.get("slicing_playback_mode"),
                                params.get("track_type", "track"))
                        elif command_type == "clear_arrangement_range":
                            result = self._clear_arrangement_range(
                                params.get("track_index", 0), params.get("expected_name"),
                                params.get("start_time"), params.get("end_time"),
                                params.get("confirm", False))
                        elif command_type == "trim_arrangement_clip":
                            result = self._trim_arrangement_clip(
                                params.get("track_index", 0), params.get("expected_name"),
                                params.get("clip_start_time"), params.get("new_start_time"),
                                params.get("new_end_time"), params.get("confirm", False))
                        elif command_type == "split_arrangement_clip":
                            result = self._split_arrangement_clip(
                                params.get("track_index", 0), params.get("expected_name"),
                                params.get("clip_start_time"), params.get("split_time"),
                                params.get("confirm", False))
                        elif command_type == "move_arrangement_clip":
                            result = self._move_arrangement_clip(
                                params.get("track_index", 0), params.get("expected_name"),
                                params.get("clip_start_time"), params.get("new_start_time"),
                                params.get("copy", False), params.get("confirm", False),
                                params.get("to_track_index"), params.get("to_expected_name"))
                        elif command_type == "create_arrangement_clip":
                            result = self._create_arrangement_clip(
                                params.get("track_index", 0), params.get("expected_name"),
                                params.get("start_time"), params.get("length"),
                                params.get("notes"), params.get("path"),
                                params.get("name", ""), params.get("confirm", False))
                        elif command_type == "delete_device":
                            result = self._delete_device(
                                params.get("track_index", 0),
                                params.get("device_index", 0),
                                params.get("expected_name"),
                                params.get("expected_device_name"),
                                params.get("confirm", False),
                                params.get("track_type", "track"))
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type in ("undo", "redo"):
                            result = self._undo_redo(
                                command_type, params.get("dry_run", True))
                        elif command_type == "load_instrument_or_effect":
                            track_index = params.get("track_index", 0)
                            uri = params.get("uri", "")
                            result = self._load_instrument_or_effect(track_index, uri)
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                        # ── Arrangement view commands ──────────────────────────────
                        elif command_type == "switch_to_arrangement_view":
                            result = self._switch_to_arrangement_view()
                        elif command_type == "set_current_song_time":
                            time_val = params.get("time", 0.0)
                            result = self._set_current_song_time(time_val)
                        elif command_type == "duplicate_session_clip_to_arrangement":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            destination_time = params.get("destination_time", 0.0)
                            result = self._duplicate_session_clip_to_arrangement(
                                track_index, clip_index, destination_time)
                        elif command_type == "map_rack_magnitude":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            macro_name = params.get("macro_name", "Magnitude")
                            result = self._map_rack_magnitude(
                                track_index, device_index, macro_name)
                        elif command_type == "inspect_rack":
                            track_index = params.get("track_index", 0)
                            device_index = params.get("device_index", 0)
                            result = self._inspect_rack(track_index, device_index)
                        # ── Mixer commands ─────────────────────────────────────────
                        elif command_type == "set_track_volume":
                            result = self._set_track_volume(
                                params.get("track_index", 0),
                                params.get("db", None),
                                params.get("value", None),
                                params.get("track_type", "track"))
                        # ── Return tracks ──────────────────────────────────────────
                        elif command_type == "create_return_track":
                            result = self._create_return_track(params.get("name", ""))
                        elif command_type == "load_device_on_return":
                            result = self._load_device_on_return(
                                params.get("return_track_index", 0),
                                params.get("uri", ""))
                        # ── Transport ──────────────────────────────────────────────
                        elif command_type == "set_time_signature":
                            result = self._set_time_signature(
                                params.get("numerator"), params.get("denominator"))
                        elif command_type == "set_metronome":
                            result = self._set_metronome(params.get("enabled"))
                        elif command_type == "set_arrangement_loop":
                            result = self._set_arrangement_loop(
                                params.get("loop_start"), params.get("loop_length"),
                                params.get("enabled"))
                        elif command_type == "jump_to_cue":
                            result = self._jump_to_cue(params.get("direction"))
                        # ── Session scene commands ─────────────────────────────────
                        # No default scene_index: a call that forgets it must fail,
                        # not quietly act on scene 0.
                        elif command_type == "create_scene":
                            result = self._create_scene(
                                params.get("index", -1), params.get("name", ""))
                        elif command_type == "duplicate_scene":
                            result = self._duplicate_scene(params.get("scene_index"))
                        elif command_type == "fire_scene":
                            result = self._fire_scene(params.get("scene_index"))
                        elif command_type == "set_scene_name":
                            result = self._set_scene_name(
                                params.get("scene_index"), params.get("name"))
                        elif command_type == "stop_all_clips":
                            result = self._stop_all_clips()
                        elif command_type == "delete_scene":
                            result = self._delete_scene(
                                params.get("scene_index"),
                                params.get("expected_name"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True))
                        elif command_type == "set_track_panning":
                            result = self._set_track_panning(
                                params.get("track_index", 0),
                                params.get("value", 0.0),
                                params.get("track_type", "track"))
                        elif command_type == "set_send":
                            result = self._set_send(
                                params.get("track_index", 0),
                                params.get("send_index", 0),
                                params.get("db", None),
                                params.get("value", None),
                                params.get("track_type", "track"))

                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self._log_command_error("Error in main thread task", e)
                        response_queue.put({"status": "error", "message": str(e)})
                    finally:
                        self._end_undo_step(undo_open)
                
                # Schedule the task to run on the main thread
                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    # If we're already on the main thread, execute directly
                    main_thread_task()
                
                # create_audio_clip decodes/imports the file on the main
                # thread and needs more than the default headroom.
                long_running_commands = {"create_audio_clip": 60.0}
                queue_timeout = long_running_commands.get(command_type, 10.0)
                try:
                    task_response = response_queue.get(timeout=queue_timeout)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                        if command_type == "load_device_on_return":
                            # Settle on this client thread (never on Live's
                            # main thread), then read the device list back.
                            response["result"] = self._verify_load_on_return(
                                response["result"])
                        elif command_type in ("load_browser_item", "load_instrument_or_effect"):
                            response["result"] = self._verify_load_on_track(response["result"])
                        elif command_type == "set_current_song_time":
                            response["result"] = self._verify_song_time(response["result"])
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            elif command_type == "search_browser_items":
                # Socket thread, like the other browser reads: it can walk many
                # items, so it works against a time budget.
                response["result"] = self._search_browser_items(
                    params.get("query"), params.get("category", "all"),
                    params.get("max_results", 20), params.get("max_seconds", 6.0),
                    params.get("loadable_only", False))
            elif command_type == "get_browser_item":
                uri = params.get("uri", None)
                path = params.get("path", None)
                response["result"] = self._get_browser_item(uri, path)
            elif command_type == "get_browser_categories":
                category_type = params.get("category_type", "all")
                response["result"] = self._get_browser_categories(category_type)
            elif command_type == "get_browser_items":
                path = params.get("path", "")
                item_type = params.get("item_type", "all")
                response["result"] = self._get_browser_items(path, item_type)
            # Add the new browser commands
            elif command_type == "get_browser_tree":
                category_type = params.get("category_type", "all")
                response["result"] = self.get_browser_tree(category_type)
            elif command_type == "get_browser_items_at_path":
                path = params.get("path", "")
                response["result"] = self.get_browser_items_at_path(path)
            # Read-only arrangement command – no main-thread scheduling required
            elif command_type == "get_arrangement_clips":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_arrangement_clips(track_index)
            # Dataset / state-snapshot reads
            elif command_type == "get_clip_notes":
                track_index = params.get("track_index", 0)
                clip_index = params.get("clip_index", 0)
                response["result"] = self._get_clip_notes(track_index, clip_index,
                                                          params.get("clip_start_time"))
            elif command_type == "get_clip_info":
                response["result"] = self._get_clip_info(
                    params.get("track_index", 0), params.get("clip_index", 0),
                    params.get("clip_start_time"))
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(
                    track_index, device_index,
                    name_contains=params.get("name_contains"),
                    limit=params.get("limit"),
                    include_racks=params.get("include_racks", False),
                    track_type=params.get("track_type", "track"))
            elif command_type == "get_session_snapshot":
                include_notes = params.get("include_notes", True)
                include_params = params.get("include_params", True)
                response["result"] = self._get_session_snapshot(
                    include_notes=include_notes,
                    include_params=include_params,
                )
            elif command_type == "drain_passive_events":
                response["result"] = self._drain_passive_events()
            elif command_type == "set_device_parameter":
                response_queue = queue.Queue()

                def main_thread_task():
                    undo_open = self._begin_undo_step(command_type)
                    try:
                        result = self._set_device_parameter(
                            params.get("track_index", 0),
                            params.get("device_index", 0),
                            params.get("parameter_index", 0),
                            params.get("value"),
                            params.get("track_type", "track"),
                            params.get("display_value"),
                        )
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self._log_command_error("Error in main thread task", e)
                        response_queue.put({"status": "error", "message": str(e)})
                    finally:
                        self._end_undo_step(undo_open)

                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    main_thread_task()

                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self._log_command_error("Error processing command", e)
            response["status"] = "error"
            response["message"] = str(e)
        
        return response
    
    # Command implementations

    def _get_script_info(self):
        """Handshake payload for MCP server version / capability checks."""
        return {
            "name": "AbletonMCP",
            "script_version": SCRIPT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "port": DEFAULT_PORT,
            "capabilities": list(SCRIPT_CAPABILITIES),
            "snapshot_schema": "ableton_mcp_snapshot_v2",
            "passive_listeners": True,
        }
    
    def _safe_song_property(self, attr, cast, default):
        """Read self._song.<attr> with cast, returning default on common failures.
        Catches only narrow exceptions so genuine bugs still surface."""
        try:
            return cast(getattr(self._song, attr))
        except (AttributeError, TypeError, ValueError):
            return default

    def _get_session_info(self):
        """Get information about the current session"""
        try:
            result = {
                "tempo": self._song.tempo,
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator,
                "track_count": len(self._song.tracks),
                "return_track_count": len(self._song.return_tracks),
                "master_track": {
                    "name": "Master",
                    "volume": self._song.master_track.mixer_device.volume.value,
                    "panning": self._song.master_track.mixer_device.panning.value
                },
                # Read via _safe_song_property so an attribute missing on a
                # given Live version falls back to its default.
                "is_playing":        self._safe_song_property("is_playing",        bool,  False),
                "current_song_time": self._safe_song_property("current_song_time", float, 0.0),
                "song_length":       self._safe_song_property("song_length",       float, 0.0),
                "loop":              self._safe_song_property("loop",              bool,  False),
                "loop_start":        self._safe_song_property("loop_start",        float, 0.0),
                "loop_length":       self._safe_song_property("loop_length",       float, 0.0),
            }
            return result
        except Exception as e:
            self.log_message("Error getting session info: " + str(e))
            raise
    
    def _get_meters(self, seconds=2.0, hz=20, source="output"):
        """Sample output_meter_left/right of every track over a time window.

        source "input": the level arriving at each track's input instead (audio tracks
        input_meter_left/right, MIDI tracks the one input_meter_level; returns and the
        master have none). That is the level to check before recording.

        Threading, deliberately: this runs on the client handler thread and
        never touches Live's main thread for longer than one attribute read.
        - It is NOT scheduled with schedule_message. That callback runs once
          per ~100 ms tick, so it cannot reach 20 Hz, and a 10 s window would
          have to be split across dozens of main-thread callbacks that compete
          with Live's own UI work.
        - It does not hold the main thread for the window either (a blocking
          main-thread loop would freeze Live for up to 10 s).
        - Between samples it sleeps on the handler thread. The reads are plain
          float properties, the same kind of off-thread LOM read that
          get_track_info and get_session_snapshot already do.
        If a track's meter cannot be read it is reported as unavailable and
        skipped; one bad track does not fail the call.

        Meter values are Live's own 0..1 readings, which are approximately
        LINEAR IN dB, not linear amplitude. *_db_approx = (raw - 0.85) / 0.01325
        (about 0.01325 per dB, 0.85 ~ 0 dBFS), measured on Live 12 Lite and
        accurate to about +-1 dB (1 sigma; single readings up to about +-4 dB) only inside roughly -37..-7 dB. Do not use
        20*log10(raw): that is off by tens of dB.
        """
        try:
            for label, val in (("seconds", seconds), ("hz", hz)):
                if (isinstance(val, bool) or not isinstance(val, (int, float))
                        or not math.isfinite(val) or val <= 0):
                    raise ValueError("%s must be a positive number, got %r" % (label, val))
            if source not in ("output", "input"):
                raise ValueError("source must be 'output' or 'input', got %r" % (source,))
            capped = seconds > METER_MAX_SECONDS
            seconds = min(float(seconds), METER_MAX_SECONDS)
            hz = min(max(float(hz), METER_MIN_HZ), METER_MAX_HZ)
            samples = int(round(seconds * hz)) + 1
            interval = 1.0 / hz

            groups = [
                ("tracks", list(self._song.tracks)),
                ("return_tracks", list(self._song.return_tracks)),
                ("master", [self._song.master_track]),
            ]
            stats = []
            for group, tracks in groups:
                for index, track in enumerate(tracks):
                    if source == "output":
                        left_attr, right_attr = "output_meter_left", "output_meter_right"
                    elif group != "tracks":
                        left_attr = right_attr = None           # returns and master have no input
                    elif self._safe_attr(track, "has_audio_input", bool, False):
                        left_attr, right_attr = "input_meter_left", "input_meter_right"
                    else:
                        left_attr = right_attr = "input_meter_level"
                    stats.append({
                        "group": group, "index": index, "track": track,
                        "name": self._safe_attr(track, "name", str, ""),
                        "peak_left": 0.0, "peak_right": 0.0,
                        "sum_left": 0.0, "sum_right": 0.0, "n": 0,
                        "left_attr": left_attr, "right_attr": right_attr,
                        "available": left_attr is not None,
                    })

            started = time.monotonic()
            taken = 0
            for i in range(samples):
                if not getattr(self, "running", True):
                    break
                for st in stats:
                    if not st["available"]:
                        continue
                    try:
                        left = float(getattr(st["track"], st["left_attr"]))
                        right = float(getattr(st["track"], st["right_attr"]))
                        if not (math.isfinite(left) and math.isfinite(right)):
                            raise ValueError("non-finite meter value")
                    except Exception:
                        st["available"] = False
                        continue
                    st["peak_left"] = max(st["peak_left"], left)
                    st["peak_right"] = max(st["peak_right"], right)
                    st["sum_left"] += left
                    st["sum_right"] += right
                    st["n"] += 1
                taken += 1
                if i < samples - 1:
                    wait = started + (i + 1) * interval - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
            elapsed = time.monotonic() - started

            def db_approx(x):
                if x <= METER_DB_FLOOR:
                    return None
                return round((x - METER_DB_REF) / METER_DB_SLOPE, 2)

            def report(st):
                entry = {"index": st["index"], "name": st["name"]}
                if not st["available"] or st["n"] == 0:
                    entry["meter_available"] = False
                    return entry
                mean_left = st["sum_left"] / st["n"]
                mean_right = st["sum_right"] / st["n"]
                peak = max(st["peak_left"], st["peak_right"])
                mean = (mean_left + mean_right) / 2.0
                entry.update({
                    "meter_available": True,
                    "peak": round(peak, 4),
                    "peak_db_approx": db_approx(peak),
                    "mean": round(mean, 4),
                    "mean_db_approx": db_approx(mean),
                    "peak_left": round(st["peak_left"], 4),
                    "peak_right": round(st["peak_right"], 4),
                    "mean_left": round(mean_left, 4),
                    "mean_right": round(mean_right, 4),
                })
                return entry

            result = {
                "seconds_requested": seconds,
                "seconds_elapsed": round(elapsed, 3),
                "hz": hz,
                "samples": taken,
                "capped_to_max_seconds": capped,
                "source": source,
                "is_playing": self._safe_song_property("is_playing", bool, False),
                "tracks": [report(st) for st in stats if st["group"] == "tracks"],
                "return_tracks": [report(st) for st in stats if st["group"] == "return_tracks"],
                "master": [report(st) for st in stats if st["group"] == "master"][0],
                "scale": dict(METER_SCALE, calibrated_range_db=list(
                    METER_SCALE["calibrated_range_db"])),
                "note": (
                    "peak/mean are Live's own output meter readings, 0..1 and "
                    "approximately linear in dB (NOT linear amplitude); peak = "
                    "loudest sample of either channel, mean = average of both "
                    "channels over the window. *_db_approx = (raw-0.85)/0.01325 "
                    "(see scale); null means silence (raw <= 0.03). Meters read "
                    "0 while nothing is playing."),
            }
            if source == "input":
                result["note"] = (
                    "source=input: the level at each track's input (audio tracks left/right, MIDI "
                    "tracks one value for both). Same 0..1 reading, but the dB conversion was "
                    "calibrated on output meters only, so treat *_db_approx of an input as a rough "
                    "guide. Tracks monitoring 'off' and not armed may read 0 even with a signal.")
            return result
        except Exception as e:
            self.log_message("Error getting meters: " + str(e))
            raise

    def _get_track_info(self, track_index, track_type="track"):
        """Get information about a track (track_type "return" or "master": its devices and mixer)"""
        try:
            if (track_type or "track").lower() != "track":
                track = self._resolve_track(track_index, track_type)
                return {
                    "index": track_index if track_type.lower() != "master" else None,
                    "track_type": track_type.lower(),
                    "name": track.name,
                    "volume": track.mixer_device.volume.value,
                    "panning": track.mixer_device.panning.value,
                    "devices": [{"index": i, "name": d.name, "class_name": d.class_name,
                                 "type": self._get_device_type(d)}
                                for i, d in enumerate(track.devices)],
                }
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Get clip slots
            clip_slots = []
            for slot_index, slot in enumerate(track.clip_slots):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_playing": clip.is_playing,
                        "is_recording": clip.is_recording
                    }
                
                clip_slots.append({
                    "index": slot_index,
                    "has_clip": slot.has_clip,
                    "clip": clip_info
                })
            
            # Get devices
            devices = []
            for device_index, device in enumerate(track.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })
            
            result = {
                "index": track_index,
                "name": track.name,
                "is_audio_track": track.has_audio_input,
                "is_midi_track": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "arm": self._safe_arm(track),
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    def _safe_arm(self, track):
        """Read track.arm, returning False for tracks that have no arm state.

        Live raises RuntimeError("Master and Return Tracks have no 'Arm'
        state!") for group tracks as well as return and main tracks. A
        `getattr(track, "arm", False)` does not guard this: the attribute
        exists, so getattr's default never applies -- reading it is what
        throws, and the error is a RuntimeError rather than an AttributeError.

        Check can_be_armed first so the common path does not rely on raising,
        and keep a narrow catch for Live versions that do not expose that
        property on every track type.
        """
        try:
            if not getattr(track, "can_be_armed", False):
                return False
            return bool(track.arm)
        except (AttributeError, RuntimeError):
            return False

    def _create_midi_track(self, index):
        """Create a new MIDI track at the specified index"""
        try:
            # Create the track
            self._song.create_midi_track(index)
            
            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]
            
            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating MIDI track: " + str(e))
            raise

    def _create_audio_track(self, index):
        """Create a new audio track at the specified index"""
        try:
            # Create the track
            self._song.create_audio_track(index)

            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]

            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio track: " + str(e))
            raise

    # ------------------------------------------------------------------
    # Mixer
    # ------------------------------------------------------------------

    def _db_for_value(self, param, value):
        """Return the dB a normalized parameter value displays as in Live.

        Live's fader taper has no published closed form, so rather than
        approximating it we ask Live what the value actually reads as and
        parse that. This stays correct across Live versions.

        Only displays that carry a "dB" unit are parsed. Anything else (a pan
        reading such as "50L") is not a level, and pulling its digits out would
        invent a bogus dB figure, so it raises instead.
        """
        raw = param.str_for_value(value)
        text = raw if isinstance(raw, str) else str(raw)
        # Normalize the unicode minus Live uses and locale decimal commas.
        text = text.replace("\u2212", "-")
        if "db" not in text.lower():
            raise ValueError("Display '%s' is not a dB value" % text)
        text = text.lower().replace("db", "").replace(",", ".").strip()
        if "inf" in text:
            return float("-inf")
        cleaned = "".join([c for c in text if c.isdigit() or c in "-+."])
        try:
            return float(cleaned)
        except Exception:
            raise ValueError("Could not parse dB from Live display '%s'" % raw)

    def _pan_percent_for_display(self, display):
        """Parse a pan display ("C", "50L", "25R") into -100..100, left negative.

        Returns None for anything else.
        """
        text = (display if isinstance(display, str) else str(display)).strip().upper()
        if text == "C":
            return 0
        m = re.match(r"^(\d+(?:[.,]\d+)?)\s*([LR])$", text) or re.match(
            r"^([LR])\s*(\d+(?:[.,]\d+)?)$", text)
        if not m:
            return None
        first, second = m.groups()
        number, side = (first, second) if first[0].isdigit() else (second, first)
        amount = float(number.replace(",", "."))
        amount = int(amount) if amount == int(amount) else amount
        return -amount if side == "L" else amount

    def _value_for_db(self, param, target_db):
        """Find the normalized value whose display matches target_db.

        dB rises monotonically with the fader value, so bisect against Live's
        own readout. ~40 steps exhausts float precision over the 0..1 range.

        Accuracy is bounded by Live's display resolution of 0.01 dB, which is
        two orders of magnitude below audibility. Targets outside the fader
        range clamp to its ends rather than raising.
        """
        target_db = float(target_db)
        low, high = param.min, param.max
        if target_db <= self._db_for_value(param, low):
            return low
        if target_db >= self._db_for_value(param, high):
            return high
        for _ in range(40):
            mid = (low + high) / 2.0
            if self._db_for_value(param, mid) < target_db:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    def _param_report(self, param, kind="level"):
        """Describe a mixer parameter as raw value, Live's display and a number.

        kind="level" (volume, sends): "db" is the level in dB. It is None when
        the display is not a dB figure, and None for silence ("-inf dB", where
        the display still says so), so the reply is always valid JSON.
        kind="pan": "db" is always None and "pan_percent" holds the position,
        -100 (hard left) .. 100 (hard right), parsed from Live's own "50L" /
        "C" / "25R" display. Reading a pan display as dB made off-centre pans
        report db=50.0.
        """
        display = param.str_for_value(param.value)
        report = {"value": param.value, "display": display, "db": None}
        if kind == "pan":
            report["pan_percent"] = self._pan_percent_for_display(display)
            return report
        try:
            db = self._db_for_value(param, param.value)
            report["db"] = None if db == float("-inf") else db
        except Exception:
            report["db"] = None
        return report

    def _apply_param(self, param, db=None, value=None):
        """Set a mixer parameter from either a dB target or a raw 0..1 value."""
        if value is not None:
            param.value = max(param.min, min(param.max, float(value)))
        elif db is not None:
            param.value = self._value_for_db(param, db)
        else:
            raise Exception("Provide either 'db' or 'value'")
        return self._param_report(param)

    def _get_mixer(self, track_index, track_type="track"):
        """Read volume, panning and sends for a mixer target."""
        try:
            track = self._resolve_track(track_index, track_type)
            mixer = track.mixer_device
            sends = []
            # The master track has no sends.
            for i, send in enumerate(getattr(mixer, "sends", []) or []):
                entry = self._param_report(send)
                entry["index"] = i
                entry["name"] = send.name
                sends.append(entry)
            return {
                "name": track.name,
                "track_type": (track_type or "track").lower(),
                "volume": self._param_report(mixer.volume),
                "panning": self._param_report(mixer.panning, kind="pan"),
                "sends": sends,
            }
        except Exception as e:
            self.log_message("Error getting mixer: " + str(e))
            raise

    def _set_track_volume(self, track_index, db=None, value=None, track_type="track"):
        """Set a track's volume, either to a dB target or a raw 0..1 value."""
        try:
            track = self._resolve_track(track_index, track_type)
            result = self._apply_param(track.mixer_device.volume, db, value)
            result["name"] = track.name
            return result
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_panning(self, track_index, value, track_type="track"):
        """Set a track's pan position. -1.0 is hard left, 1.0 is hard right."""
        try:
            track = self._resolve_track(track_index, track_type)
            param = track.mixer_device.panning
            param.value = max(param.min, min(param.max, float(value)))
            result = self._param_report(param, kind="pan")
            result["name"] = track.name
            return result
        except Exception as e:
            self.log_message("Error setting track panning: " + str(e))
            raise

    def _set_send(self, track_index, send_index, db=None, value=None, track_type="track"):
        """Set one of a track's send levels."""
        try:
            track = self._resolve_track(track_index, track_type)
            sends = getattr(track.mixer_device, "sends", []) or []
            if send_index < 0 or send_index >= len(sends):
                raise IndexError("Send index %s out of range (track '%s' has %d sends)"
                                 % (send_index, track.name, len(sends)))
            send = sends[send_index]
            result = self._apply_param(send, db, value)
            result["name"] = track.name
            result["send"] = send.name
            result["index"] = send_index
            return result
        except Exception as e:
            self.log_message("Error setting send: " + str(e))
            raise

    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            # Set the name
            track = self._song.tracks[track_index]
            track.name = name
            
            result = {
                "name": track.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting track name: " + str(e))
            raise

    def _resolve_track(self, track_index, track_type="track"):
        """Resolve (track_index, track_type) to a Live track object.

        track_type is "track", "return" or "master". For "master" the index is
        ignored. Rejects non-integer and out-of-range indices with a clear
        message rather than an opaque TypeError from list indexing.
        """
        kind = (track_type or "track").lower()
        if kind == "master":
            return self._song.master_track
        if kind == "return":
            tracks = self._song.return_tracks
        elif kind == "track":
            tracks = self._song.tracks
        else:
            raise ValueError(
                "Unknown track_type '%s' (expected track, return or master)" % track_type)
        if isinstance(track_index, bool) or not isinstance(track_index, int):
            raise TypeError("track_index must be an integer, got %r" % (track_index,))
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("%s index %d out of range (have %d)" % (kind, track_index, len(tracks)))
        return tracks[track_index]

    def _set_track_flag(self, flag, track_index, enabled, track_type="track",
                        expected_name=None):
        """Set Track.mute / Track.solo / Track.arm and report old and new state.

        Where the Live Object Model allows it:
        - mute and solo exist on regular, group and return tracks. The master
          track has neither, so it is refused with an explanation.
        - arm exists only on tracks whose can_be_armed is true. Group, return
          and master tracks are refused (reading or writing arm on them makes
          Live raise a RuntimeError; see _safe_arm).

        expected_name, when given, must equal the track's current name. It
        catches a stale index (tracks shifted after a create or delete) before
        the wrong track is changed.
        """
        try:
            if flag not in ("mute", "solo", "arm"):
                raise ValueError("Unknown track flag '%s'" % flag)
            if not isinstance(enabled, bool):
                raise TypeError("'%s' must be true or false, got %r" % (flag, enabled))
            kind = (track_type or "track").lower()
            track = self._resolve_track(track_index, track_type)
            if expected_name is not None and track.name != expected_name:
                raise ValueError(
                    "%s %s is '%s', not '%s'; indices may have shifted"
                    % (kind, track_index, track.name, expected_name))
            if kind == "master":
                raise ValueError("The master track has no %s state" % flag)
            if flag == "arm":
                if not getattr(track, "can_be_armed", False):
                    raise ValueError(
                        "Track '%s' cannot be armed (group, return and master "
                        "tracks have no arm state)" % track.name)
                previous = self._safe_arm(track)
                track.arm = enabled
                current = self._safe_arm(track)
            else:
                previous = bool(getattr(track, flag))
                setattr(track, flag, enabled)
                current = bool(getattr(track, flag))
            return {
                "track_index": track_index if kind != "master" else None,
                "track_type": kind,
                "name": track.name,
                "flag": flag,
                "previous": previous,
                "value": current,
                "changed": previous != current,
            }
        except Exception as e:
            self.log_message("Error setting track %s: %s" % (flag, str(e)))
            raise
    
    def _create_clip(self, track_index, clip_index, length):
        """Create a new MIDI clip in the specified track and clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            # Check if the clip slot already has a clip
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")
            
            # Create the clip
            clip_slot.create_clip(length)
            
            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length
            }
            return result
        except Exception as e:
            self.log_message("Error creating clip: " + str(e))
            raise

    def _create_audio_clip(self, track_index, clip_index, path, warping=None):
        """Create an audio clip in the specified audio track clip slot by importing a file.

        Requires Ableton Live 12.0.5 or newer (the underlying
        ClipSlot.create_audio_clip Live API was introduced in 12.0.5 — it is
        not available in earlier 12.0.x releases).
        """
        try:
            if not path:
                raise ValueError("Audio file path is required")

            if not os.path.isabs(path):
                raise ValueError("Audio file path must be absolute (got: %s)" % path)

            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if getattr(track, "has_midi_input", False) or not getattr(track, "has_audio_input", True):
                raise ValueError("Track %d is not an audio track" % track_index)

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")

            if not hasattr(clip_slot, "create_audio_clip"):
                raise Exception(
                    "ClipSlot.create_audio_clip is unavailable in this Ableton Live "
                    "version. Requires Live 12.0.5 or newer."
                )

            if warping is not None and not isinstance(warping, bool):
                raise TypeError("warping must be true or false")

            clip_slot.create_audio_clip(path)
            clip = clip_slot.clip

            # Live imports with auto-warp on, which can round the length to a
            # whole-bar / power-of-two beat count (upstream issue #137). Say what
            # happened, and let the caller turn warp off.
            if warping is not None and bool(clip.warping) != warping:
                clip.warping = warping
            result = {
                "name": clip.name,
                "length": clip.length,
                "is_audio_clip": clip.is_audio_clip,
                "warping": bool(clip.warping),
            }
            warp_name = getattr(clip, "warp_mode", None)
            if warp_name is not None:
                result["warp_mode"] = warp_name
            result["length_unit"] = "beats" if clip.warping else "seconds"
            try:
                seconds = float(clip.sample_length) / float(clip.sample_rate)
                result["file_seconds"] = seconds
                if not clip.warping:
                    # An unwarped clip plays the file at its own speed; Clip.length
                    # still reads the warped value in the same tick, so give the file's.
                    result["length"] = seconds
                tempo = float(self._song.tempo)
                result["file_beats_at_set_tempo"] = seconds * tempo / 60.0
                if clip.warping and abs(float(clip.length) - result["file_beats_at_set_tempo"]) > 0.05:
                    result["warning"] = (
                        "Live's auto-warp set the length to %s beats; the file is %.3f s, which is "
                        "%.3f beats at %s BPM. The clip is warped against the set. Pass warping=false "
                        "to keep the file's own length and timing (the clip's length then reads in seconds)."
                        % (float(clip.length), seconds, result["file_beats_at_set_tempo"], tempo))
            except Exception:
                pass
            return result
        except Exception as e:
            self.log_message("Error creating audio clip: " + str(e))
            raise

    def _validate_new_notes(self, clip, notes):
        """Check notes for add_notes_to_clip / replace_clip_notes.

        Returns (accepted, rejected, uses_extended). A malformed note raises and
        nothing is written; a note that starts before 0 or at or after the clip's
        end (it would never play) goes to rejected with the reason.
        """
        if not isinstance(notes, (list, tuple)):
            raise ValueError("notes must be a list of note objects")
        allowed = set(("pitch", "start_time", "duration", "velocity", "mute")
                      + NOTE_EXTENDED_FIELDS)
        length = float(clip.length)
        accepted = []
        rejected = []
        uses_extended = False
        for position, note in enumerate(notes):
            label = "notes[%d]" % position
            if not isinstance(note, dict):
                raise TypeError("%s must be an object, got %r" % (label, note))
            unknown = sorted(set(note) - allowed)
            if unknown:
                raise ValueError("%s has unknown field(s) %s; allowed: %s"
                                 % (label, ", ".join(unknown), ", ".join(sorted(allowed))))
            spec = {
                "pitch": _midi_int(note.get("pitch", 60), label + ".pitch", 0, 127),
                "start_time": _finite_number(note.get("start_time", 0.0), label + ".start_time"),
                "duration": _finite_number(note.get("duration", 0.25), label + ".duration"),
                "velocity": _finite_number(note.get("velocity", 100), label + ".velocity"),
                "mute": note.get("mute", False),
            }
            if not isinstance(spec["mute"], bool):
                raise TypeError("%s.mute must be true or false" % label)
            if spec["duration"] <= 0:
                raise ValueError("%s.duration must be > 0" % label)
            if spec["velocity"] < 1 or spec["velocity"] > 127:
                raise ValueError("%s.velocity must be between 1 and 127" % label)
            for field, low, high in (("probability", 0.0, 1.0), ("velocity_deviation", -127.0, 127.0),
                                     ("release_velocity", 0.0, 127.0)):
                if field in note:
                    spec[field] = _finite_number(note[field], "%s.%s" % (label, field))
                    if spec[field] < low or spec[field] > high:
                        raise ValueError("%s.%s must be between %s and %s"
                                         % (label, field, low, high))
                    uses_extended = True
            if spec["start_time"] < 0 or spec["start_time"] >= length:
                rejected.append({
                    "index": position, "pitch": spec["pitch"], "start_time": spec["start_time"],
                    "reason": "starts %s the clip (0 to %s beats), so it would never play"
                              % ("before" if spec["start_time"] < 0 else "at or after the end of",
                                 length)})
                continue
            accepted.append(spec)
        return accepted, rejected, uses_extended

    def _write_new_notes(self, clip, accepted, uses_extended):
        """Write validated notes: Clip.add_new_notes when there is one (it takes the
        Live 11+ fields), else the legacy set_notes."""
        if not accepted:
            return
        maker = None
        if hasattr(clip, "add_new_notes"):
            try:
                import Live
                maker = Live.Clip.MidiNoteSpecification
            except Exception:
                maker = None
        if maker is not None:
            clip.add_new_notes(tuple(maker(**spec) for spec in accepted))
        elif uses_extended:
            raise Exception(
                "This version of Live cannot set probability, velocity_deviation or "
                "release_velocity (needs Clip.add_new_notes, Live 11+). Nothing was added.")
        else:
            clip.set_notes(tuple(
                (n["pitch"], n["start_time"], n["duration"], n["velocity"], n["mute"])
                for n in accepted))

    @staticmethod
    def _count_clip_notes(clip):
        getter = getattr(clip, "get_notes_extended", None)
        if getter is None:
            return None
        return len(list(getter(0, 128, 0.0, float(clip.length))))

    def _add_notes_to_clip(self, track_index, clip_index, notes, clip_start_time=None):
        """Add MIDI notes to a Session clip and report what Live really kept.

        Each note: pitch (0-127), start_time (beats, inside the clip), duration,
        velocity (1-127), mute, and the Live 11+ fields probability (0-1),
        velocity_deviation (-127..127), release_velocity (0-127). An unknown
        field is an error and nothing is added. A note that starts before 0 or at
        or after the clip's end can never play, so it is NOT added and is listed
        in "rejected" with the reason (Live would keep it silently, hidden past
        the end). The reply counts the notes read back from the clip.
        """
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            if not getattr(clip, "is_midi_clip", False):
                raise Exception("Clip is not a MIDI clip")
            accepted, rejected, uses_extended = self._validate_new_notes(clip, notes)
            before = self._count_clip_notes(clip)
            self._write_new_notes(clip, accepted, uses_extended)
            after = self._count_clip_notes(clip)
            added = (after - before) if (before is not None and after is not None) else len(accepted)
            result = {"note_count": added, "sent": len(notes), "rejected": rejected,
                      "clip_note_count": after, "clip_length": float(clip.length)}
            if added != len(accepted):
                result["warning"] = ("Live kept %d of the %d notes that were sent for writing"
                                     % (added, len(accepted)))
            return result
        except Exception as e:
            self.log_message("Error adding notes to clip: " + str(e))
            raise

    def _replace_clip_notes(self, track_index, clip_index, expected_clip_name, notes, confirm=False,
                            clip_start_time=None):
        """Preview or replace ALL the notes of a Session MIDI clip with new ones.

        Everything is validated before anything is removed; a note that would
        never play (outside the clip) is an error here, since the old notes would
        be gone. If the write fails after the old notes were removed they are put
        back. Adapted from upstream PR #119 (mateogon). Previews unless confirm is
        exactly True; expected_clip_name (may be "") must equal the clip's name.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            if expected_clip_name is None or not isinstance(expected_clip_name, str):
                raise ValueError("expected_clip_name is required (the clip's exact current name, "
                                 "\"\" for an unnamed clip)")
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)
            if clip.name != expected_clip_name:
                raise ValueError("The clip is named '%s', not '%s'; nothing was changed."
                                 % (clip.name, expected_clip_name))
            accepted, rejected, uses_extended = self._validate_new_notes(clip, notes)
            if rejected:
                raise ValueError(
                    "%d of the new notes would never play (outside the clip), and the old notes "
                    "would be gone: %s. Nothing was changed."
                    % (len(rejected), "; ".join("note %d starts at %s" % (r["index"], r["start_time"])
                                                for r in rejected)))
            existing = self._count_clip_notes(clip)
            info = {"track_index": track_index, "clip_index": clip_index, "clip_name": clip.name,
                    "existing_note_count": existing, "new_note_count": len(accepted),
                    "applied": False, "dry_run": not do_apply}
            if not do_apply:
                return info
            getter = getattr(clip, "get_notes_extended", None)
            old = []
            if getter is not None:
                for n in getter(0, 128, 0.0, float(clip.length)):
                    spec = self._note_fields(n)
                    spec.pop("note_id", None)
                    old.append(spec)
            remover = getattr(clip, "remove_notes_extended", None)
            if remover is not None:
                remover(0, 128, 0.0, float(clip.length))
            else:
                clip.remove_notes(0.0, 0, float(clip.length), 128)
            try:
                self._write_new_notes(clip, accepted, uses_extended)
            except Exception as e:
                restored = "the %d old notes were put back" % len(old)
                try:
                    self._write_new_notes(
                        clip, old, any(k in n for n in old for k in NOTE_EXTENDED_FIELDS))
                except Exception:
                    # a Live without add_new_notes cannot restore probability and friends
                    plain = [dict((k, v) for k, v in n.items() if k not in NOTE_EXTENDED_FIELDS)
                             for n in old]
                    try:
                        self._write_new_notes(clip, plain, False)
                        restored = ("the %d old notes were put back WITHOUT their probability, "
                                    "velocity deviation and release velocity" % len(old))
                    except Exception as e2:
                        restored = "RESTORING THE OLD NOTES ALSO FAILED (%s); use Live's undo" % e2
                raise Exception("Writing the new notes failed (%s); %s." % (e, restored))
            after = self._count_clip_notes(clip)
            info["applied"] = True
            info["clip_note_count"] = after
            info["verified"] = after is None or after == len(accepted)
            return info
        except Exception as e:
            self.log_message("Error replacing clip notes: " + str(e))
            raise

    COLOR_INDEX_MAX = 69

    def _set_color(self, kind, color_index, track_index=None, clip_index=None, scene_index=None,
                   track_type="track", expected_name=None):
        """Set the colour (Live's palette index 0-69) of a track, a Session clip or a scene.

        Adapted from upstream PR #99 (Zachary May), merged into one tool. Reports
        the previous and the new index.
        """
        try:
            if kind not in ("track", "clip", "scene"):
                raise ValueError("kind must be 'track', 'clip' or 'scene'")
            if isinstance(color_index, bool) or not isinstance(color_index, int) \
                    or color_index < 0 or color_index > self.COLOR_INDEX_MAX:
                raise ValueError("color_index must be an integer 0-%d (Live's palette)"
                                 % self.COLOR_INDEX_MAX)
            if kind == "track":
                target = self._resolve_track(track_index, track_type)
                label = target.name
            elif kind == "clip":
                _t, target = self._session_clip(track_index, clip_index)
                label = target.name
            else:
                scenes = list(self._song.scenes)
                if isinstance(scene_index, bool) or not isinstance(scene_index, int) \
                        or scene_index < 0 or scene_index >= len(scenes):
                    raise IndexError("scene index out of range (have %d)" % len(scenes))
                target = scenes[scene_index]
                label = target.name
            if expected_name is not None and label != expected_name:
                raise ValueError("The %s is '%s', not '%s'; nothing was changed."
                                 % (kind, label, expected_name))
            if not hasattr(target, "color_index"):
                raise ValueError("This %s has no colour in this version of Live" % kind)
            # an uncoloured scene reads color_index as None
            before = target.color_index
            target.color_index = color_index
            now = target.color_index
            return {"kind": kind, "name": label,
                    "previous_color_index": None if before is None else int(before),
                    "color_index": None if now is None else int(now)}
        except Exception as e:
            self.log_message("Error setting colour: " + str(e))
            raise

    def _set_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            clip.name = name
            
            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip name: " + str(e))
            raise

    def _set_arrangement_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip placed in the Arrangement timeline.

        clip_index indexes into track.arrangement_clips, in the same order
        as returned by _get_arrangement_clips (i.e. ordered by start_time).
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            arrangement_clips = list(track.arrangement_clips)

            if clip_index < 0 or clip_index >= len(arrangement_clips):
                raise IndexError("Clip index out of range")

            clip = arrangement_clips[clip_index]
            clip.name = name

            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting arrangement clip name: " + str(e))
            raise

    # ── Audio clip properties (warp, gain, pitch) ─────────────────────────────
    #
    # Adapted from ahujasid/ableton-mcp#99 (Zachary May): the warp mode table
    # and the Clip.gain / pitch_coarse / pitch_fine / warping / warp_mode
    # attribute names. Reads follow #119 (mateogon, get_clip_properties) for
    # start_marker / end_marker. This version adds Arrangement clips, strict
    # validation before anything is written, and old/new reporting.

    def _resolve_audio_clip(self, track_index, clip_index, arrangement=False):
        """Return (clip, where) for an audio clip, or raise a clear error.

        arrangement False: clip_index is a Session slot on tracks[track_index].
        arrangement True: clip_index indexes list(track.arrangement_clips), the
        same order set_arrangement_clip_name uses. MIDI clips and empty slots
        are refused.
        """
        if not isinstance(arrangement, bool):
            raise TypeError("arrangement must be true or false, got %r" % (arrangement,))
        for label, value in (("track_index", track_index), ("clip_index", clip_index)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("%s must be an integer, got %r" % (label, value))
        tracks = self._song.tracks
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("Track index %d out of range (have %d tracks)"
                             % (track_index, len(tracks)))
        track = tracks[track_index]
        if arrangement:
            clips = list(track.arrangement_clips)
            if clip_index < 0 or clip_index >= len(clips):
                raise IndexError(
                    "Arrangement clip index %d out of range (track '%s' has %d "
                    "arrangement clips)" % (clip_index, track.name, len(clips)))
            clip = clips[clip_index]
            where = "arrangement clip %d on track %d ('%s')" % (
                clip_index, track_index, track.name)
        else:
            slots = track.clip_slots
            if clip_index < 0 or clip_index >= len(slots):
                raise IndexError(
                    "Clip slot index %d out of range (track '%s' has %d slots)"
                    % (clip_index, track.name, len(slots)))
            slot = slots[clip_index]
            if not slot.has_clip:
                raise ValueError("Slot %d on track %d ('%s') is empty"
                                 % (clip_index, track_index, track.name))
            clip = slot.clip
            where = "session clip slot %d on track %d ('%s')" % (
                clip_index, track_index, track.name)
        if not getattr(clip, "is_audio_clip", False):
            raise ValueError(
                "The clip at %s is not an audio clip (MIDI clips have no "
                "warp, gain or transpose of this kind)" % where)
        return clip, where

    def _audio_warp_mode_name(self, mode):
        if mode is None:
            return None
        return AUDIO_WARP_MODES.get(int(mode), "Unknown (%s)" % mode)

    def _parse_audio_warp_mode(self, warp_mode):
        """Return the Live warp mode integer for a name or a number, or raise."""
        valid = ", ".join("%s (%d)" % (n, i) for i, n in sorted(AUDIO_WARP_MODES.items()))
        if isinstance(warp_mode, bool):
            raise ValueError("warp_mode must be a name or number, got %r. Valid: %s"
                             % (warp_mode, valid))
        if isinstance(warp_mode, float) and warp_mode == int(warp_mode):
            warp_mode = int(warp_mode)
        if isinstance(warp_mode, int):
            if warp_mode not in AUDIO_WARP_MODES:
                raise ValueError("Unknown warp_mode %d. Valid: %s" % (warp_mode, valid))
            return warp_mode
        if isinstance(warp_mode, str):
            def norm(text):
                return "".join(ch for ch in text.lower() if ch.isalnum())
            key = norm(warp_mode)
            for number, name in AUDIO_WARP_MODES.items():
                if norm(name) == key:
                    return number
            if key.isdigit() and int(key) in AUDIO_WARP_MODES:
                return int(key)
        raise ValueError("Unknown warp_mode %r. Valid: %s" % (warp_mode, valid))

    def _audio_clip_properties(self, clip):
        """The audio properties of a clip, read defensively (None when absent)."""
        mode = self._safe_attr(clip, "warp_mode", int, None)
        return {
            "warping": self._safe_attr(clip, "warping", bool, None),
            "warp_mode": mode,
            "warp_mode_name": self._audio_warp_mode_name(mode),
            "gain": self._safe_attr(clip, "gain", float, None),
            "gain_display_string": self._safe_attr(clip, "gain_display_string", str, None),
            "pitch_coarse": self._safe_attr(clip, "pitch_coarse", int, None),
            "pitch_fine": self._safe_attr(clip, "pitch_fine", float, None),
        }

    def _get_audio_clip_info(self, track_index, clip_index, arrangement=False):
        """Read an audio clip's length, warp, gain, pitch, markers and file."""
        try:
            clip, where = self._resolve_audio_clip(track_index, clip_index, arrangement)
            info = {
                "track_index": track_index,
                "clip_index": clip_index,
                "arrangement": bool(arrangement),
                "name": self._safe_attr(clip, "name", str, ""),
                "length": self._safe_attr(clip, "length", float, None),
                "looping": self._safe_attr(clip, "looping", bool, None),
                "loop_start": self._safe_attr(clip, "loop_start", float, None),
                "loop_end": self._safe_attr(clip, "loop_end", float, None),
                "start_marker": self._safe_attr(clip, "start_marker", float, None),
                "end_marker": self._safe_attr(clip, "end_marker", float, None),
            }
            if arrangement:
                info["start_time"] = self._safe_attr(clip, "start_time", float, None)
                info["end_time"] = self._safe_attr(clip, "end_time", float, None)
            info.update(self._audio_clip_properties(clip))
            for attr in ("file_path", "file_path_relative"):
                path = self._safe_attr(clip, attr, str, None)
                if path:
                    info["file_path"] = path
                    break
            markers = self._warp_markers_from_clip(clip)
            info["warp_markers"] = markers
            info["warp_marker_count"] = len(markers)
            return info
        except Exception as e:
            self.log_message("Error getting audio clip info: " + str(e))
            raise

    def _audio_clip_change_report(self, track_index, clip_index, arrangement, clip,
                                  where, previous, names):
        current = self._audio_clip_properties(clip)
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "arrangement": bool(arrangement),
            "clip": where,
            "name": self._safe_attr(clip, "name", str, ""),
            "previous": dict((n, previous.get(n)) for n in names),
            "value": dict((n, current.get(n)) for n in names),
            "changed": any(previous.get(n) != current.get(n) for n in names),
        }

    def _set_audio_clip_warp(self, track_index, clip_index, warping,
                             warp_mode=None, arrangement=False):
        """Turn warping on or off and/or choose the warp mode of an audio clip.

        warping must be a real boolean. warp_mode is a name (Beats, Tones,
        Texture, Re-Pitch, Complex, Complex Pro) or Live's number (0, 1, 2, 3,
        4, 6); anything else is refused. Everything is validated before
        anything is written.
        """
        try:
            if not isinstance(warping, bool):
                raise TypeError("warping must be true or false, got %r" % (warping,))
            mode_int = None
            if warp_mode is not None:
                mode_int = self._parse_audio_warp_mode(warp_mode)
            clip, where = self._resolve_audio_clip(track_index, clip_index, arrangement)
            previous = self._audio_clip_properties(clip)
            clip.warping = warping
            if mode_int is not None:
                clip.warp_mode = mode_int
            return self._audio_clip_change_report(
                track_index, clip_index, arrangement, clip, where, previous,
                ("warping", "warp_mode", "warp_mode_name"))
        except Exception as e:
            self.log_message("Error setting audio clip warp: " + str(e))
            raise

    def _set_audio_clip_gain(self, track_index, clip_index, gain, arrangement=False):
        """Set Clip.gain, the raw LOM value in 0.0..1.0 (not dB).

        The dB Live shows for a raw value is reported back as
        gain_display_string.
        """
        try:
            if gain is None or isinstance(gain, bool) or not isinstance(gain, (int, float)):
                raise TypeError("gain must be a number between %s and %s, got %r"
                                % (AUDIO_CLIP_GAIN_RANGE + (gain,)))
            gain = float(gain)
            low, high = AUDIO_CLIP_GAIN_RANGE
            if gain != gain or gain < low or gain > high:
                raise ValueError("gain must be between %s and %s (raw Live value, not "
                                 "dB), got %r" % (low, high, gain))
            clip, where = self._resolve_audio_clip(track_index, clip_index, arrangement)
            previous = self._audio_clip_properties(clip)
            clip.gain = gain
            return self._audio_clip_change_report(
                track_index, clip_index, arrangement, clip, where, previous,
                ("gain", "gain_display_string"))
        except Exception as e:
            self.log_message("Error setting audio clip gain: " + str(e))
            raise

    def _set_audio_clip_pitch(self, track_index, clip_index, pitch_coarse=None,
                              pitch_fine=None, arrangement=False):
        """Set transposition: pitch_coarse in semitones, pitch_fine in cents."""
        try:
            if pitch_coarse is None and pitch_fine is None:
                raise ValueError("Give pitch_coarse and/or pitch_fine")
            coarse = fine = None
            if pitch_coarse is not None:
                if (isinstance(pitch_coarse, bool)
                        or not isinstance(pitch_coarse, (int, float))
                        or pitch_coarse != int(pitch_coarse)):
                    raise TypeError("pitch_coarse must be a whole number of semitones, "
                                    "got %r" % (pitch_coarse,))
                coarse = int(pitch_coarse)
                low, high = AUDIO_CLIP_PITCH_COARSE_RANGE
                if coarse < low or coarse > high:
                    raise ValueError("pitch_coarse must be between %d and %d semitones, "
                                     "got %d" % (low, high, coarse))
            if pitch_fine is not None:
                if isinstance(pitch_fine, bool) or not isinstance(pitch_fine, (int, float)):
                    raise TypeError("pitch_fine must be a number of cents, got %r"
                                    % (pitch_fine,))
                fine = float(pitch_fine)
                low, high = AUDIO_CLIP_PITCH_FINE_RANGE
                if fine != fine or fine < low or fine > high:
                    raise ValueError("pitch_fine must be between %s and %s cents, got %r"
                                     % (low, high, fine))
            clip, where = self._resolve_audio_clip(track_index, clip_index, arrangement)
            previous = self._audio_clip_properties(clip)
            if coarse is not None:
                clip.pitch_coarse = coarse
            if fine is not None:
                clip.pitch_fine = fine
            return self._audio_clip_change_report(
                track_index, clip_index, arrangement, clip, where, previous,
                ("pitch_coarse", "pitch_fine"))
        except Exception as e:
            self.log_message("Error setting audio clip pitch: " + str(e))
            raise

    def _set_tempo(self, tempo):
        """Set the tempo of the session"""
        try:
            self._song.tempo = tempo
            
            result = {
                "tempo": self._song.tempo
            }
            return result
        except Exception as e:
            self.log_message("Error setting tempo: " + str(e))
            raise
    
    def _fire_clip(self, track_index, clip_index):
        """Fire a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip_slot.fire()
            
            result = {
                "fired": True
            }
            return result
        except Exception as e:
            self.log_message("Error firing clip: " + str(e))
            raise
    
    def _stop_clip(self, track_index, clip_index):
        """Stop a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            clip_slot.stop()
            
            result = {
                "stopped": True
            }
            return result
        except Exception as e:
            self.log_message("Error stopping clip: " + str(e))
            raise

    def _delete_clip(self, track_index, clip_index):
        """Delete the clip in the given clip slot, freeing the slot for reuse."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                return {"deleted": False, "reason": "Clip slot was already empty"}

            clip_slot.delete_clip()

            return {"deleted": True}
        except Exception as e:
            self.log_message("Error deleting clip: " + str(e))
            raise

    def _delete_track(self, track_index, expected_name=None, track_type="track",
                      dry_run=True):
        """Preview or perform the deletion of one regular (Session) track.

        Guards, all enforced here so a direct TCP caller gets them too:
        - dry_run defaults to True; deleting requires dry_run to be False.
        - Only regular tracks (song.tracks) can be deleted. Return and master
          tracks are refused: song.delete_track cannot remove them, and a
          plain index would otherwise silently hit a regular track instead.
        - Deleting requires expected_name to equal the track's current name.
          Indices shift after every delete, so a remembered index is the
          realistic way to delete the wrong track.
        - The last remaining track is refused (Live needs at least one), and
          so is a deletion that would remove every track.
        - Deleting a group track also deletes its members; they are listed.

        Always returns the facts about the track and the track list that would
        remain (preview) or does remain (after deleting), re-indexed.
        """
        try:
            kind = (track_type or "track").lower()
            if kind in ("return", "master"):
                raise ValueError(
                    "Return and master tracks cannot be deleted with delete_track")
            if kind != "track":
                raise ValueError("Unknown track_type '%s' (expected track)" % track_type)
            if isinstance(track_index, bool) or not isinstance(track_index, int):
                raise TypeError("track_index must be an integer, got %r" % (track_index,))
            tracks = list(self._song.tracks)
            if track_index < 0 or track_index >= len(tracks):
                raise IndexError(
                    "track index %d out of range (have %d)" % (track_index, len(tracks)))
            track = tracks[track_index]
            if expected_name is not None and track.name != expected_name:
                raise ValueError(
                    "Track %d is '%s', not '%s'; indices may have shifted. "
                    "Nothing was deleted." % (track_index, track.name, expected_name))
            if not dry_run and expected_name is None:
                raise ValueError("expected_name is required to delete a track")

            # Group members go with their group (nested groups included).
            doomed = [track]
            for candidate in tracks:
                parent = getattr(candidate, "group_track", None)
                if (candidate not in doomed and parent is not None
                        and any(parent == d for d in doomed)):
                    doomed.append(candidate)
            members = [t.name for t in doomed[1:]]
            if len(doomed) >= len(tracks):
                raise ValueError(
                    "Refusing to delete the last remaining track; "
                    "a Live Set needs at least one")

            survivors = [t for t in tracks if not any(t == d for d in doomed)]
            info = {
                "track_index": track_index,
                "name": track.name,
                "is_group": bool(getattr(track, "is_foldable", False)),
                "type": ("group" if getattr(track, "is_foldable", False)
                         else "midi" if getattr(track, "has_midi_input", False)
                         else "audio"),
                "group_members": members,
                "devices": [d.name for d in track.devices],
                "session_clip_count": sum(1 for s in track.clip_slots if s.has_clip),
                "arrangement_clip_count": len(
                    self._safe_attr(track, "arrangement_clips", list, [])),
                "armed": self._safe_arm(track),
                "remaining": [{"index": i, "name": t.name}
                              for i, t in enumerate(survivors)],
            }
            if dry_run:
                info["deleted"] = False
                info["dry_run"] = True
                return info

            # The group first: on Live 12.4 Lite deleting the group takes its members
            # with it, while deleting the members one by one fails on the last one
            # ("Couldn't delete track.") and leaves the set half deleted. After each
            # delete the indices have moved, so every victim is re-found by identity
            # right before deleting it and skipped if it is already gone (a member that
            # went with its group). Never trust a stale index on a destructive call.
            try:
                for victim in doomed:
                    current = list(self._song.tracks)
                    at = next((i for i, t in enumerate(current) if t == victim), None)
                    if at is not None:
                        self._song.delete_track(at)
            except Exception as e:
                left = len(list(self._song.tracks))
                if left != len(tracks):
                    raise RuntimeError(
                        "Live stopped partway (%s): the set has %d of its %d tracks. Undo (Cmd+Z in "
                        "Live, or the undo tool after reading its warning) brings them back."
                        % (e, left, len(tracks)))
                raise
            after = list(self._song.tracks)
            info["deleted"] = len(after) == len(survivors)
            info["remaining"] = [{"index": i, "name": t.name}
                                 for i, t in enumerate(after)]
            if not info["deleted"]:
                raise RuntimeError(
                    "Live did not delete the track (%d tracks before, %d after)"
                    % (len(tracks), len(after)))
            return info
        except Exception as e:
            self.log_message("Error deleting track: " + str(e))
            raise


    # ── Session scenes ────────────────────────────────────────────────────────
    # Scenes are the rows of the Session view. Indices shift after every create,
    # duplicate and delete, so every reply carries the full, re-indexed list.
    # Adapted from ahujasid/ableton-mcp#99 (Zachary May): the same Live calls,
    # plus validation, verification that Live really acted (a Live Lite set
    # refuses extra scenes), and the guarded delete_scene.

    def _scene_clips(self, scene_index):
        """The clips in one scene row: [{"track": ..., "clip": ...}], in track order."""
        found = []
        for track in list(self._song.tracks):
            slots = track.clip_slots
            if scene_index >= len(slots):
                continue
            slot = slots[scene_index]
            if slot.has_clip:
                try:
                    clip_name = slot.clip.name
                except Exception:
                    clip_name = None
                found.append({"track": track.name, "clip": clip_name})
        return found

    def _scene_summary(self, index, scene):
        """One scene as a dict. tempo is -1 when the scene has no tempo of its own."""
        try:
            tempo = float(scene.tempo)
        except Exception:
            tempo = -1.0
        if tempo <= 0:
            tempo = -1.0
        return {
            "index": index,
            "name": scene.name,
            "tempo": tempo,
            "is_triggered": bool(self._safe_attr(scene, "is_triggered", bool, False)),
            "clip_count": len(self._scene_clips(index)),
        }

    def _scene_list(self):
        return [self._scene_summary(i, s)
                for i, s in enumerate(list(self._song.scenes))]

    def _resolve_scene(self, scene_index, what="scene_index"):
        """Validate a scene index and return (scene, scenes). Clear errors, no
        opaque TypeError from list indexing."""
        if isinstance(scene_index, bool) or not isinstance(scene_index, int):
            raise TypeError("%s must be an integer, got %r" % (what, scene_index))
        scenes = list(self._song.scenes)
        if scene_index < 0 or scene_index >= len(scenes):
            raise IndexError(
                "scene index %d out of range (have %d scenes, valid 0..%d)"
                % (scene_index, len(scenes), len(scenes) - 1))
        return scenes[scene_index], scenes

    def _scene_refused(self, action, count, error=None):
        """A readable reason for a scene change Live did not make."""
        reason = (": %s" % error) if error else ""
        return RuntimeError(
            "Live did not %s (the set has %d scenes)%s. If this is Live Lite, "
            "it limits how many scenes a set can have; delete one or use a "
            "full edition of Live." % (action, count, reason))

    def _new_scene_index(self, before, after, fallback):
        """Index of the one scene in `after` that was not in `before`, else fallback."""
        added = [i for i, s in enumerate(after)
                 if not any(s == b for b in before)]
        return added[0] if len(added) == 1 else fallback

    def _get_scenes(self):
        """List every Session scene: index, name, tempo (-1 = none), is_triggered, clip_count."""
        try:
            scenes = self._scene_list()
            return {"scene_count": len(scenes), "scenes": scenes}
        except Exception as e:
            self.log_message("Error getting scenes: " + str(e))
            raise

    def _create_scene(self, index=-1, name=""):
        """Create an empty scene at index (-1 or len = append) and optionally name it."""
        try:
            if isinstance(index, bool) or not isinstance(index, int):
                raise TypeError("index must be an integer, got %r" % (index,))
            if name is None:
                name = ""
            if not isinstance(name, _STRING_TYPES):
                raise TypeError("name must be a string, got %r" % (name,))
            before = list(self._song.scenes)
            if index < -1 or index > len(before):
                raise IndexError(
                    "scene index %d out of range (use -1 to append, or 0..%d)"
                    % (index, len(before)))
            try:
                self._song.create_scene(index)
            except Exception as e:
                raise self._scene_refused("create a scene", len(before), e)
            after = list(self._song.scenes)
            if len(after) != len(before) + 1:
                raise self._scene_refused("create a scene", len(after))
            new_index = self._new_scene_index(
                before, after, len(after) - 1 if index == -1 else index)
            if name:
                try:
                    after[new_index].name = name
                except Exception as e:
                    raise RuntimeError(
                        "Scene %d was created but could not be named: %s"
                        % (new_index, e))
            return {
                "created_index": new_index,
                "name": after[new_index].name,
                "scene_count": len(after),
                "scenes": self._scene_list(),
            }
        except Exception as e:
            self.log_message("Error creating scene: " + str(e))
            raise

    def _duplicate_scene(self, scene_index):
        """Duplicate a scene (clips included); the copy goes right after the original."""
        try:
            scene, before = self._resolve_scene(scene_index)
            try:
                self._song.duplicate_scene(scene_index)
            except Exception as e:
                raise self._scene_refused("duplicate the scene", len(before), e)
            after = list(self._song.scenes)
            if len(after) != len(before) + 1:
                raise self._scene_refused("duplicate the scene", len(after))
            new_index = self._new_scene_index(before, after, scene_index + 1)
            return {
                "source_index": scene_index,
                "new_index": new_index,
                "name": after[new_index].name,
                "scene_count": len(after),
                "scenes": self._scene_list(),
            }
        except Exception as e:
            self.log_message("Error duplicating scene: " + str(e))
            raise

    def _fire_scene(self, scene_index):
        """Launch every clip in a scene. AUDIBLE, and it takes the tracks that
        have a clip in the scene off the Arrangement until Back to Arrangement."""
        try:
            scene, _ = self._resolve_scene(scene_index)
            name = scene.name
            scene.fire()
            return {
                "fired": True,
                "index": scene_index,
                "name": name,
                "clip_count": len(self._scene_clips(scene_index)),
                "scenes": self._scene_list(),
            }
        except Exception as e:
            self.log_message("Error firing scene: " + str(e))
            raise

    def _set_scene_name(self, scene_index, name):
        """Rename a scene ('' restores Live's default look)."""
        try:
            if not isinstance(name, _STRING_TYPES):
                raise TypeError("name must be a string, got %r" % (name,))
            scene, _ = self._resolve_scene(scene_index)
            previous = scene.name
            scene.name = name
            return {
                "index": scene_index,
                "previous_name": previous,
                "name": scene.name,
                "scenes": self._scene_list(),
            }
        except Exception as e:
            self.log_message("Error setting scene name: " + str(e))
            raise

    def _delete_scene(self, scene_index, expected_name=None, dry_run=True):
        """Preview or perform the deletion of one scene (and the clips in it).

        Guards, all enforced here so a direct TCP caller gets them too:
        - dry_run defaults to True; deleting requires dry_run to be False.
        - Deleting requires expected_name (None is refused; '' is a valid name,
          Live's unnamed scenes) to equal the scene's current name. Indices
          shift after every create and delete, so a remembered index is the
          realistic way to delete the wrong scene. A mismatch is an error even
          in a preview.
        - The last remaining scene is refused (Live needs at least one).

        Always returns the facts about the scene (name, tempo, clips it holds)
        and the scene list that would remain (preview) or does remain (after
        deleting), re-indexed.
        """
        try:
            scene, scenes = self._resolve_scene(scene_index)
            if expected_name is not None and not isinstance(expected_name, _STRING_TYPES):
                raise TypeError("expected_name must be a string, got %r" % (expected_name,))
            if expected_name is not None and scene.name != expected_name:
                raise ValueError(
                    "Scene %d is '%s', not '%s'; indices may have shifted. "
                    "Nothing was deleted." % (scene_index, scene.name, expected_name))
            if not dry_run and expected_name is None:
                raise ValueError("expected_name is required to delete a scene")
            if len(scenes) <= 1:
                raise ValueError(
                    "Refusing to delete the last remaining scene; "
                    "a Live Set needs at least one")

            summary = self._scene_summary(scene_index, scene)
            info = {
                "scene_index": scene_index,
                "name": summary["name"],
                "tempo": summary["tempo"],
                "clip_count": summary["clip_count"],
                "clips": self._scene_clips(scene_index),
            }
            remaining = [self._scene_summary(i, s)
                         for i, s in enumerate(scenes) if i != scene_index]
            # Preview shows the post-delete numbering.
            for new_index, entry in enumerate(remaining):
                entry["index"] = new_index
            if dry_run:
                info["deleted"] = False
                info["dry_run"] = True
                info["remaining"] = remaining
                return info

            try:
                self._song.delete_scene(scene_index)
            except Exception as e:
                raise RuntimeError("Live did not delete the scene: %s" % e)
            after = list(self._song.scenes)
            info["deleted"] = (len(after) == len(scenes) - 1
                               and not any(scene == s for s in after))
            info["remaining"] = self._scene_list()
            if not info["deleted"]:
                raise RuntimeError(
                    "Live did not delete the scene (%d scenes before, %d after)"
                    % (len(scenes), len(after)))
            return info
        except Exception as e:
            self.log_message("Error deleting scene: " + str(e))
            raise

    def _stop_all_clips(self):
        """Ask Live to stop every playing Session clip (like the Stop All Clips button)."""
        try:
            self._song.stop_all_clips()
            return {"stop_requested": True}
        except Exception as e:
            self.log_message("Error stopping all clips: " + str(e))
            raise


    @staticmethod
    def _require_confirm_flag(confirm):
        """Return True only for an explicit boolean True.

        None means "not given" and previews. Any other non-boolean (the string
        "false", 0, 1) is ambiguous on a destructive call, so it is refused
        rather than guessed at.
        """
        if confirm is None:
            return False
        if not isinstance(confirm, bool):
            raise TypeError("confirm must be true or false, got %r" % (confirm,))
        return confirm

    @staticmethod
    def _require_expected_name(expected_name, what):
        if not isinstance(expected_name, str) or expected_name == "":
            raise ValueError(
                "expected_name is required (the %s's exact current name); "
                "read it first and pass it unchanged" % what)

    @staticmethod
    def _require_finite_number(value, label):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("%s must be a number of beats, got %r" % (label, value))
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            raise ValueError("%s must be a finite number of beats" % label)
        return value

    @staticmethod
    def _arrangement_clip_facts(index, clip):
        return {
            "index": index,
            "name": clip.name,
            "start_time": float(clip.start_time),
            "end_time": float(clip.end_time),
            "length": float(clip.length),
        }

    def _delete_arrangement_clips(self, track_index, expected_name, start_time,
                                  end_time, confirm=False):
        """Preview or perform the deletion of Arrangement clips on one track.

        Matching rule: a clip is selected when its START lies in
        [start_time, end_time) (start inclusive, end exclusive), in absolute
        Arrangement beats. A clip that starts before start_time but runs into
        the range is NOT selected, and neither is one that starts at end_time.

        Guards, all enforced here so a direct TCP caller gets them too:
        - confirm defaults to False: that only previews. Deleting needs
          confirm to be exactly True.
        - expected_name is required (preview and delete) and must equal the
          track's current name, which catches a stale track index.
        - Only regular tracks are accepted (song.tracks); group tracks hold no
          Arrangement clips of their own and are refused.
        - start_time and end_time must be finite numbers with start < end.
        - More than MAX_ARRANGEMENT_CLIPS_PER_DELETE matches is refused, and
          so is a match list where two clips share a start time (it should
          not happen, and a delete must never be ambiguous).
        - Track.delete_clip(clip) must exist in this Live version; if not, an
          error says so and nothing is deleted.

        Returns the clips that would be (or were) deleted and the track's
        remaining Arrangement clips, indexed as get_arrangement_clips does.
        """
        try:
            do_delete = self._require_confirm_flag(confirm)
            if isinstance(track_index, bool) or not isinstance(track_index, int):
                raise TypeError("track_index must be an integer, got %r" % (track_index,))
            self._require_expected_name(expected_name, "track")
            start = self._require_finite_number(start_time, "start_time")
            end = self._require_finite_number(end_time, "end_time")
            if start >= end:
                raise ValueError(
                    "start_time (%s) must be less than end_time (%s)" % (start, end))
            tracks = list(self._song.tracks)
            if track_index < 0 or track_index >= len(tracks):
                raise IndexError(
                    "track index %d out of range (have %d)" % (track_index, len(tracks)))
            track = tracks[track_index]
            if track.name != expected_name:
                raise ValueError(
                    "Track %d is '%s', not '%s'; indices may have shifted. "
                    "Nothing was deleted." % (track_index, track.name, expected_name))
            if getattr(track, "is_foldable", False):
                raise ValueError(
                    "Track '%s' is a group track and has no Arrangement clips "
                    "of its own; target the tracks inside it" % track.name)
            try:
                clips = list(track.arrangement_clips)
            except Exception as e:
                raise RuntimeError(
                    "Could not read Arrangement clips of track '%s': %s"
                    % (track.name, e))

            matched = [c for c in clips if start <= float(c.start_time) < end]
            if len(matched) > MAX_ARRANGEMENT_CLIPS_PER_DELETE:
                raise ValueError(
                    "%d clips start in [%s, %s); refusing more than %d at once. "
                    "Narrow the range. Nothing was deleted."
                    % (len(matched), start, end, MAX_ARRANGEMENT_CLIPS_PER_DELETE))
            starts = [float(c.start_time) for c in matched]
            if len(set(starts)) != len(starts):
                raise ValueError(
                    "Two matching clips share a start time; refusing an "
                    "ambiguous delete. Nothing was deleted.")

            delete_clip = getattr(track, "delete_clip", None)
            supported = callable(delete_clip)
            info = {
                "track_index": track_index,
                "track_name": track.name,
                "start_time": start,
                "end_time": end,
                "rule": "clips whose start lies in [start_time, end_time), in beats",
                "match_count": len(matched),
                "clips": [self._arrangement_clip_facts(i, c)
                          for i, c in enumerate(clips)
                          if any(c is m for m in matched)],
                "delete_supported": supported,
            }
            if not do_delete:
                info["deleted"] = False
                info["dry_run"] = True
                info["remaining"] = [self._arrangement_clip_facts(i, c)
                                     for i, c in enumerate(clips)
                                     if not any(c is m for m in matched)]
                return info
            if not supported:
                raise RuntimeError(
                    "Track.delete_clip is not available in this version of Live, "
                    "so Arrangement clips cannot be deleted through the API. "
                    "Nothing was deleted.")

            for clip in matched:
                delete_clip(clip)
            after = list(track.arrangement_clips)
            leftover = [c for c in after if start <= float(c.start_time) < end]
            info["deleted"] = not leftover
            info["dry_run"] = False
            info["deleted_count"] = len(clips) - len(after)
            info["remaining"] = [self._arrangement_clip_facts(i, c)
                                 for i, c in enumerate(after)]
            if leftover or len(after) != len(clips) - len(matched):
                raise RuntimeError(
                    "Live did not delete exactly the matched clips (%d clips "
                    "before, %d after, %d still start in the range); check "
                    "the Arrangement and use undo if needed"
                    % (len(clips), len(after), len(leftover)))
            return info
        except Exception as e:
            self.log_message("Error deleting arrangement clips: " + str(e))
            raise

    def _delete_device(self, track_index, device_index, expected_name,
                       expected_device_name, confirm=False, track_type="track"):
        """Preview or perform the deletion of one device from a track's chain.

        Guards, all enforced here so a direct TCP caller gets them too:
        - confirm defaults to False: that only previews. Deleting needs
          confirm to be exactly True.
        - track_type is "track" or "return"; the master track is refused.
        - expected_name (the track's name) and expected_device_name (the
          device's name) are both required, for preview as well as delete, and
          both must match the current state. A stale track or device index is
          the realistic way to delete the wrong thing.
        - device_index must be an integer inside the chain. Only devices at the
          top level of the track's chain are addressed, not devices nested in
          a rack's chains.
        - Track.delete_device(index) must exist, else an error says so.

        Returns the chain with the target marked (preview) or the remaining
        chain, re-indexed (after deleting).
        """
        try:
            do_delete = self._require_confirm_flag(confirm)
            kind = (track_type or "track").lower()
            if kind == "master":
                raise ValueError("delete_device does not support the master track")
            if kind not in ("track", "return"):
                raise ValueError(
                    "Unknown track_type '%s' (expected track or return)" % track_type)
            self._require_expected_name(expected_name, "track")
            if not isinstance(expected_device_name, str) or expected_device_name == "":
                raise ValueError(
                    "expected_device_name is required (the device's exact "
                    "current name in the chain); read it first and pass it unchanged")
            track = self._resolve_track(track_index, kind)
            if track.name != expected_name:
                raise ValueError(
                    "%s %s is '%s', not '%s'; indices may have shifted. "
                    "Nothing was deleted."
                    % (kind, track_index, track.name, expected_name))
            if isinstance(device_index, bool) or not isinstance(device_index, int):
                raise TypeError("device_index must be an integer, got %r" % (device_index,))
            devices = list(track.devices)
            if device_index < 0 or device_index >= len(devices):
                raise IndexError(
                    "device index %d out of range (track '%s' has %d devices)"
                    % (device_index, track.name, len(devices)))
            device = devices[device_index]
            if device.name != expected_device_name:
                raise ValueError(
                    "Device %d on '%s' is '%s', not '%s'; indices may have "
                    "shifted. Nothing was deleted."
                    % (device_index, track.name, device.name, expected_device_name))

            def chain(items, mark=None):
                return [{"index": i, "name": d.name,
                         "class_name": getattr(d, "class_name", None),
                         "to_delete": i == mark}
                        for i, d in enumerate(items)]

            delete_device = getattr(track, "delete_device", None)
            info = {
                "track_index": track_index,
                "track_type": kind,
                "track_name": track.name,
                "device_index": device_index,
                "device_name": device.name,
                "delete_supported": callable(delete_device),
                "chain": chain(devices, device_index),
            }
            if not do_delete:
                info["deleted"] = False
                info["dry_run"] = True
                return info
            if not callable(delete_device):
                raise RuntimeError(
                    "Track.delete_device is not available in this version of "
                    "Live. Nothing was deleted.")

            delete_device(device_index)
            after = list(track.devices)
            info["dry_run"] = False
            info["chain"] = chain(after)
            info["deleted"] = (len(after) == len(devices) - 1
                               and not any(d is device for d in after))
            if not info["deleted"]:
                raise RuntimeError(
                    "Live did not delete the device (%d devices before, %d "
                    "after); check the track and use undo if needed"
                    % (len(devices), len(after)))
            return info
        except Exception as e:
            self.log_message("Error deleting device: " + str(e))
            raise


    def _undo_redo(self, action, dry_run=True):
        """Undo or redo one step in Live's undo history, if there is one.

        DANGEROUS, so dry_run defaults to True (like delete_track): without
        dry_run=False nothing is changed and song.undo()/redo() is NOT called;
        the reply is a preview with UNDO_WARNING and can_undo / can_redo.

        Why: measured on Live 12 Lite, Live merges edits that come from the API
        into ONE undo step. Three Remote Script edits made 2 s apart
        (set_track_name, set_tempo, set_track_mute) were all reverted by a
        single undo(); another single undo() reverted every rename, track
        creation/deletion and mute made since the last human action. So one undo
        may revert several MCP changes and the user's own recent manual edits.

        Also guarded by Song.can_undo / Song.can_redo: with nothing to undo (or
        redo) nothing is called and the reply says so, instead of Live raising.
        """
        try:
            if action not in ("undo", "redo"):
                raise ValueError("Unknown action '%s'" % action)
            can = "can_" + action
            can_undo = bool(getattr(self._song, "can_undo", False))
            can_redo = bool(getattr(self._song, "can_redo", False))
            if not getattr(self._song, can, False):
                return {
                    "performed": False,
                    "dry_run": bool(dry_run),
                    "action": action,
                    "message": "Nothing to %s: Live's %s history is empty" % (action, action),
                    "can_undo": can_undo,
                    "can_redo": can_redo,
                }
            if dry_run:
                return {
                    "performed": False,
                    "dry_run": True,
                    "action": action,
                    "message": (
                        "PREVIEW ONLY, nothing was changed. " + UNDO_WARNING
                        + " Call %s again with confirm=true to go ahead." % action),
                    "warning": UNDO_WARNING,
                    "can_undo": can_undo,
                    "can_redo": can_redo,
                }
            getattr(self._song, action)()
            return {
                "performed": True,
                "dry_run": False,
                "action": action,
                "message": "Performed %s. %s" % (action, UNDO_WARNING),
                "warning": UNDO_WARNING,
                "can_undo": bool(getattr(self._song, "can_undo", False)),
                "can_redo": bool(getattr(self._song, "can_redo", False)),
            }
        except Exception as e:
            self.log_message("Error performing %s: %s" % (action, str(e)))
            raise

    def _start_playback(self):
        """Start playing the session"""
        try:
            self._song.start_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error starting playback: " + str(e))
            raise
    
    def _stop_playback(self):
        """Stop playing the session"""
        try:
            self._song.stop_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error stopping playback: " + str(e))
            raise
    
    # ── Arrangement view implementations ──────────────────────────────────────

    def _switch_to_arrangement_view(self):
        """Switch Ableton's main window to the Arrangement view"""
        try:
            self.application().view.show_view("Arranger")
            return {"view": "Arranger"}
        except Exception as e:
            self.log_message("Error switching to arrangement view: " + str(e))
            raise

    def _set_current_song_time(self, time_val):
        """Move the arrangement playhead to a position in beats"""
        try:
            requested = float(time_val)
            self._song.current_song_time = requested
            # Live applies the new position a moment later and reads the OLD one
            # back until then; the dispatcher settles and reads again
            # (_verify_song_time) before the reply goes out.
            return {"requested": requested, "current_song_time": requested}
        except Exception as e:
            self.log_message("Error setting current song time: " + str(e))
            raise

    def _get_arrangement_clips(self, track_index):
        """Return all clips placed in the Arrangement timeline for a track.

        Each clip dict contains:
          name, start_time, end_time, length, color,
          is_midi_clip, is_audio_clip, is_playing,
          extent, start_marker, end_marker, loop_start, loop_end, looping, has_envelopes
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]
            clips = []

            # track.arrangement_clips is available in Live 11 / 12
            for clip in track.arrangement_clips:
                clips.append({
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "color": clip.color,
                    "is_midi_clip": clip.is_midi_clip,
                    "is_audio_clip": clip.is_audio_clip,
                    "is_playing": clip.is_playing,
                    # extent is what the clip occupies on the timeline; length
                    # is the loop length. start_marker / loop_* say which part
                    # of the material plays (a trimmed head moves start_marker).
                    "extent": clip.end_time - clip.start_time,
                    "start_marker": getattr(clip, "start_marker", None),
                    "end_marker": getattr(clip, "end_marker", None),
                    "loop_start": getattr(clip, "loop_start", None),
                    "loop_end": getattr(clip, "loop_end", None),
                    "looping": getattr(clip, "looping", None),
                    "has_envelopes": getattr(clip, "has_envelopes", None),
                })

            return {
                "track_index": track_index,
                "track_name": track.name,
                "clip_count": len(clips),
                "clips": clips
            }
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _clear_notes_from_clip(self, track_index, clip_index, clip_start_time=None):
        """Remove all MIDI notes from a Session clip.

        Pairs with _add_notes_to_clip to make a real replace (clear, then add),
        which the write-only API otherwise can't do. Counts notes first so the
        result can report how many were removed.
        """
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)

            if not clip.is_midi_clip:
                raise Exception("Clip is not a MIDI clip; no notes to clear")

            length = clip.length

            # Count existing notes for the report (best-effort; never fatal).
            cleared = 0
            try:
                getter = getattr(clip, "get_notes_extended", None)
                if getter is not None:
                    cleared = len(list(getter(0, 128, 0.0, length)))
                else:
                    cleared = len(list(clip.get_notes(0.0, 0, length, 128)))
            except Exception:
                cleared = 0

            # Remove every note across the full pitch/time range. Prefer the
            # modern API (Live 11+); fall back to the legacy signature. Argument
            # order mirrors the get/remove _extended family:
            #   remove_notes_extended(from_pitch, pitch_span, from_time, time_span)
            # vs the legacy remove_notes(from_time, from_pitch, time_span, pitch_span).
            remover = getattr(clip, "remove_notes_extended", None)
            if remover is not None:
                remover(0, 128, 0.0, length)
            else:
                clip.remove_notes(0.0, 0, length, 128)

            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "cleared_count": cleared,
            }
        except Exception as e:
            self.log_message("Error clearing notes from clip: " + str(e))
            raise

    def _session_clip(self, track_index, clip_index, midi=False, clip_start_time=None):
        """Return (track, clip) for a Session clip slot, with strict checks.

        Indices must be real integers (a bool or float is an error rather than
        silently coerced). midi=True also requires a MIDI clip. With
        clip_start_time (beats) the clip is instead the Arrangement clip that
        starts there on that track, and clip_index is ignored: the note API
        works on Arrangement MIDI clips too (measured on Live 12.4 Lite).
        """
        if clip_start_time is not None:
            if isinstance(track_index, bool) or not isinstance(track_index, int):
                raise TypeError("track_index must be an integer, got %r" % (track_index,))
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if getattr(track, "is_foldable", False):
                raise ValueError("Track '%s' is a group track and has no Arrangement clips of its own"
                                 % track.name)
            clip = self._arr_find(track, self._require_finite_number(clip_start_time, "clip_start_time"))
            if midi and not getattr(clip, "is_midi_clip", False):
                raise Exception("Clip is not a MIDI clip")
            return track, clip
        for label, value in (("track_index", track_index), ("clip_index", clip_index)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("%s must be an integer, got %r" % (label, value))
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise Exception("No clip in slot")
        clip = slot.clip
        if midi and not getattr(clip, "is_midi_clip", False):
            raise Exception("Clip is not a MIDI clip")
        return track, clip

    def _note_summary(self, note):
        """Plain dict of one note: a Live MidiNote object or a legacy tuple."""
        if isinstance(note, (tuple, list)):
            return {"pitch": int(note[0]), "start_time": float(note[1]),
                    "duration": float(note[2]), "velocity": float(note[3]),
                    "mute": bool(note[4]) if len(note) > 4 else False}
        entry = {
            "pitch": int(getattr(note, "pitch", 0)),
            "start_time": float(getattr(note, "start_time", 0.0)),
            "duration": float(getattr(note, "duration", 0.0)),
            "velocity": float(getattr(note, "velocity", 0)),
            "mute": bool(getattr(note, "mute", False)),
        }
        if hasattr(note, "note_id"):
            try:
                entry["note_id"] = int(note.note_id)
            except Exception:
                pass
        return entry

    def _note_fields(self, note):
        """_note_summary plus the Live 11+ fields (probability, ...) when the note has them."""
        entry = self._note_summary(note)
        for field in NOTE_EXTENDED_FIELDS:
            if hasattr(note, field):
                entry[field] = float(getattr(note, field))
        return entry

    def _notes_in_range(self, clip, from_time, time_span, from_pitch, pitch_span):
        """Notes inside a time/pitch window, as plain dicts.

        Uses get_notes_extended (Live 11+; argument order from_pitch,
        pitch_span, from_time, time_span, as in _notes_from_clip) and falls
        back to the legacy get_notes(from_time, from_pitch, time_span,
        pitch_span), which carries no note_id.
        """
        getter = getattr(clip, "get_notes_extended", None)
        if getter is not None:
            raw = getter(from_pitch, pitch_span, from_time, time_span)
        else:
            raw = clip.get_notes(from_time, from_pitch, time_span, pitch_span)
        return [self._note_summary(n) for n in raw]

    def _get_clip_info(self, track_index, clip_index, clip_start_time=None):
        """Read-only facts about one Session clip (MIDI or audio)."""
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            is_midi = bool(getattr(clip, "is_midi_clip", False))
            info = {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": self._safe_attr(clip, "name", str, ""),
                "length": self._safe_attr(clip, "length", float, None),
                "is_midi_clip": is_midi,
                "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
                "is_playing": bool(self._safe_attr(clip, "is_playing", bool, False)),
                "looping": bool(self._safe_attr(clip, "looping", bool, False)),
                "loop_start": self._safe_attr(clip, "loop_start", float, None),
                "loop_end": self._safe_attr(clip, "loop_end", float, None),
                "start_marker": self._safe_attr(clip, "start_marker", float, None),
                "end_marker": self._safe_attr(clip, "end_marker", float, None),
                "muted": self._safe_attr(clip, "muted", bool, None),
                "color_index": self._safe_attr(clip, "color_index", int, None),
                "note_count": None,
            }
            if clip_start_time is None:
                info.update(self._clip_launch_state(clip))
            if is_midi and info["length"] is not None:
                try:
                    info["note_count"] = len(self._notes_in_range(
                        clip, 0.0, info["length"] + 1.0, 0, 128))
                except Exception as e:
                    self.log_message("get_clip_info note count failed: " + str(e))
            return info
        except Exception as e:
            self.log_message("Error getting clip info: " + str(e))
            raise

    def _loop_state(self, clip):
        return {
            "loop_start": self._safe_attr(clip, "loop_start", float, None),
            "loop_end": self._safe_attr(clip, "loop_end", float, None),
            "looping": self._safe_attr(clip, "looping", bool, None),
            "start_marker": self._safe_attr(clip, "start_marker", float, None),
            "end_marker": self._safe_attr(clip, "end_marker", float, None),
        }

    def _write_loop_points(self, clip, loop_start, loop_end):
        """Move the loop to [loop_start, loop_end] without an invalid step.

        Live rejects a loop whose start is not before its end, even for the
        instant between the two assignments. Writing loop_end first is valid
        whenever the CURRENT start is before the NEW end (growing, or moving
        the loop later); otherwise the new end is at or before the current
        start, so the new start (which is before the new end) must go first.
        At least one of the two orders is always valid because the current
        loop has start < end. Unchanged values are not rewritten.
        """
        current_start = float(clip.loop_start)
        current_end = float(clip.loop_end)
        steps = [("loop_end", loop_end, current_end),
                 ("loop_start", loop_start, current_start)]
        if current_start >= loop_end:
            steps.reverse()
        for name, value, current in steps:
            if value != current:
                setattr(clip, name, value)

    def _set_clip_loop(self, track_index, clip_index, loop_start, loop_end,
                       looping=None):
        """Set a Session clip's loop range (beats) and optionally looping.

        Validates start < end, writes the two markers in an order Live accepts
        (see _write_loop_points), then reads everything back. If Live did not
        keep a value, the previous loop is restored and an error is raised, so
        a reported success always means the clip now has that loop. Notes are
        never touched.
        """
        try:
            start = _finite_number(loop_start, "loop_start")
            end = _finite_number(loop_end, "loop_end")
            if start < 0:
                raise ValueError("loop_start must be >= 0, got %r" % (loop_start,))
            if start >= end:
                raise ValueError(
                    "loop_start (%r) must be before loop_end (%r)" % (loop_start, loop_end))
            if looping is not None and not isinstance(looping, bool):
                raise TypeError("looping must be true, false or omitted, got %r" % (looping,))
            track, clip = self._session_clip(track_index, clip_index)

            before = self._loop_state(clip)
            try:
                self._write_loop_points(clip, start, end)
                if looping is not None:
                    clip.looping = looping
                after = self._loop_state(clip)
                problems = []
                if (after["loop_start"] is None
                        or abs(after["loop_start"] - start) > 1e-6):
                    problems.append("loop_start is %r, wanted %r"
                                    % (after["loop_start"], start))
                if after["loop_end"] is None or abs(after["loop_end"] - end) > 1e-6:
                    problems.append("loop_end is %r, wanted %r"
                                    % (after["loop_end"], end))
                if looping is not None and after["looping"] != looping:
                    problems.append("looping is %r, wanted %r"
                                    % (after["looping"], looping))
                if problems:
                    raise RuntimeError("; ".join(problems))
            except Exception as failure:
                restored = True
                try:
                    if before["loop_start"] is not None and before["loop_end"] is not None:
                        self._write_loop_points(
                            clip, before["loop_start"], before["loop_end"])
                    if looping is not None and before["looping"] is not None:
                        clip.looping = before["looping"]
                except Exception as restore_failure:
                    restored = False
                    self.log_message("set_clip_loop restore failed: " + str(restore_failure))
                raise RuntimeError(
                    "Live did not accept the loop (%s). %s" % (
                        failure,
                        "The previous loop was restored." if restored
                        else "Restoring the previous loop ALSO failed; check the clip."))
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "before": before,
                "after": after,
            }
        except Exception as e:
            self.log_message("Error setting clip loop: " + str(e))
            raise

    def _remove_notes_from_clip(self, track_index, clip_index, from_time, time_span,
                                from_pitch, pitch_span, dry_run=True, clip_start_time=None):
        """Preview or perform removal of the notes in a time/pitch window.

        Every window parameter is required: there is no default that clears the
        clip by accident (use clear_notes_from_clip for that, on purpose).
        dry_run defaults to True and only reports the count and a sample of
        the notes the window selects, using the very query the removal uses,
        so the preview and the removal agree. Removing re-queries the window
        afterwards and raises if notes are still there.
        """
        try:
            start = _finite_number(from_time, "from_time")
            span = _finite_number(time_span, "time_span")
            if start < 0:
                raise ValueError("from_time must be >= 0, got %r" % (from_time,))
            if span <= 0:
                raise ValueError("time_span must be > 0, got %r" % (time_span,))
            low = _midi_int(from_pitch, "from_pitch", 0, 127)
            pitches = _midi_int(pitch_span, "pitch_span", 1, 128)
            if low + pitches > 128:
                raise ValueError(
                    "from_pitch + pitch_span must be <= 128, got %d" % (low + pitches))
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)

            window = {"from_time": start, "time_span": span,
                      "from_pitch": low, "pitch_span": pitches}
            doomed = self._notes_in_range(clip, start, span, low, pitches)
            doomed.sort(key=lambda n: (n["start_time"], n["pitch"]))
            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "window": window,
                "matched_count": len(doomed),
                "sample": doomed[:NOTE_SAMPLE_SIZE],
                "sample_truncated": len(doomed) > NOTE_SAMPLE_SIZE,
            }
            if dry_run:
                result["removed"] = False
                result["dry_run"] = True
                return result
            if not doomed:
                result["removed"] = False
                result["removed_count"] = 0
                result["dry_run"] = False
                return result

            # Argument order: remove_notes_extended(from_pitch, pitch_span,
            # from_time, time_span) vs the legacy remove_notes(from_time,
            # from_pitch, time_span, pitch_span); same as _clear_notes_from_clip.
            remover = getattr(clip, "remove_notes_extended", None)
            if remover is not None:
                remover(low, pitches, start, span)
            else:
                clip.remove_notes(start, low, span, pitches)

            left = self._notes_in_range(clip, start, span, low, pitches)
            result["removed_count"] = len(doomed) - len(left)
            result["remaining_in_window"] = len(left)
            result["removed"] = len(left) == 0
            result["dry_run"] = False
            if left:
                raise RuntimeError(
                    "Removed %d of %d notes; %d are still in the window"
                    % (result["removed_count"], len(doomed), len(left)))
            return result
        except Exception as e:
            self.log_message("Error removing notes from clip: " + str(e))
            raise

    def _validated_note_edits(self, notes):
        """Validate apply_note_modifications input. Returns {note_id: {field: value}}."""
        if not isinstance(notes, (list, tuple)) or not notes:
            raise ValueError("notes must be a non-empty list of {note_id, ...changes}")
        edits = {}
        for position, entry in enumerate(notes):
            label = "notes[%d]" % position
            if not isinstance(entry, dict):
                raise TypeError("%s must be an object, got %r" % (label, entry))
            unknown = sorted(set(entry) - set(NOTE_EDIT_FIELDS) - set(NOTE_EXTENDED_FIELDS)
                             - set(["note_id"]))
            if unknown:
                raise ValueError(
                    "%s has unknown field(s) %s; allowed: note_id, %s"
                    % (label, ", ".join(unknown),
                       ", ".join(NOTE_EDIT_FIELDS + NOTE_EXTENDED_FIELDS)))
            if "note_id" not in entry:
                raise ValueError("%s needs a note_id (from get_clip_notes)" % label)
            note_id = entry["note_id"]
            if isinstance(note_id, bool) or not isinstance(note_id, int):
                raise TypeError("%s.note_id must be an integer, got %r" % (label, note_id))
            if note_id in edits:
                raise ValueError("note_id %d appears more than once" % note_id)
            changes = {}
            if "pitch" in entry:
                changes["pitch"] = _midi_int(entry["pitch"], label + ".pitch", 0, 127)
            if "start_time" in entry:
                changes["start_time"] = _finite_number(entry["start_time"], label + ".start_time")
                if changes["start_time"] < 0:
                    raise ValueError("%s.start_time must be >= 0" % label)
            if "duration" in entry:
                changes["duration"] = _finite_number(entry["duration"], label + ".duration")
                if changes["duration"] <= 0:
                    raise ValueError("%s.duration must be > 0" % label)
            if "velocity" in entry:
                changes["velocity"] = _finite_number(entry["velocity"], label + ".velocity")
                if changes["velocity"] < 1 or changes["velocity"] > 127:
                    raise ValueError("%s.velocity must be between 1 and 127" % label)
            if "mute" in entry:
                if not isinstance(entry["mute"], bool):
                    raise TypeError("%s.mute must be true or false" % label)
                changes["mute"] = entry["mute"]
            for field, low, high in (("probability", 0.0, 1.0), ("velocity_deviation", -127.0, 127.0),
                                     ("release_velocity", 0.0, 127.0)):
                if field in entry:
                    changes[field] = _finite_number(entry[field], "%s.%s" % (label, field))
                    if changes[field] < low or changes[field] > high:
                        raise ValueError("%s.%s must be between %s and %s" % (label, field, low, high))
            if not changes:
                raise ValueError(
                    "%s changes nothing; give at least one of %s"
                    % (label, ", ".join(NOTE_EDIT_FIELDS)))
            edits[note_id] = changes
        return edits

    def _apply_note_modifications(self, track_index, clip_index, notes, dry_run=True,
                                  clip_start_time=None):
        """Preview or perform in-place edits of EXISTING notes, by note_id.

        notes: [{"note_id": 12, "pitch": 62, "velocity": 90, ...}, ...] with
        ids as returned by get_clip_notes. Only the listed fields change;
        everything else about the note (including its id) stays. Unknown ids
        are an error and nothing is changed. This rewrites notes, so it
        previews (before and proposed after) unless dry_run is explicitly
        false. Needs Live 11+ (get_notes_extended / apply_note_modifications).

        Only the notes that actually change are handed to Live. After applying,
        the notes are read back by id and compared with what was asked.
        """
        try:
            edits = self._validated_note_edits(notes)
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)
            getter = getattr(clip, "get_notes_extended", None)
            applier = getattr(clip, "apply_note_modifications", None)
            if getter is None or applier is None:
                raise Exception(
                    "This version of Live cannot edit notes in place "
                    "(needs Clip.get_notes_extended / apply_note_modifications, Live 11+)")

            latest_end = max([float(clip.length)] + [
                c["start_time"] + c.get("duration", 0.0) for c in edits.values()
                if "start_time" in c])
            read_span = latest_end + 1.0
            live_notes = list(getter(0, 128, 0.0, read_span))   # plain list: for reading only
            by_id = {}
            for note in live_notes:
                note_id = getattr(note, "note_id", None)
                if note_id is not None:
                    by_id[int(note_id)] = note
            missing = sorted(set(edits) - set(by_id))
            if missing:
                raise ValueError(
                    "Unknown note_id(s) %s in this clip. Read the current ids with "
                    "get_clip_notes (they change when notes are added or removed). "
                    "Nothing was changed." % ", ".join(str(m) for m in missing))

            changes = []
            unchanged = []
            to_apply = []
            for note_id in sorted(edits):
                note = by_id[note_id]
                before = self._note_fields(note)
                after = dict(before)
                for field, value in edits[note_id].items():
                    if field in NOTE_EXTENDED_FIELDS and field not in before:
                        raise ValueError(
                            "This version of Live does not give notes a '%s' field" % field)
                    after[field] = value
                if all(before[f] == after[f] for f in before):
                    unchanged.append(note_id)
                    continue
                changes.append({"note_id": note_id, "before": before, "after": after})
                to_apply.append(note)

            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "changed_count": len(changes),
                "unchanged_note_ids": unchanged,
                "changes": changes,
            }
            if dry_run:
                result["applied"] = False
                result["dry_run"] = True
                return result
            result["dry_run"] = False
            if not changes:
                result["applied"] = False
                return result

            method = self._apply_modified_notes(clip, applier, to_apply, live_notes, changes)
            result["method"] = method

            reread = {}
            reread_notes = list(getter(0, 128, 0.0, read_span))
            for note in reread_notes:
                note_id = getattr(note, "note_id", None)
                if note_id is not None:
                    reread[int(note_id)] = self._note_fields(note)
            if method.startswith("remove + set_notes"):
                # Live gave the re-added notes new ids: find each edit by its values.
                reread = {}
                summaries = [self._note_summary(n) for n in reread_notes]
                for change in changes:
                    wanted = change["after"]
                    for summary in summaries:
                        if (summary["pitch"] == wanted["pitch"]
                                and abs(summary["start_time"] - wanted["start_time"]) <= 1e-6):
                            reread[change["note_id"]] = summary
                            break
                result["note_ids_changed"] = True
            mismatches = []
            for change in changes:
                actual = reread.get(change["note_id"])
                if actual is None:
                    mismatches.append("note %d is no longer in the clip" % change["note_id"])
                    change["after"] = None
                    continue
                for field in change["after"]:
                    if field == "note_id" or field not in actual:
                        continue
                    wanted = change["after"][field]
                    got = actual[field]
                    same = (got == wanted if field in ("mute", "pitch")
                            else abs(float(got) - float(wanted)) <= 1e-6)
                    if not same:
                        mismatches.append("note %d %s is %r, wanted %r"
                                          % (change["note_id"], field, got, wanted))
                change["after"] = actual
            result["applied"] = True
            result["verified"] = not mismatches
            if mismatches:
                result["mismatches"] = mismatches
            return result
        except Exception as e:
            self.log_message("Error applying note modifications: " + str(e))
            raise

    @staticmethod
    def _set_note_fields(note, change):
        for field, value in change["after"].items():
            if field == "note_id" or field not in change["before"]:
                continue
            if change["after"][field] != change["before"][field]:
                setattr(note, field, value)

    def _apply_modified_notes(self, clip, applier, to_apply, live_notes, changes):
        """Hand edited notes to Live and return the method that worked.

        Live's Clip.apply_note_modifications only accepts the MidiNoteVector that
        get_notes_by_id / get_notes_extended return: a Python list or tuple of the
        very same notes is refused with "did not match C++ signature" (found on
        Live 12 Lite, 2026-10-24; before that this fell back to remove + set_notes,
        which changes note ids). So: edit the notes of a fresh get_notes_by_id
        vector in place and apply that vector. The older shapes stay as fallbacks,
        ending in remove + set_notes (which drops probability and the note id).
        """
        errors = []
        by_id_getter = getattr(clip, "get_notes_by_id", None)
        if by_id_getter is not None:
            try:
                wanted = dict((c["note_id"], c) for c in changes)
                vector = by_id_getter([c["note_id"] for c in changes])
                for note in vector:
                    change = wanted.get(int(note.note_id))
                    if change is not None:
                        self._set_note_fields(note, change)
                applier(vector)
                return "in place"
            except Exception as e:
                errors.append("in place: %s" % str(e).replace("\n", " ")[:160])
                self.log_message("apply_note_modifications in place failed: %s" % e)
        for change, note in zip(changes, to_apply):
            self._set_note_fields(note, change)
        for label, argument in (("edited list", list(to_apply)),
                                ("edited tuple", tuple(to_apply)),
                                ("all notes tuple", tuple(live_notes))):
            try:
                applier(argument)
                return label
            except Exception as e:
                errors.append("%s: %s" % (label, str(e).replace("\n", " ")[:160]))
                self.log_message("apply_note_modifications with %s failed: %s" % (label, e))
        remover = getattr(clip, "remove_notes_extended", None)
        if remover is None or not hasattr(clip, "set_notes"):
            raise Exception("Live rejected every way of applying the note edits: " + " | ".join(errors))
        for change in changes:
            before = change["before"]
            remover(before["pitch"], 1, before["start_time"] - 1e-4, 2e-4)
        clip.set_notes(tuple(
            (c["after"]["pitch"], c["after"]["start_time"], c["after"]["duration"],
             c["after"]["velocity"], c["after"]["mute"]) for c in changes))
        return "remove + set_notes (extra note fields reset)"

    def _quantize_clip(self, track_index, clip_index, grid, amount=1.0, dry_run=True,
                       clip_start_time=None):
        """Preview or perform Clip.quantize on a Session MIDI clip.

        grid: one of QUANTIZE_GRIDS (1/4, 1/8, 1/8T, 1/16, 1/16T, 1/32).
        amount: 0..1, how far each note start moves toward the grid (1 = onto it).
        This REWRITES note start times for the whole clip, so it previews
        unless dry_run is explicitly false. The preview computes where each
        start would land (an estimate: Live does the real rounding); the
        applied result reports the before and after read back from Live.
        """
        try:
            if not isinstance(grid, str):
                raise TypeError("grid must be one of %s, got %r"
                                % (", ".join(sorted(QUANTIZE_GRIDS)), grid))
            key = grid.strip().upper()
            if key not in QUANTIZE_GRIDS:
                raise ValueError("Unknown grid %r; use one of %s"
                                 % (grid, ", ".join(sorted(QUANTIZE_GRIDS))))
            ratio = _finite_number(amount, "amount")
            if ratio < 0 or ratio > 1:
                raise ValueError("amount must be between 0 and 1, got %r" % (amount,))
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)
            if not callable(getattr(clip, "quantize", None)):
                raise Exception("This clip cannot be quantized (Clip.quantize is unavailable)")
            enum_value, size = QUANTIZE_GRIDS[key]

            span = float(clip.length) + 1.0
            notes = self._notes_in_range(clip, 0.0, span, 0, 128)
            notes.sort(key=lambda n: (n["start_time"], n["pitch"]))
            result = {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "grid": key,
                "grid_beats": size,
                "amount": ratio,
                "note_count": len(notes),
            }

            def label(n):
                return n.get("note_id", "%d@%g" % (n["pitch"], n["start_time"]))

            if dry_run:
                moves = []
                for n in notes:
                    target = round(n["start_time"] / size) * size
                    landing = n["start_time"] + ratio * (target - n["start_time"])
                    if abs(landing - n["start_time"]) > 1e-6:
                        moves.append({"note": label(n), "pitch": n["pitch"],
                                      "start_before": n["start_time"],
                                      "start_estimated_after": landing})
                result["dry_run"] = True
                result["applied"] = False
                result["estimated_moved_count"] = len(moves)
                result["sample"] = moves[:NOTE_SAMPLE_SIZE]
                result["sample_truncated"] = len(moves) > NOTE_SAMPLE_SIZE
                result["estimate_note"] = (
                    "Estimated from the grid; Live does the real rounding. "
                    "Note starts change; durations are Live's to adjust.")
                return result

            result["dry_run"] = False
            if not notes or ratio == 0:
                result["applied"] = False
                result["moved_count"] = 0
                return result
            clip.quantize(enum_value, ratio)
            after = self._notes_in_range(clip, 0.0, span, 0, 128)
            before_by = dict((label(n), n) for n in notes)
            moves = []
            for n in after:
                old = before_by.get(label(n))
                if old is not None and abs(old["start_time"] - n["start_time"]) > 1e-6:
                    moves.append({"note": label(n), "pitch": n["pitch"],
                                  "start_before": old["start_time"],
                                  "start_after": n["start_time"]})
            moves.sort(key=lambda m: (m["start_before"], m["pitch"]))
            result["applied"] = True
            result["moved_count"] = len(moves)
            result["note_count_after"] = len(after)
            result["sample"] = moves[:NOTE_SAMPLE_SIZE]
            result["sample_truncated"] = len(moves) > NOTE_SAMPLE_SIZE
            return result
        except Exception as e:
            self.log_message("Error quantizing clip: " + str(e))
            raise

    def _duplicate_session_clip_to_arrangement(self, track_index, clip_index, destination_time):
        """Copy a Session-view clip into the Arrangement timeline.

        Uses the real Live API:
          track.duplicate_clip_to_arrangement(clip, destination_time)

        Available in Live 11 / 12.  destination_time is in beats from the
        start of the arrangement.
        """
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")

            track = self._song.tracks[track_index]

            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip slot index out of range")

            clip_slot = track.clip_slots[clip_index]

            if not clip_slot.has_clip:
                raise Exception(
                    "No clip in slot " + str(clip_index) +
                    " on track " + str(track_index)
                )

            clip = clip_slot.clip

            # Duplicate to arrangement at the requested beat position
            track.duplicate_clip_to_arrangement(clip, float(destination_time))

            return {
                "success": True,
                "track_index": track_index,
                "track_name": track.name,
                "clip_name": clip.name,
                "destination_time": destination_time
            }
        except Exception as e:
            self.log_message("Error duplicating clip to arrangement: " + str(e))
            raise

    # Seconds to wait after writing Song.current_song_time before toggling the
    # cue. Live applies the new position one tick later, and Song.set_or_delete_cue
    # uses the position that is already applied (measured on Live 12 Lite,
    # 2026-10-23: toggling in the same tick put the cue at the OLD playhead and
    # deleted a locator that was there).
    LOCATOR_SETTLE_SECONDS = 0.4

    def _create_locator(self, name, time_val):
        """Create (or rename) a named locator at the given beat position.

        Runs on the socket thread in steps, with each Live call on the main
        thread: move the playhead, wait for Live to apply it, toggle the cue,
        read it back, then put the playhead back. If a cue already exists at
        the time it is only renamed (toggling would delete it). Refused while
        the transport is playing, because the playhead moves during the wait.
        """
        target_time = float(time_val)
        if not math.isfinite(target_time) or target_time < 0:
            raise ValueError("time must be a number of beats >= 0")
        tolerance = 1e-3
        settle = self.LOCATOR_SETTLE_SECONDS

        def find_cue():
            for cue in self._song.cue_points:
                if abs(cue.time - target_time) < tolerance:
                    return cue
            return None

        def prepare():
            song = self._song
            existing = find_cue()
            if existing is not None:
                return {"existing": True, "original": song.current_song_time}
            if song.is_playing:
                raise Exception(
                    "Stop playback before creating a locator: the playhead has to be "
                    "moved to the locator time and it would keep running")
            before = [c.time for c in song.cue_points]
            original = song.current_song_time
            song.current_song_time = target_time
            return {"existing": False, "original": original, "before": before}

        def toggle():
            # No read-back guard here: current_song_time reads back the value
            # that was just written even while Live has not applied it yet.
            self._song.set_or_delete_cue()

        try:
            state = self._call_on_main_thread(prepare)
            if not state["existing"]:
                time.sleep(settle)
                self._call_on_main_thread(toggle)
                time.sleep(settle)

            def new_cue():
                known = state.get("before", [])
                for candidate in self._song.cue_points:
                    if not any(abs(candidate.time - t) < tolerance for t in known):
                        return candidate
                return None

            def inspect():
                cue = find_cue()
                if cue is None and not state["existing"]:
                    # Song.set_or_delete_cue puts the cue on a whole beat, so a
                    # fractional time lands up to one beat earlier.
                    candidate = new_cue()
                    if candidate is not None and abs(candidate.time - target_time) < 1.0:
                        cue = candidate
                return cue, new_cue()

            cue, created = self._call_on_main_thread(inspect)
            if cue is None and created is not None:
                # A cue appeared somewhere else: Live toggled at the old playhead.
                # Live has moved the playhead onto it, so toggling again removes it.
                stray = created.time
                self._call_on_main_thread(
                    lambda: setattr(self._song, "current_song_time", stray))
                time.sleep(settle)
                self._call_on_main_thread(self._song.set_or_delete_cue)
                time.sleep(settle)

            def finish():
                song = self._song
                if not state["existing"]:
                    try:
                        song.current_song_time = state["original"]
                    except Exception:
                        pass
                if cue is None:
                    raise Exception(
                        "Failed to create a cue at beat %s: Live did not apply the playhead "
                        "move%s. The Set has %d cue point(s), it had %d."
                        % (target_time,
                           "; the stray cue it made at beat %s was removed" % created.time
                           if created is not None else "",
                           len(song.cue_points), len(state.get("before", []))))
                if name:
                    try:
                        cue.name = str(name)
                    except Exception as e:
                        self.log_message("Could not rename locator: " + str(e))
                reply = {"success": True, "time": cue.time, "name": cue.name,
                         "created": not state["existing"],
                         "cue_count": len(song.cue_points)}
                if abs(cue.time - target_time) >= tolerance:
                    reply["requested_time"] = target_time
                    reply["note"] = ("Live puts locators on whole beats: the cue is at beat %s, "
                                     "not %s" % (cue.time, target_time))
                return reply

            return self._call_on_main_thread(finish)
        except Exception as e:
            self.log_message("Error creating locator: " + str(e))
            raise

    def _delete_locator(self, time_val, expected_name, dry_run=True):
        """Preview or delete the locator at a beat position (guarded).

        Needs the locator's exact current name as a stale-index check. Deleting
        uses the same steps as create_locator: Song.set_or_delete_cue toggles at
        the playhead position Live has already applied, so the playhead is moved
        onto the cue, Live is given a moment, the cue is toggled off and the
        playhead is put back. Refused while the transport plays.
        """
        if time_val is None:
            raise ValueError("time is required: the beat of the locator to delete")
        target_time = float(time_val)
        if not math.isfinite(target_time) or target_time < 0:
            raise ValueError("time must be a number of beats >= 0")
        if expected_name is None:
            raise ValueError("expected_name is required: read it with get_cue_points "
                             "(locators have names like \"1\" until renamed)")
        tolerance = 1e-3
        settle = self.LOCATOR_SETTLE_SECONDS

        def listing(exclude=None):
            return [{"name": c.name, "time": c.time} for c in self._song.cue_points
                    if exclude is None or abs(c.time - exclude) >= tolerance]

        def find():
            for cue in self._song.cue_points:
                if abs(cue.time - target_time) < tolerance:
                    return cue
            return None

        def inspect():
            cue = find()
            if cue is None:
                raise Exception(
                    "No locator at beat %s. Locators are at: %s"
                    % (target_time, ", ".join("%s @ %s" % (c["name"], c["time"])
                                              for c in listing()) or "none"))
            if cue.name != expected_name:
                raise Exception(
                    "The locator at beat %s is '%s', not '%s'; nothing was deleted "
                    "(the index may be stale)." % (target_time, cue.name, expected_name))
            if not dry_run and self._song.is_playing:
                raise Exception("Stop playback before deleting a locator: the playhead "
                                "has to be moved onto it and it would keep running")
            return {"name": cue.name, "time": cue.time, "remaining": listing(cue.time)}

        try:
            info = self._call_on_main_thread(inspect)
            if dry_run:
                info.update({"deleted": False, "dry_run": True})
                return info

            def move():
                original = self._song.current_song_time
                self._song.current_song_time = info["time"]
                return original

            original = self._call_on_main_thread(move)
            time.sleep(settle)
            self._call_on_main_thread(self._song.set_or_delete_cue)
            time.sleep(settle)

            def finish():
                try:
                    self._song.current_song_time = original
                except Exception:
                    pass
                return find() is None, listing()

            gone, remaining = self._call_on_main_thread(finish)
            if not gone:
                raise Exception(
                    "The locator at beat %s is still there after the delete; "
                    "check get_cue_points." % target_time)
            info.update({"deleted": True, "dry_run": False, "remaining": remaining})
            return info
        except Exception as e:
            self.log_message("Error deleting locator: " + str(e))
            raise

    # ── Arrangement clip editing (clear / trim / split / move / create) ───────
    # Live's API has no setter for an Arrangement clip's start or end. What it
    # does have, measured on Live 12.4 Lite (2026-10-23): placing a clip over
    # others OVERWRITES them like a paste does (a tail is shortened, a head
    # starts later with its content offset kept, a middle splits the clip in
    # two); Track.duplicate_clip_to_arrangement accepts an Arrangement clip and
    # keeps its extent and content offset; Track.create_midi_clip(start, length)
    # makes a clip of exactly that length. So "erase a range" is: place a clip
    # over it and delete that clip. Trim, split and move are built from that.
    # Every edit runs in one main-thread task (measured to work without waits).

    ARRANGEMENT_EPSILON = 1e-3
    ARRANGEMENT_MIN_PIECE = 0.0625   # beats; shorter trims and splits are refused

    def _arr_track(self, track_index, expected_name):
        if isinstance(track_index, bool) or not isinstance(track_index, int):
            raise TypeError("track_index must be an integer, got %r" % (track_index,))
        self._require_expected_name(expected_name, "track")
        tracks = list(self._song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError(
                "track index %d out of range (have %d)" % (track_index, len(tracks)))
        track = tracks[track_index]
        if track.name != expected_name:
            raise ValueError(
                "Track %d is '%s', not '%s'; indices may have shifted. Nothing was changed."
                % (track_index, track.name, expected_name))
        if getattr(track, "is_foldable", False):
            raise ValueError(
                "Track '%s' is a group track and has no Arrangement clips of its own; "
                "target the tracks inside it" % track.name)
        for needed in ("arrangement_clips", "delete_clip", "duplicate_clip_to_arrangement"):
            if not hasattr(track, needed):
                raise RuntimeError(
                    "This version of Live has no Track.%s, so Arrangement clips cannot "
                    "be edited through the API. Nothing was changed." % needed)
        return track

    @staticmethod
    def _arr_clips(track):
        return sorted(track.arrangement_clips, key=lambda c: float(c.start_time))

    def _arr_facts(self, track):
        return [{"index": i, "name": c.name, "start_time": float(c.start_time),
                 "end_time": float(c.end_time),
                 "extent": float(c.end_time) - float(c.start_time)}
                for i, c in enumerate(self._arr_clips(track))]

    def _arr_find(self, track, start_time):
        eps = self.ARRANGEMENT_EPSILON
        clips = self._arr_clips(track)
        matches = [c for c in clips if abs(float(c.start_time) - start_time) < eps]
        if not matches:
            raise ValueError(
                "No Arrangement clip starts at beat %s on '%s'. Clips start at: %s"
                % (start_time, track.name,
                   ", ".join("%s" % float(c.start_time) for c in clips) or "none"))
        if len(matches) > 1:
            raise ValueError("Two clips start at beat %s; refusing an ambiguous edit" % start_time)
        return matches[0]

    def _arr_effects(self, track, start, end, ignore=None):
        """What overwriting [start, end) does to the clips already there."""
        eps = self.ARRANGEMENT_EPSILON
        effects = []
        for c in self._arr_clips(track):
            if c is ignore:
                continue
            cs, ce = float(c.start_time), float(c.end_time)
            if cs >= end - eps or ce <= start + eps:
                continue
            if cs >= start - eps and ce <= end + eps:
                effect = "removed"
            elif cs < start - eps and ce > end + eps:
                effect = "split in two"
            elif cs < start - eps:
                effect = "tail cut, now ends at %s" % start
            else:
                effect = "head cut, now starts at %s" % end
            effects.append({"name": c.name, "start_time": cs, "end_time": ce, "effect": effect})
        return effects

    def _arr_dup(self, track, clip, time_val):
        eps = self.ARRANGEMENT_EPSILON
        track.duplicate_clip_to_arrangement(clip, float(time_val))
        found = [c for c in track.arrangement_clips if abs(float(c.start_time) - time_val) < eps]
        if len(found) != 1:
            raise RuntimeError(
                "Expected one clip at beat %s after duplicating, found %d" % (time_val, len(found)))
        return found[0]

    def _arr_delete_at(self, track, start_time, name=None):
        eps = self.ARRANGEMENT_EPSILON
        for c in list(track.arrangement_clips):
            if abs(float(c.start_time) - start_time) < eps and (name is None or c.name == name):
                track.delete_clip(c)
                return True
        return False

    def _arr_scratch_time(self, track):
        ends = [float(c.end_time) for c in track.arrangement_clips]
        return float(math.ceil(max(ends + [0.0])) + 4)

    def _arr_eraser_wav(self):
        import tempfile
        import wave
        path = os.path.join(tempfile.gettempdir(), "ableton_mcp_eraser_60s.wav")
        if not os.path.isfile(path):
            w = wave.open(path, "wb")
            try:
                w.setnchannels(1)
                w.setsampwidth(1)
                w.setframerate(8000)
                w.writeframes(bytes([128]) * 8000 * 60)
            finally:
                w.close()
        return path

    def _arr_erase(self, track, start, end):
        """Remove whatever lies in [start, end) on this track.

        Clips that cross an edge are shortened (their content offset is kept),
        a clip that spans the whole range is split in two, a clip inside it is
        removed. Nothing outside the range changes.
        """
        length = end - start
        if length <= self.ARRANGEMENT_EPSILON:
            return
        if getattr(track, "has_midi_input", False):
            eraser = track.create_midi_clip(start, length)
            track.delete_clip(eraser)
            return
        slot = None
        for candidate in track.clip_slots:
            if not candidate.has_clip:
                slot = candidate
                break
        if slot is None:
            raise RuntimeError(
                "Editing Arrangement clips on an audio track needs one empty Session "
                "slot on it (a silent clip is placed there for a moment). Nothing was "
                "changed; clear a slot first.")
        path = self._arr_eraser_wav()
        slot.create_audio_clip(path)
        try:
            eraser = slot.clip
            limit = float(eraser.length)
            pieces = max(1, int(math.ceil(length / limit)))
            chunk = length / pieces
            eraser.loop_start = 0.0
            for i in range(pieces):
                eraser.loop_end = chunk
                at = start + i * chunk
                track.duplicate_clip_to_arrangement(eraser, at)
                for c in list(track.arrangement_clips):
                    if (abs(float(c.start_time) - at) < self.ARRANGEMENT_EPSILON
                            and getattr(c, "file_path", None) == path):
                        track.delete_clip(c)
                        break
        finally:
            slot.delete_clip()

    def _arr_info(self, track, track_index, do_apply, **extra):
        info = {"track_index": track_index, "track_name": track.name}
        info.update(extra)
        info["applied"] = False
        info["dry_run"] = not do_apply
        return info

    def _clear_arrangement_range(self, track_index, expected_name, start_time, end_time,
                                 confirm=False):
        """Preview or clear [start_time, end_time) on one Arrangement track.

        Clips crossing an edge are shortened, one spanning the range is split in
        two, ones inside are removed. DESTRUCTIVE: it previews unless confirm is
        exactly True. Clips are not moved to close the gap.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            track = self._arr_track(track_index, expected_name)
            start = self._require_finite_number(start_time, "start_time")
            end = self._require_finite_number(end_time, "end_time")
            if start < 0 or end - start < self.ARRANGEMENT_MIN_PIECE:
                raise ValueError("start_time must be >= 0 and the range at least %s beats"
                                 % self.ARRANGEMENT_MIN_PIECE)
            effects = self._arr_effects(track, start, end)
            info = self._arr_info(track, track_index, do_apply, start_time=start,
                                  end_time=end, affected=effects)
            if not do_apply:
                return info
            if effects:
                self._arr_erase(track, start, end)
            leftover = self._arr_effects(track, start, end)
            info["applied"] = True
            info["verified"] = not leftover
            info["clips"] = self._arr_facts(track)
            return info
        except Exception as e:
            self.log_message("Error clearing arrangement range: " + str(e))
            raise

    def _trim_arrangement_clip(self, track_index, expected_name, clip_start_time,
                               new_start_time=None, new_end_time=None, confirm=False):
        """Preview or shorten one Arrangement clip from its start and/or end.

        The clip is identified by its start beat. The content is kept (a later
        start keeps the content offset); only the audible extent shrinks. It
        cannot be lengthened. Touches nothing but this clip.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            track = self._arr_track(track_index, expected_name)
            clip_start = self._require_finite_number(clip_start_time, "clip_start_time")
            clip = self._arr_find(track, clip_start)
            s, e = float(clip.start_time), float(clip.end_time)
            if new_start_time is None and new_end_time is None:
                raise ValueError("Give new_start_time and/or new_end_time")
            ns = s if new_start_time is None else self._require_finite_number(
                new_start_time, "new_start_time")
            ne = e if new_end_time is None else self._require_finite_number(
                new_end_time, "new_end_time")
            eps = self.ARRANGEMENT_EPSILON
            if ns < s - eps or ne > e + eps:
                raise ValueError(
                    "A clip can only be shortened: it spans [%s, %s), so new_start_time "
                    "must be >= %s and new_end_time <= %s" % (s, e, s, e))
            if ne - ns < self.ARRANGEMENT_MIN_PIECE:
                raise ValueError("The trimmed clip would be shorter than %s beats"
                                 % self.ARRANGEMENT_MIN_PIECE)
            info = self._arr_info(track, track_index, do_apply, clip=clip.name,
                                  from_range=[s, e], to_range=[ns, ne])
            if not do_apply:
                return info
            name = clip.name
            if ns > s + eps:
                self._arr_erase(track, s, ns)
            if ne < e - eps:
                self._arr_erase(track, ne, e)
            found = [c for c in track.arrangement_clips
                     if abs(float(c.start_time) - ns) < eps and abs(float(c.end_time) - ne) < eps]
            info["applied"] = True
            info["verified"] = len(found) == 1
            info["clips"] = self._arr_facts(track)
            return info
        except Exception as e:
            self.log_message("Error trimming arrangement clip: " + str(e))
            raise

    def _split_arrangement_clip(self, track_index, expected_name, clip_start_time,
                                split_time, confirm=False):
        """Preview or split one Arrangement clip in two at a beat, with no gap.

        Both halves keep the content (the right half starts at the matching
        offset). Works through a scratch copy placed after the last clip on the
        track, removed again at the end, so no other clip is touched.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            track = self._arr_track(track_index, expected_name)
            clip_start = self._require_finite_number(clip_start_time, "clip_start_time")
            at = self._require_finite_number(split_time, "split_time")
            clip = self._arr_find(track, clip_start)
            s, e = float(clip.start_time), float(clip.end_time)
            piece = self.ARRANGEMENT_MIN_PIECE
            if at - s < piece or e - at < piece:
                raise ValueError(
                    "split_time must be at least %s beats inside the clip [%s, %s)"
                    % (piece, s, e))
            info = self._arr_info(track, track_index, do_apply, clip=clip.name,
                                  from_range=[s, e], to_ranges=[[s, at], [at, e]])
            if not do_apply:
                return info
            eps = self.ARRANGEMENT_EPSILON
            scratch = self._arr_scratch_time(track)
            d = at - s
            try:
                self._arr_dup(track, clip, scratch)                  # copy of the whole clip
                self._arr_erase(track, scratch, scratch + d)         # keep its right part
                self._arr_erase(track, at, e)                        # shorten the original
                remainder = [c for c in track.arrangement_clips
                             if abs(float(c.start_time) - (scratch + d)) < eps]
                if len(remainder) != 1:
                    raise RuntimeError("The scratch copy did not come out as expected")
                self._arr_dup(track, remainder[0], at)               # right part back in place
            finally:
                for c in list(track.arrangement_clips):
                    if float(c.start_time) >= scratch - eps:
                        track.delete_clip(c)
            left = [c for c in track.arrangement_clips
                    if abs(float(c.start_time) - s) < eps and abs(float(c.end_time) - at) < eps]
            right = [c for c in track.arrangement_clips
                     if abs(float(c.start_time) - at) < eps and abs(float(c.end_time) - e) < eps]
            info["applied"] = True
            info["verified"] = len(left) == 1 and len(right) == 1
            info["clips"] = self._arr_facts(track)
            return info
        except Exception as e:
            self.log_message("Error splitting arrangement clip: " + str(e))
            raise

    def _move_arrangement_clip(self, track_index, expected_name, clip_start_time,
                               new_start_time=None, copy=False, confirm=False,
                               to_track_index=None, to_expected_name=None):
        """Preview or move (or copy) one Arrangement clip, on its own track or to another.

        The clip keeps its length, content offset and notes. Whatever lies at the
        destination is overwritten (the preview lists it). A move on the same track that
        overlaps the clip's own old range goes through a scratch copy after the last
        clip. With to_track_index (and to_expected_name) the clip goes to another track
        of a compatible kind (MIDI to MIDI, audio to audio; Live refuses the rest);
        new_start_time then defaults to the same beat.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            if not isinstance(copy, bool):
                raise TypeError("copy must be true or false, got %r" % (copy,))
            track = self._arr_track(track_index, expected_name)
            clip_start = self._require_finite_number(clip_start_time, "clip_start_time")
            clip = self._arr_find(track, clip_start)
            s, e = float(clip.start_time), float(clip.end_time)
            extent = e - s
            eps = self.ARRANGEMENT_EPSILON
            dest_track = track
            if to_track_index is not None:
                if isinstance(to_track_index, bool) or not isinstance(to_track_index, int):
                    raise TypeError("to_track_index must be an integer")
                if to_track_index != track_index:
                    dest_track = self._arr_track(to_track_index, to_expected_name)
            elif to_expected_name is not None:
                raise ValueError("to_expected_name needs to_track_index")
            other_track = dest_track is not track
            if new_start_time is None:
                if not other_track:
                    raise ValueError("new_start_time is required (or give to_track_index)")
                dest = s
            else:
                dest = self._require_finite_number(new_start_time, "new_start_time")
            if dest < 0:
                raise ValueError("new_start_time must be >= 0")
            if not other_track and abs(dest - s) < eps:
                raise ValueError("The clip already starts at beat %s" % dest)
            overlaps_self = (not other_track) and dest < e - eps and dest + extent > s + eps
            if copy and overlaps_self:
                raise ValueError("A copy cannot overlap the clip it is copied from")
            if other_track and bool(getattr(dest_track, "has_midi_input", False)) != bool(
                    getattr(track, "has_midi_input", False)):
                raise ValueError("Track '%s' is %s and track '%s' is %s: a clip can only go to a track of "
                                 "the same kind" % (track.name, "MIDI" if track.has_midi_input else "audio",
                                                    dest_track.name, "MIDI" if dest_track.has_midi_input else "audio"))
            effects = self._arr_effects(dest_track, dest, dest + extent, ignore=None if other_track else clip)
            info = self._arr_info(track, track_index, do_apply, clip=clip.name,
                                  mode="copy" if copy else "move",
                                  from_range=[s, e], to_range=[dest, dest + extent],
                                  overwrites=effects)
            if other_track:
                info["to_track"] = dest_track.name
            if not do_apply:
                return info
            if not overlaps_self:
                try:
                    dest_track.duplicate_clip_to_arrangement(clip, float(dest))
                except Exception as err:
                    raise RuntimeError("Live refused to place the clip on '%s': %s" % (dest_track.name, err))
                if not copy:
                    self._arr_delete_at(track, s)
            else:
                scratch = self._arr_scratch_time(track)
                try:
                    held = self._arr_dup(track, clip, scratch)
                    self._arr_delete_at(track, s)
                    self._arr_dup(track, held, dest)
                finally:
                    for c in list(track.arrangement_clips):
                        if float(c.start_time) >= scratch - eps:
                            track.delete_clip(c)
            landed = [c for c in dest_track.arrangement_clips
                      if abs(float(c.start_time) - dest) < eps
                      and abs(float(c.end_time) - (dest + extent)) < eps]
            gone = copy or not any(abs(float(c.start_time) - s) < eps and abs(float(c.end_time) - e) < eps
                                   for c in track.arrangement_clips)
            info["applied"] = True
            info["verified"] = len(landed) == 1 and gone
            info["clips"] = self._arr_facts(dest_track)
            if other_track:
                info["source_clips"] = self._arr_facts(track)
            return info
        except Exception as e:
            self.log_message("Error moving arrangement clip: " + str(e))
            raise

    def _create_arrangement_clip(self, track_index, expected_name, start_time, length=None,
                                 notes=None, path=None, name="", confirm=False):
        """Preview or create a clip at a beat position in the Arrangement.

        MIDI track: needs length (beats); notes are optional and must lie inside
        the clip (a note past the end is an error, not silently dropped).
        Audio track: needs path (an audio file); the clip is as long as the file.
        Whatever lies where the new clip goes is overwritten (the preview lists it).
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            track = self._arr_track(track_index, expected_name)
            start = self._require_finite_number(start_time, "start_time")
            if start < 0:
                raise ValueError("start_time must be >= 0")
            is_midi = bool(getattr(track, "has_midi_input", False))
            live_notes = []
            if is_midi:
                if path:
                    raise ValueError("path is for audio tracks; this is a MIDI track")
                length = self._require_finite_number(length, "length")
                if length < self.ARRANGEMENT_MIN_PIECE:
                    raise ValueError("length must be at least %s beats" % self.ARRANGEMENT_MIN_PIECE)
                for position, note in enumerate(notes or []):
                    label = "notes[%d]" % position
                    if not isinstance(note, dict):
                        raise TypeError("%s must be an object" % label)
                    pitch = note.get("pitch")
                    if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
                        raise ValueError("%s.pitch must be an integer 0-127" % label)
                    n_start = self._require_finite_number(note.get("start_time", 0.0), label + ".start_time")
                    n_dur = self._require_finite_number(note.get("duration", 0.25), label + ".duration")
                    velocity = self._require_finite_number(note.get("velocity", 100), label + ".velocity")
                    mute = note.get("mute", False)
                    if not isinstance(mute, bool):
                        raise TypeError("%s.mute must be true or false" % label)
                    if n_start < 0 or n_dur <= 0 or n_start >= length:
                        raise ValueError("%s must start inside the clip (0 <= start < %s) and have "
                                         "a positive duration" % (label, length))
                    if not 1 <= velocity <= 127:
                        raise ValueError("%s.velocity must be 1-127" % label)
                    live_notes.append((pitch, n_start, n_dur, velocity, mute))
                span = length
            else:
                if notes:
                    raise ValueError("notes are for MIDI tracks; this is an audio track")
                if not isinstance(path, str) or not os.path.isfile(path):
                    raise ValueError("path must be an existing audio file, got %r" % (path,))
                span = None
            if name is not None and not isinstance(name, str):
                raise TypeError("name must be a string")
            effects = self._arr_effects(track, start, start + span) if span else []
            info = self._arr_info(track, track_index, do_apply, start_time=start,
                                  length=span, kind="midi" if is_midi else "audio",
                                  note_count=len(live_notes), overwrites=effects)
            if not do_apply:
                if not is_midi:
                    info["note"] = "the clip is as long as the file; what it overwrites is listed after creation"
                return info
            eps = self.ARRANGEMENT_EPSILON
            if is_midi:
                clip = track.create_midi_clip(start, length)
                if live_notes:
                    clip.set_notes(tuple(live_notes))
            else:
                clip = track.create_audio_clip(path, start)
                if clip is None:
                    found = [c for c in track.arrangement_clips
                             if abs(float(c.start_time) - start) < eps]
                    clip = found[0] if len(found) == 1 else None
                if clip is None:
                    raise RuntimeError("Live did not report the new audio clip")
            if name:
                clip.name = name
            info["applied"] = True
            info["created"] = {"name": clip.name, "start_time": float(clip.start_time),
                               "end_time": float(clip.end_time)}
            info["clips"] = self._arr_facts(track)
            return info
        except Exception as e:
            self.log_message("Error creating arrangement clip: " + str(e))
            raise


    # ── Back to Arrangement, track routing ────────────────────────────────────
    # back_to_arrangement is adapted from upstream PR ahujasid/ableton-mcp#119
    # (mateogon); the routing tools from #99 (Zachary May), extended with channels,
    # track_type and a name check.

    def _back_to_arrangement(self):
        """Hand playback back to the Arrangement (Live's Back to Arrangement button).

        Launching a Session clip or scene takes those tracks off the Arrangement
        until this is called. Song.back_to_arranger reads 1 while any track is
        off it; writing 0 returns them. Live may apply it a moment after the
        reply, so the reply gives the value read back and the requested one.
        """
        try:
            song = self._song
            if not hasattr(song, "back_to_arranger"):
                raise RuntimeError("Song.back_to_arranger is not available in this version of Live")
            before = bool(song.back_to_arranger)
            song.back_to_arranger = 0
            return {"before": before, "requested": False,
                    "read_back": bool(song.back_to_arranger),
                    "note": "Live may apply the change just after replying"}
        except Exception as e:
            self.log_message("Error going back to the arrangement: " + str(e))
            raise

    @staticmethod
    def _routing_names(items):
        return [r.display_name for r in items]

    def _routing_state(self, track, direction):
        """Current type and channel plus what Live offers, for one direction."""
        attr = direction + "_routing_"
        state = {}
        if not hasattr(track, attr + "type"):
            return None
        current_type = getattr(track, attr + "type")
        state["type"] = current_type.display_name
        current_channel = getattr(track, attr + "channel", None)
        state["channel"] = current_channel.display_name if current_channel is not None else None
        state["available_types"] = self._routing_names(
            getattr(track, "available_%s_routing_types" % direction, []))
        state["available_channels"] = self._routing_names(
            getattr(track, "available_%s_routing_channels" % direction, []))
        return state

    def _get_track_routing(self, track_index, track_type="track"):
        """Input and output routing of a track: current type and channel, and the
        types and channels Live offers for the current type. Every kind of track
        (track, return, master) reports an input and an output when Live has them."""
        try:
            track = self._resolve_track(track_index, track_type)
            result = {"track_index": track_index if (track_type or "track").lower() != "master" else None,
                      "track_type": (track_type or "track").lower(), "track_name": track.name}
            for direction in ("input", "output"):
                result[direction] = self._routing_state(track, direction)
            return result
        except Exception as e:
            self.log_message("Error getting track routing: " + str(e))
            raise

    @staticmethod
    def _find_routing(items, wanted, what):
        names = [r.display_name for r in items]
        exact = [r for r in items if r.display_name == wanted]
        if len(exact) == 1:
            return exact[0]
        folded = [r for r in items if r.display_name.lower() == str(wanted).lower()]
        if len(exact) > 1 or len(folded) > 1:
            raise ValueError(
                "%d %ss are named '%s' (two tracks share a name), so it cannot be chosen by "
                "name. Rename one of the tracks first." % (len(exact) or len(folded), what.lower(), wanted))
        if len(folded) == 1:
            return folded[0]
        raise ValueError("%s '%s' not found. Available: %s" % (what, wanted, ", ".join(names) or "none"))

    def _set_track_routing(self, track_index, track_type, expected_name, direction,
                           routing_type=None, routing_channel=None):
        """Set the input or output routing (type and/or channel) of a track.

        direction: "input" or "output". routing_type and routing_channel are the
        display names from get_track_routing; give either or both. A type change
        is applied first, then Live is given a moment to list the channels for
        the new type, then the channel is set. expected_name (the track's exact
        current name) is required: a wrong output can silence a track, and it
        catches a stale index. Returns the previous and the new routing.
        """
        if direction not in ("input", "output"):
            raise ValueError("direction must be 'input' or 'output'")
        if routing_type is None and routing_channel is None:
            raise ValueError("Give routing_type and/or routing_channel (names from get_track_routing)")
        self._require_expected_name(expected_name, "track")
        settle = 0.3

        def first():
            track = self._resolve_track(track_index, track_type)
            if track.name != expected_name:
                raise ValueError("Track %s is '%s', not '%s'; indices may have shifted. "
                                 "Nothing was changed." % (track_index, track.name, expected_name))
            before = self._routing_state(track, direction)
            if before is None:
                raise ValueError("A %s track has no %s routing"
                                 % ((track_type or "track").lower(), direction))
            if routing_type is not None:
                chosen = self._find_routing(
                    getattr(track, "available_%s_routing_types" % direction),
                    routing_type, "Routing type")
                if chosen.display_name != before["type"]:
                    setattr(track, direction + "_routing_type", chosen)
            elif routing_channel is not None:
                # fail early, before anything changes, if the channel is unknown
                self._find_routing(getattr(track, "available_%s_routing_channels" % direction),
                                   routing_channel, "Routing channel")
            return before

        try:
            before = self._call_on_main_thread(first)
            if routing_type is not None:
                time.sleep(settle)

            def second():
                track = self._resolve_track(track_index, track_type)
                if routing_channel is not None:
                    chosen = self._find_routing(
                        getattr(track, "available_%s_routing_channels" % direction),
                        routing_channel, "Routing channel")
                    setattr(track, direction + "_routing_channel", chosen)

            try:
                self._call_on_main_thread(second)
            except Exception as e:
                if routing_type is not None and before["type"] != routing_type:
                    def restore():
                        t = self._resolve_track(track_index, track_type)
                        setattr(t, direction + "_routing_type", self._find_routing(
                            getattr(t, "available_%s_routing_types" % direction),
                            before["type"], "Routing type"))
                    self._call_on_main_thread(restore)
                    time.sleep(settle)
                    raise ValueError("%s. The routing type was put back to '%s'; nothing else changed."
                                     % (e, before["type"]))
                raise
            time.sleep(settle)
            after = self._call_on_main_thread(
                lambda: self._routing_state(self._resolve_track(track_index, track_type), direction))
            wanted_ok = ((routing_type is None or after["type"].lower() == str(routing_type).lower())
                         and (routing_channel is None
                              or str(after["channel"]).lower() == str(routing_channel).lower()))
            return {"track_name": expected_name, "direction": direction,
                    "before": {"type": before["type"], "channel": before["channel"]},
                    "after": after, "verified": wanted_ok}
        except Exception as e:
            self.log_message("Error setting track routing: " + str(e))
            raise

    # ── Device routing (sidechain) and clip automation envelopes ──────────────
    # Measured on Live 12.4 Lite (2026-10-24): Compressor and similar devices have
    # input_routing_type / input_routing_channel (the "Audio From" of the
    # sidechain; the channels of a new type are listed a moment later), and a
    # clip's automation_envelope(parameter) answers value_at_time in the
    # parameter's own units while insert_step(time, length, value) writes a
    # constant stretch. Only SESSION clips have an envelope API; a Session clip
    # copied into the Arrangement keeps its automation. Envelope ideas are from
    # upstream PR #23 (zzstoatzz).

    def _device_of(self, track_index, device_index, track_type="track"):
        track = self._resolve_track(track_index, track_type)
        devices = list(track.devices)
        if isinstance(device_index, bool) or not isinstance(device_index, int):
            raise TypeError("device_index must be an integer, got %r" % (device_index,))
        if device_index < 0 or device_index >= len(devices):
            raise IndexError("device index %d out of range (the track has %d)"
                             % (device_index, len(devices)))
        return track, devices[device_index]

    def _device_routing_view(self, track, device, device_index):
        state = self._routing_state(device, "input")
        if state is None:
            raise ValueError(
                "Device '%s' has no routing (only devices with a sidechain, such as "
                "Compressor, Gate, Glue Compressor, expose one)" % device.name)
        sc = None
        for p in device.parameters:
            if p.name == "S/C On":
                sc = bool(p.value)
        return {"track_name": track.name, "device_index": device_index,
                "device_name": device.name, "device_class": device.class_name,
                "sidechain_on": sc, "input": state}

    def _get_device_routing(self, track_index, device_index, track_type="track"):
        """The sidechain "Audio From" of a device: current type and channel and
        what Live offers, plus whether the device's sidechain is switched on."""
        try:
            track, device = self._device_of(track_index, device_index, track_type)
            return self._device_routing_view(track, device, device_index)
        except Exception as e:
            self.log_message("Error getting device routing: " + str(e))
            raise

    def _set_device_routing(self, track_index, device_index, track_type, expected_name,
                            expected_device_name, routing_type=None, routing_channel=None,
                            sidechain_on=None):
        """Set a device's sidechain source (type and/or channel) and, optionally,
        switch its sidechain on or off. Needs the track's and the device's exact
        names. A new type is applied first, Live is given a moment to list its
        channels, then the channel is set."""
        if routing_type is None and routing_channel is None and sidechain_on is None:
            raise ValueError("Give routing_type, routing_channel and/or sidechain_on")
        if sidechain_on is not None and not isinstance(sidechain_on, bool):
            raise TypeError("sidechain_on must be true or false")
        self._require_expected_name(expected_name, "track")
        self._require_expected_name(expected_device_name, "device")
        settle = 0.3

        def first():
            track, device = self._device_of(track_index, device_index, track_type)
            if track.name != expected_name:
                raise ValueError("Track %s is '%s', not '%s'; nothing was changed."
                                 % (track_index, track.name, expected_name))
            if device.name != expected_device_name:
                raise ValueError("Device %s is '%s', not '%s'; nothing was changed."
                                 % (device_index, device.name, expected_device_name))
            before = self._device_routing_view(track, device, device_index)
            if routing_type is not None:
                chosen = self._find_routing(device.available_input_routing_types,
                                            routing_type, "Routing type")
                if chosen.display_name != before["input"]["type"]:
                    device.input_routing_type = chosen
            elif routing_channel is not None:
                self._find_routing(device.available_input_routing_channels,
                                   routing_channel, "Routing channel")
            return before

        try:
            before = self._call_on_main_thread(first)
            if routing_type is not None:
                time.sleep(settle)

            def second():
                track, device = self._device_of(track_index, device_index, track_type)
                if routing_channel is not None:
                    device.input_routing_channel = self._find_routing(
                        device.available_input_routing_channels, routing_channel, "Routing channel")
                if sidechain_on is not None:
                    params = [p for p in device.parameters if p.name == "S/C On"]
                    if not params:
                        raise ValueError("Device '%s' has no 'S/C On' parameter" % device.name)
                    params[0].value = 1.0 if sidechain_on else 0.0

            try:
                self._call_on_main_thread(second)
            except Exception as e:
                if routing_type is not None and before["input"]["type"] != routing_type:
                    def restore():
                        _t, dev = self._device_of(track_index, device_index, track_type)
                        dev.input_routing_type = self._find_routing(
                            dev.available_input_routing_types, before["input"]["type"], "Routing type")
                    self._call_on_main_thread(restore)
                    time.sleep(settle)
                    raise ValueError("%s. The routing type was put back to '%s'; nothing else changed."
                                     % (e, before["input"]["type"]))
                raise
            time.sleep(settle)
            after = self._call_on_main_thread(lambda: self._device_routing_view(
                *self._device_of(track_index, device_index, track_type)[:2], device_index))
            ok = ((routing_type is None or after["input"]["type"].lower() == str(routing_type).lower())
                  and (routing_channel is None
                       or str(after["input"]["channel"]).lower() == str(routing_channel).lower())
                  and (sidechain_on is None or after["sidechain_on"] == sidechain_on))
            return {"before": {"type": before["input"]["type"], "channel": before["input"]["channel"],
                               "sidechain_on": before["sidechain_on"]},
                    "after": after, "verified": ok}
        except Exception as e:
            self.log_message("Error setting device routing: " + str(e))
            raise

    ENVELOPE_MAX_STEPS = 2048
    ENVELOPE_SAMPLE_OFFSET = 1e-4
    ENVELOPE_MAX_SAMPLES = 512

    def _automation_target(self, track, parameter, device_index):
        """The automatable parameter named by (parameter, device_index) on a track.

        device_index None: a mixer parameter, "volume", "pan" or "send <letter or
        index>" (for example "send A" or "send 0"). Otherwise a parameter of that
        device, by exact name (case-insensitive) or by its index in the device's
        parameter list.
        """
        if parameter is None or (isinstance(parameter, str) and parameter == ""):
            raise ValueError("parameter is required (volume, pan, send A, or a device parameter)")
        if device_index is None:
            mixer = track.mixer_device
            key = str(parameter).strip().lower()
            if key in ("volume", "track volume"):
                return mixer.volume
            if key in ("pan", "panning", "track pan"):
                return mixer.panning
            if key.startswith("send"):
                label = key.replace("send", "", 1).strip()
                sends = list(mixer.sends)
                index = None
                if label.isdigit():
                    index = int(label)
                elif len(label) == 1 and label.isalpha():
                    index = ord(label) - ord("a")
                if index is None or index < 0 or index >= len(sends):
                    raise ValueError("Unknown send '%s'; the track has %d send(s) (A, B, ...)"
                                     % (parameter, len(sends)))
                return sends[index]
            raise ValueError("Unknown mixer parameter '%s' (use volume, pan or send A/B)" % parameter)
        if isinstance(device_index, bool) or not isinstance(device_index, int):
            raise TypeError("device_index must be an integer")
        devices = list(track.devices)
        if device_index < 0 or device_index >= len(devices):
            raise IndexError("device index %d out of range (the track has %d)"
                             % (device_index, len(devices)))
        params = list(devices[device_index].parameters)
        if isinstance(parameter, int) and not isinstance(parameter, bool):
            if parameter < 0 or parameter >= len(params):
                raise IndexError("parameter index %d out of range (the device has %d)"
                                 % (parameter, len(params)))
            return params[parameter]
        matches = [p for p in params if p.name.lower() == str(parameter).lower()]
        if len(matches) != 1:
            names = ", ".join(sorted(set(p.name for p in params)))
            raise ValueError("%s parameter '%s' on '%s'. Parameters: %s"
                             % ("No" if not matches else "Several", parameter,
                                devices[device_index].name, names))
        return matches[0]

    def _envelope_clip(self, track_index, clip_index, expected_name, arrangement, clip_start_time):
        """(track, clip) for a Session slot or, when arrangement is true, the
        Arrangement clip that starts at clip_start_time."""
        if isinstance(track_index, bool) or not isinstance(track_index, int):
            raise TypeError("track_index must be an integer")
        tracks = list(self._song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            raise IndexError("track index %d out of range (have %d)" % (track_index, len(tracks)))
        track = tracks[track_index]
        if expected_name is not None and track.name != expected_name:
            raise ValueError("Track %d is '%s', not '%s'; nothing was changed."
                             % (track_index, track.name, expected_name))
        if arrangement:
            raise ValueError(
                "Live only gives the API the automation of SESSION clips ('Not a session clip' "
                "for an Arrangement clip). Write the automation on a Session clip, then copy that "
                "clip into the Arrangement with duplicate_to_arrangement: Live carries the clip's "
                "automation along (get_arrangement_clips shows has_envelopes).")
        if isinstance(clip_index, bool) or not isinstance(clip_index, int):
            raise TypeError("clip_index must be an integer")
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise ValueError("No clip in slot %d of track '%s'" % (clip_index, track.name))
        clip = slot.clip
        return track, clip

    @staticmethod
    def _param_facts(p):
        facts = {"name": p.name, "min": float(p.min), "max": float(p.max), "value": float(p.value)}
        try:
            facts["display"] = p.str_for_value(p.value)
        except Exception:
            pass
        return facts

    def _clip_span(self, clip, arrangement):
        if arrangement:
            return float(clip.end_time) - float(clip.start_time)
        return float(clip.length)

    def _get_clip_envelope(self, track_index, clip_index, parameter, device_index=None,
                           arrangement=False, clip_start_time=None, start=None, end=None,
                           step=0.25):
        """Read a clip's automation of one parameter as samples of value_at_time.

        Times are beats from the clip start; values are in the parameter's own
        units (a display string is added). has_envelope is false when the clip
        has no automation for it. At most 512 samples; raise step for long clips.
        """
        try:
            track, clip = self._envelope_clip(track_index, clip_index, None, arrangement,
                                              clip_start_time)
            target = self._automation_target(track, parameter, device_index)
            span = self._clip_span(clip, arrangement)
            a = 0.0 if start is None else self._require_finite_number(start, "start")
            b = span if end is None else self._require_finite_number(end, "end")
            st = self._require_finite_number(step, "step")
            if st <= 0 or b <= a:
                raise ValueError("step must be > 0 and end > start")
            count = int(math.ceil((b - a) / st))
            if count > self.ENVELOPE_MAX_SAMPLES:
                raise ValueError("%d samples requested; at most %d. Raise step or narrow start/end."
                                 % (count, self.ENVELOPE_MAX_SAMPLES))
            env = clip.automation_envelope(target)
            result = {"track_name": track.name, "clip_name": clip.name, "clip_span": span,
                      "parameter": self._param_facts(target), "has_envelope": env is not None}
            if env is not None:
                samples = []
                for i in range(count):
                    t = a + i * st
                    # At the exact start of a step Live answers with the value from
                    # before the jump (two events share that time), so ask just after.
                    v = float(env.value_at_time(t + self.ENVELOPE_SAMPLE_OFFSET))
                    row = {"time": t, "value": v}
                    try:
                        row["display"] = target.str_for_value(v)
                    except Exception:
                        pass
                    samples.append(row)
                result["samples"] = samples
            return result
        except Exception as e:
            self.log_message("Error reading clip envelope: " + str(e))
            raise

    ENVELOPE_SHAPES = ("sine", "triangle", "saw_up", "saw_down", "square",
                       "random_steps", "random_smooth", "curve")
    ENVELOPE_JUMP = 1.0 / 128.0     # beats between the two events of a vertical jump

    def _envelope_event(self, time_val, value):
        """A Live envelope event (a real breakpoint; Live draws straight lines between them)."""
        try:
            import Live
            return Live.Envelope.EnvelopeEvent(float(time_val), float(value))
        except Exception:
            return types.SimpleNamespace(time=float(time_val), value=float(value))

    def _envelope_shape_points(self, shape, lo, hi, span):
        """Turn a shape spec into breakpoints. Returns (points, mode, summary).

        shape: {"type": one of ENVELOPE_SHAPES, "start", "end" (beats, default the
        clip), "period" beats or "cycles", "min", "max" (parameter units, default the
        parameter's range), "phase" (0-1 of a cycle; sine starts at the middle going
        up, phase 0.75 starts at the bottom), "points_per_cycle" (4-128, default 16),
        "duty" (square, 0.01-0.99), "seed" (random), "exponent" (curve), "invert"}.
        Straight lines between breakpoints are all Live offers (curve coefficients
        are ignored), so a sine is drawn with points_per_cycle breakpoints per cycle:
        16 is within 2% of the amplitude, 32 within 0.5%.
        """
        if not isinstance(shape, dict):
            raise TypeError("shape must be an object like {\"type\": \"sine\", \"period\": 4}")
        known = set(("type", "start", "end", "period", "cycles", "min", "max", "phase",
                     "points_per_cycle", "duty", "seed", "exponent", "invert"))
        unknown = sorted(set(shape) - known)
        if unknown:
            raise ValueError("shape has unknown field(s) %s; allowed: %s"
                             % (", ".join(unknown), ", ".join(sorted(known))))
        kind = shape.get("type")
        if kind not in self.ENVELOPE_SHAPES:
            raise ValueError("shape.type must be one of %s" % ", ".join(self.ENVELOPE_SHAPES))
        num = self._require_finite_number
        start = num(shape.get("start", 0.0), "shape.start")
        end = span if shape.get("end") is None else num(shape["end"], "shape.end")
        if start < 0 or end <= start or end > span + 1e-9:
            raise ValueError("shape start/end must satisfy 0 <= start < end <= the clip's length (%s)" % span)
        vmin = lo if shape.get("min") is None else num(shape["min"], "shape.min")
        vmax = hi if shape.get("max") is None else num(shape["max"], "shape.max")
        for label, v in (("min", vmin), ("max", vmax)):
            if v < lo - 1e-9 or v > hi + 1e-9:
                raise ValueError("shape.%s %s is outside the parameter's range %s..%s" % (label, v, lo, hi))
        if vmax < vmin:
            raise ValueError("shape.max must be >= shape.min")
        if shape.get("invert") is not None and not isinstance(shape["invert"], bool):
            raise TypeError("shape.invert must be true or false")
        invert = bool(shape.get("invert", False))
        phase = num(shape.get("phase", 0.0), "shape.phase")
        ppc = shape.get("points_per_cycle", 16)
        if isinstance(ppc, bool) or not isinstance(ppc, int) or ppc < 4 or ppc > 128:
            raise ValueError("shape.points_per_cycle must be an integer 4-128")
        if kind == "curve":
            period = end - start
        elif shape.get("period") is not None and shape.get("cycles") is not None:
            raise ValueError("give shape.period or shape.cycles, not both")
        elif shape.get("cycles") is not None:
            cycles = num(shape["cycles"], "shape.cycles")
            if cycles <= 0:
                raise ValueError("shape.cycles must be > 0")
            period = (end - start) / cycles
        else:
            period = num(shape.get("period", 4.0), "shape.period")
        if period < 0.03125:
            raise ValueError("the period is too short (%s beats; at least 0.03125)" % period)
        mid, amp = (vmin + vmax) / 2.0, (vmax - vmin) / 2.0
        sign = -1.0 if invert else 1.0

        def frac(t):
            return ((t - start) / period + phase) % 1.0

        def at(unit):          # unit in -1..1 -> parameter value
            return mid + sign * amp * unit

        pts, mode = [], "linear"
        eps = self.ENVELOPE_JUMP
        if kind == "sine":
            n = max(1, int(math.ceil((end - start) / period * ppc)))
            for k in range(n + 1):
                t = min(end, start + k * period / ppc)
                pts.append((t, at(math.sin(2.0 * math.pi * frac(t)))))
        elif kind == "triangle":
            times = set([start, end])
            m = int(math.floor((start - start) / period - 1))
            while True:
                for off in (0.25, 0.75):
                    t = start + period * (m + off - phase)
                    if start < t < end:
                        times.add(t)
                m += 1
                if start + period * (m - 1 - phase) > end:
                    break
            for t in sorted(times):
                pts.append((t, at(1.0 - 4.0 * abs(((frac(t) + 0.25) % 1.0) - 0.5))))
        elif kind in ("saw_up", "saw_down"):
            def saw(t):
                x = frac(t)
                return at((2.0 * x - 1.0) if kind == "saw_up" else (1.0 - 2.0 * x))
            wraps, m = [], int(math.floor(-phase)) - 1
            while True:
                t = start + period * (m - phase)
                if t > end:
                    break
                if start + eps < t < end - eps:
                    wraps.append(t)
                m += 1
            pts.append((start, saw(start)))
            for w in wraps:
                pts.append((w - eps, saw(w - eps)))
                pts.append((w, saw(w)))
            if end - eps > pts[-1][0]:
                pts.append((end - eps, saw(end - eps)))     # the top of the last ramp, before the clip ends
            pts.append((end, saw(end)))
        elif kind == "square":
            mode = "steps"
            duty = num(shape.get("duty", 0.5), "shape.duty")
            if duty < 0.01 or duty > 0.99:
                raise ValueError("shape.duty must be between 0.01 and 0.99")
            high, low = at(1.0), at(-1.0)
            pts.append((start, high if frac(start) < duty else low))
            times = []
            m = int(math.floor(-phase)) - 1
            while True:
                base = start + period * (m - phase)
                if base > end:
                    break
                for t, value in ((base, high), (base + duty * period, low)):
                    if start + 1e-9 < t < end - 1e-9:
                        times.append((t, value))
                m += 1
            pts += sorted(times)
        elif kind in ("random_steps", "random_smooth"):
            import random
            rng = random.Random(shape.get("seed", 0))
            mode = "steps" if kind == "random_steps" else "linear"
            n = max(1, int(math.ceil((end - start) / period)))
            for k in range(n + (1 if mode == "linear" else 0)):
                pts.append((min(end, start + k * period), vmin + (vmax - vmin) * rng.random()))
            if mode == "steps":
                pts = [(t, v) for t, v in pts if t < end - 1e-9]
        else:   # curve
            exponent = num(shape.get("exponent", 2.0), "shape.exponent")
            if exponent <= 0 or exponent > 20:
                raise ValueError("shape.exponent must be between 0 and 20")
            for k in range(ppc + 1):
                x = k / float(ppc)
                value = vmin + (vmax - vmin) * (x ** exponent)
                pts.append((start + x * (end - start), (vmax + vmin - value) if invert else value))
        # drop points that landed on the same time with the same value, keep order
        clean = []
        for t, v in pts:
            if clean and abs(clean[-1][0] - t) < 1e-9 and abs(clean[-1][1] - v) < 1e-12:
                continue
            clean.append((t, max(lo, min(hi, v))))
        summary = {"type": kind, "start": start, "end": end, "period": period, "min": vmin,
                   "max": vmax, "phase": phase, "invert": invert}
        return clean, mode, summary

    def _display_to_raw(self, param, number):
        """The raw value at which `param` displays `number` (Hz, ms, dB, %): Live does the
        conversion, so the parameter is set to it and put back at once."""
        if getattr(param, "is_quantized", False):
            raise ValueError("'%s' is a choice, not a number: give its position with value_unit raw" % param.name)
        if not hasattr(param, "display_value"):
            raise RuntimeError("This version of Live has no DeviceParameter.display_value")
        old = param.value
        try:
            param.display_value = float(number)
            return float(param.value)
        except Exception as e:
            raise ValueError("Live would not take %s as a display value for '%s': %s"
                             % (number, param.name, str(e).strip()[:100]))
        finally:
            param.value = old

    def _set_clip_envelope(self, track_index, clip_index, expected_name, parameter,
                           device_index=None, arrangement=False, clip_start_time=None,
                           points=None, mode="linear", resolution=0.125, end=None,
                           confirm=False, shape=None, value_unit="raw"):
        """Preview or write a clip's automation of one parameter.

        Give points or shape.
        points: [{"time": beats from the clip start, "value": parameter units}, ...]
        in increasing time. mode "linear" (default; "ramp" is the same): real
        breakpoints, Live draws straight lines between them; after the last point the
        value holds until `end` (default the clip's end). mode "steps": each value
        holds until the next point. shape: a generated wave (sine, triangle, saw_up,
        saw_down, square, random_steps, random_smooth, curve), see
        _envelope_shape_points. Existing automation of this parameter between the first
        point and the end is replaced. Previews unless confirm is exactly True.
        value_unit "display": the values (points' value, shape min and max) are in the
        unit Live displays (Hz, ms, dB, %), converted by Live itself; a shape still runs
        between the converted ends in the parameter's own curve.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            self._require_expected_name(expected_name, "track")
            track, clip = self._envelope_clip(track_index, clip_index, expected_name, arrangement,
                                              clip_start_time)
            target = self._automation_target(track, parameter, device_index)
            if mode == "ramp":
                mode = "linear"
            if mode not in ("steps", "linear"):
                raise ValueError("mode must be 'linear' or 'steps' ('ramp' means linear)")
            if value_unit not in ("raw", "display"):
                raise ValueError("value_unit must be 'raw' or 'display'")
            converted = []

            def to_raw(number, label):
                number = self._require_finite_number(number, label)
                if value_unit == "raw":
                    return number
                raw = self._display_to_raw(target, number)
                converted.append({"display": number, "raw": raw})
                return raw

            span = self._clip_span(clip, arrangement)
            lo, hi = float(target.min), float(target.max)
            summary = None
            if shape is not None:
                if points:
                    raise ValueError("give points or shape, not both")
                if value_unit == "display":
                    shape = dict(shape)
                    for key in ("min", "max"):
                        if shape.get(key) is not None:
                            shape[key] = to_raw(shape[key], "shape." + key)
                pts, mode, summary = self._envelope_shape_points(shape, lo, hi, span)
                stop = summary["end"]
            else:
                if not isinstance(points, (list, tuple)) or not points:
                    raise ValueError("points must be a non-empty list of {time, value} (or give shape)")
                stop = span if end is None else self._require_finite_number(end, "end")
                pts = []
                last = None
                for i, pt in enumerate(points):
                    if not isinstance(pt, dict):
                        raise TypeError("points[%d] must be an object" % i)
                    t = self._require_finite_number(pt.get("time"), "points[%d].time" % i)
                    v = to_raw(pt.get("value"), "points[%d].value" % i)
                    too_late = t > span + 1e-9 if mode == "linear" else t >= span
                    if t < 0 or too_late:
                        raise ValueError("points[%d].time %s is outside the clip (0 to %s beats)" % (i, t, span))
                    if v < lo - 1e-9 or v > hi + 1e-9:
                        raise ValueError("points[%d].value %s is outside '%s' range %s..%s"
                                         % (i, v, target.name, lo, hi))
                    if last is not None and t <= last:
                        raise ValueError("points must be in increasing time (point %d)" % i)
                    last = t
                    pts.append((t, v))
                if stop <= pts[0][0] and not (mode == "linear" and len(pts) > 1 and stop >= pts[-1][0]):
                    raise ValueError("end must be after the first point and not past the clip's end (%s)" % span)
                if stop > span + 1e-9:
                    raise ValueError("end must be after the first point and not past the clip's end (%s)" % span)
            if mode == "steps":
                steps = []   # (time, length, value)
                for i, (t, v) in enumerate(pts):
                    nxt = pts[i + 1][0] if i + 1 < len(pts) else stop
                    if nxt - t > 1e-9:
                        steps.append((t, nxt - t, v))
                events = []
                count = len(steps)
            else:
                events = list(pts)
                if stop - events[-1][0] > 1e-6:          # hold the last value until `stop`
                    events.append((stop, events[-1][1]))
                steps = []
                count = len(events)
            if count > self.ENVELOPE_MAX_STEPS:
                raise ValueError("%d events; at most %d. Use a longer period, fewer points_per_cycle "
                                 "or a shorter range." % (count, self.ENVELOPE_MAX_STEPS))
            existing = clip.automation_envelope(target) is not None
            info = {"track_name": track.name, "clip_name": clip.name, "parameter": self._param_facts(target),
                    "mode": mode, "point_count": len(pts), "event_count": count,
                    "from": pts[0][0], "to": stop, "replaces_existing_automation": existing,
                    "applied": False, "dry_run": not do_apply}
            if summary is not None:
                info["shape"] = summary
            if converted:
                info["value_unit"] = "display"
                info["converted"] = converted[:8]
            if not do_apply:
                return info
            env = clip.automation_envelope(target)
            if env is None:
                env = clip.create_automation_envelope(target)
            if mode == "steps":
                for t, length, v in steps:
                    env.insert_step(float(t), float(length), float(v))
            else:
                try:
                    env.delete_events_in_range(float(events[0][0]) - 1e-6, float(stop) + 1e-6)
                except Exception as e:
                    self.log_message("delete_events_in_range failed: " + str(e))
                for t, v in events:
                    env.create_event(self._envelope_event(t, v))
            sample = pts if len(pts) <= 16 else pts[::max(1, len(pts) // 16)]
            checks = []
            worst = 0.0
            for t, v in sample:
                got = float(env.value_at_time(min(t + self.ENVELOPE_SAMPLE_OFFSET, stop)))
                checks.append({"time": t, "wanted": v, "read_back": got})
                worst = max(worst, abs(got - v))
            tol = (hi - lo) * 0.01 + 1e-6
            if mode == "linear" and any(abs(events[k][0] - events[k + 1][0]) < 0.02 for k in range(len(events) - 1)):
                tol = (hi - lo) * 0.05      # a vertical jump (saw) reads between its two events
            info["verified"] = worst <= tol
            info["max_error"] = worst
            info["checks"] = checks[:8]
            info["applied"] = True
            return info
        except Exception as e:
            self.log_message("Error writing clip envelope: " + str(e))
            raise

    def _clear_clip_envelope(self, track_index, clip_index, expected_name, parameter,
                             device_index=None, arrangement=False, clip_start_time=None,
                             confirm=False):
        """Preview or remove a clip's automation of one parameter (Live's undo can bring it back)."""
        try:
            do_apply = self._require_confirm_flag(confirm)
            self._require_expected_name(expected_name, "track")
            track, clip = self._envelope_clip(track_index, clip_index, expected_name, arrangement,
                                              clip_start_time)
            target = self._automation_target(track, parameter, device_index)
            had = clip.automation_envelope(target) is not None
            info = {"track_name": track.name, "clip_name": clip.name,
                    "parameter": self._param_facts(target), "had_automation": had,
                    "applied": False, "dry_run": not do_apply}
            if not do_apply:
                return info
            if had:
                clip.clear_envelope(target)
            info["applied"] = True
            info["has_automation_now"] = clip.automation_envelope(target) is not None
            return info
        except Exception as e:
            self.log_message("Error clearing clip envelope: " + str(e))
            raise

    # ── Overview and arrangement check ────────────────────────────────────────
    # Both are adapted from upstream PR ahujasid/ableton-mcp#110 (M4x28): one
    # compact read of every track, and a check of the Arrangement for clips off
    # the grid, overlaps and gaps.

    @staticmethod
    def _display(param):
        try:
            return param.str_for_value(param.value)
        except Exception:
            return None

    def _track_overview_row(self, index, track, kind):
        row = {"index": index, "name": track.name, "kind": kind,
               "devices": [d.name for d in track.devices]}
        mixer = getattr(track, "mixer_device", None)
        if mixer is not None:
            row["volume"] = self._display(mixer.volume)
            row["pan"] = self._display(mixer.panning)
        if kind != "master":
            for attr in ("mute", "solo"):
                if hasattr(track, attr):
                    row[attr] = bool(getattr(track, attr))
            # only when true: why a track is silent (another one is soloed) and that it is frozen
            if self._safe_attr(track, "muted_via_solo", bool, False):
                row["muted_via_solo"] = True
            if self._safe_attr(track, "is_frozen", bool, False):
                row["frozen"] = True
        if kind in ("audio", "midi", "group"):
            if getattr(track, "can_be_armed", False):
                row["arm"] = bool(track.arm)
            try:
                # hasattr is true for group tracks too, but reading it raises there
                row["monitoring"] = self.MONITORING_NAMES.get(int(track.current_monitoring_state), "?")
            except Exception:
                pass
            row["session_clips"] = sum(1 for slot in track.clip_slots if slot.has_clip)
            if kind != "group":
                row["arrangement_clips"] = len(list(track.arrangement_clips))
            group = getattr(track, "group_track", None)
            if group is not None:
                row["group"] = group.name
            try:
                row["color_index"] = int(track.color_index)
            except Exception:
                pass
        return row

    def _get_tracks_overview(self):
        """Every track, return and the master in one compact read: kind, devices,
        mixer, mute/solo/arm, clip counts, group. Use it before reaching for
        get_track_info on each track."""
        try:
            song = self._song
            tracks = []
            for i, t in enumerate(song.tracks):
                if getattr(t, "is_foldable", False):
                    kind = "group"
                elif getattr(t, "has_midi_input", False):
                    kind = "midi"
                else:
                    kind = "audio"
                tracks.append(self._track_overview_row(i, t, kind))
            returns = [self._track_overview_row(i, t, "return") for i, t in enumerate(song.return_tracks)]
            return {"tempo": song.tempo,
                    "time_signature": "%d/%d" % (song.signature_numerator, song.signature_denominator),
                    "is_playing": bool(song.is_playing),
                    "track_count": len(tracks), "tracks": tracks,
                    "return_tracks": returns,
                    "master": self._track_overview_row(0, song.master_track, "master"),
                    "scene_count": len(song.scenes), "cue_point_count": len(song.cue_points)}
        except Exception as e:
            self.log_message("Error getting tracks overview: " + str(e))
            raise

    def _check_arrangement_sync(self, grid_beats=4.0, tolerance=1e-3):
        """Check each track's Arrangement clips: starts and ends off the grid,
        overlaps, and gaps between neighbouring clips. Read-only.

        grid_beats: the grid to check against (4 = bars in 4/4; 1 = beats).
        Each list is cut at 20 entries; the counts are complete. A gap is only
        silence between two clips of the same track, which is often intended.
        """
        try:
            grid = self._require_finite_number(grid_beats, "grid_beats")
            tol = self._require_finite_number(tolerance, "tolerance")
            if grid <= 0 or tol < 0:
                raise ValueError("grid_beats must be > 0 and tolerance >= 0")
            cap = 20

            def off_grid(value):
                remainder = value % grid
                return remainder > tol and (grid - remainder) > tol

            report = []
            totals = {"clips": 0, "off_grid": 0, "overlaps": 0, "gaps": 0}
            for index, track in enumerate(self._song.tracks):
                if getattr(track, "is_foldable", False):
                    continue
                clips = self._arr_clips(track)
                if not clips:
                    continue
                problems = {"off_grid": [], "overlaps": [], "gaps": []}
                counts = {"off_grid": 0, "overlaps": 0, "gaps": 0}
                previous = None
                for clip in clips:
                    start, end = float(clip.start_time), float(clip.end_time)
                    for edge, value in (("start", start), ("end", end)):
                        if off_grid(value):
                            counts["off_grid"] += 1
                            if len(problems["off_grid"]) < cap:
                                problems["off_grid"].append(
                                    {"clip": clip.name, "edge": edge, "beat": value})
                    if previous is not None:
                        pe = float(previous.end_time)
                        if start < pe - tol:
                            counts["overlaps"] += 1
                            if len(problems["overlaps"]) < cap:
                                problems["overlaps"].append(
                                    {"clips": [previous.name, clip.name], "overlap_beats": pe - start})
                        elif start - pe > tol:
                            counts["gaps"] += 1
                            if len(problems["gaps"]) < cap:
                                problems["gaps"].append(
                                    {"from": pe, "to": start, "length": start - pe})
                    previous = clip
                totals["clips"] += len(clips)
                for key in counts:
                    totals[key] += counts[key]
                report.append({"index": index, "track": track.name, "clips": len(clips),
                               "first_start": float(clips[0].start_time),
                               "last_end": float(clips[-1].end_time),
                               "counts": counts, "problems": problems})
            totals["in_sync"] = totals["off_grid"] == 0 and totals["overlaps"] == 0
            return {"grid_beats": grid, "totals": totals, "tracks": report}
        except Exception as e:
            self.log_message("Error checking arrangement: " + str(e))
            raise

    # ── Monitoring and duplicating tracks ─────────────────────────────────────
    # Duplicate track is from upstream PR #94 (Luke Gimza); the monitoring state
    # (Track.current_monitoring_state: 0 In, 1 Auto, 2 Off) is new.

    MONITORING_NAMES = {0: "in", 1: "auto", 2: "off"}

    def _set_track_monitoring(self, track_index, state, expected_name=None):
        """Set a track's monitoring: "in", "auto" or "off". Audio tracks and MIDI
        tracks; the master, returns and tracks inside a group that follow it have
        none. Returns the previous and the new state."""
        try:
            key = str(state).strip().lower()
            names = dict((v, k) for k, v in self.MONITORING_NAMES.items())
            if key not in names:
                raise ValueError("state must be 'in', 'auto' or 'off', got %r" % (state,))
            track = self._resolve_track(track_index, "track")
            if expected_name is not None and track.name != expected_name:
                raise ValueError("Track %s is '%s', not '%s'; nothing was changed."
                                 % (track_index, track.name, expected_name))
            try:
                before = self.MONITORING_NAMES.get(int(track.current_monitoring_state), "?")
            except Exception:
                raise ValueError("Track '%s' has no monitoring state (group tracks, returns and the "
                                 "master do not)" % track.name)
            track.current_monitoring_state = names[key]
            return {"track_name": track.name, "previous": before,
                    "state": self.MONITORING_NAMES.get(int(track.current_monitoring_state), "?")}
        except Exception as e:
            self.log_message("Error setting track monitoring: " + str(e))
            raise

    def _duplicate_track(self, track_index, expected_name):
        """Duplicate a track (devices, clips and mixer), placed right after it.
        Live Lite refuses past 8 tracks: the reply says so and nothing changes."""
        try:
            self._require_expected_name(expected_name, "track")
            track = self._resolve_track(track_index, "track")
            if track.name != expected_name:
                raise ValueError("Track %s is '%s', not '%s'; nothing was changed."
                                 % (track_index, track.name, expected_name))
            before = len(self._song.tracks)
            try:
                self._song.duplicate_track(track_index)
            except Exception as e:
                raise RuntimeError("Live refused to duplicate the track (%s). Live Lite allows "
                                   "8 tracks; the Set has %d." % (e, before))
            after = len(self._song.tracks)
            if after != before + 1:
                raise RuntimeError("Live did not add a track (it has %d, it had %d)" % (after, before))
            new = self._song.tracks[track_index + 1]
            return {"source": track.name, "new_track_index": track_index + 1, "new_track_name": new.name,
                    "track_count": after,
                    "devices": [d.name for d in new.devices],
                    "session_clips": sum(1 for slot in new.clip_slots if slot.has_clip),
                    "note": "tracks after it moved down by one; the new track may have taken the arm"}
        except Exception as e:
            self.log_message("Error duplicating track: " + str(e))
            raise

    # ── Browser search ────────────────────────────────────────────────────────
    # Idea from upstream PR #97 (vanjaoljaca): look an item up by name instead of
    # walking folders of 150+ items. Breadth first (what is near the top, like a
    # device, comes before presets deep inside), with a time budget.

    BROWSER_ROOTS = ("instruments", "sounds", "drums", "audio_effects", "midi_effects",
                     "plugins", "user_library", "packs")

    def _search_browser_items(self, query, category="all", max_results=20, max_seconds=6.0,
                              loadable_only=False):
        """Find browser items whose name or path contains every word of the query.

        category: "all" or one of BROWSER_ROOTS. Results carry the uri that
        load_instrument_or_effect takes. truncated is true when the time or the
        result limit stopped the search before the whole tree was seen.
        """
        try:
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query is required (words to look for in the item name)")
            if category != "all" and category not in self.BROWSER_ROOTS:
                raise ValueError("category must be 'all' or one of %s" % ", ".join(self.BROWSER_ROOTS))
            limit = int(max_results)
            seconds = float(max_seconds)
            if limit < 1 or limit > 200 or seconds <= 0 or seconds > 30:
                raise ValueError("max_results must be 1-200 and max_seconds 0-30")
            words = [w for w in query.lower().split() if w]
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            browser = app.browser
            roots = []
            for name in (self.BROWSER_ROOTS if category == "all" else (category,)):
                root = getattr(browser, name, None)
                if root is not None:
                    roots.append((name, root))
            started = time.time()
            # (item, root name, names of the folders below the root down to the item)
            queue_ = collections.deque((root, name, "") for name, root in roots)
            results = []
            visited = 0
            skipped = 0
            truncated = False
            while queue_:
                if time.time() - started > seconds:
                    truncated = True
                    break
                item, root_name, below = queue_.popleft()
                visited += 1
                name = getattr(item, "name", "") or ""
                path = root_name + ("/" + below if below else "")
                # words are looked for in the item's own name and the folders below
                # the root, never in the root's name (every item is under one)
                if below and all(w in below.lower() for w in words):
                    loadable = bool(getattr(item, "is_loadable", False))
                    if loadable or not loadable_only:
                        results.append({"name": name, "path": path, "uri": getattr(item, "uri", None),
                                        "is_loadable": loadable,
                                        "is_device": bool(getattr(item, "is_device", False)),
                                        "is_folder": bool(getattr(item, "is_folder", False))})
                        if len(results) >= limit:
                            truncated = bool(queue_)
                            break
                try:
                    children = list(getattr(item, "children", None) or [])
                except Exception:
                    skipped += 1
                    continue
                for child in children:
                    child_name = getattr(child, "name", "") or "?"
                    queue_.append((child, root_name, below + "/" + child_name if below else child_name))
            return {"query": query, "category": category, "count": len(results), "results": results,
                    "visited": visited, "skipped": skipped, "truncated": truncated,
                    "seconds": round(time.time() - started, 2)}
        except Exception as e:
            self.log_message("Error searching the browser: " + str(e))
            raise

    # ── Undo steps, Live status and dialogs ───────────────────────────────────
    # Measured on Live 12.4 Lite (2026-10-24): Song.begin_undo_step / end_undo_step make
    # each wrapped edit its own undo step (without them Live merged every API edit into one).

    def _begin_undo_step(self, command_type):
        """Open an undo step around one main-thread command; True if one was opened.
        Not around undo/redo themselves."""
        if command_type in ("undo", "redo"):
            return False
        begin = getattr(self._song, "begin_undo_step", None)
        if begin is None:
            return False
        try:
            begin()
            return True
        except Exception as e:
            self.log_message("begin_undo_step failed: " + str(e))
            return False

    def _end_undo_step(self, opened):
        if not opened:
            return
        try:
            self._song.end_undo_step()
        except Exception as e:
            self.log_message("end_undo_step failed: " + str(e))

    def _get_live_status(self):
        """Live's version and edition, CPU load (average and peak, and per track), the
        features this edition lacks, and any open dialog. Every field is read on its own,
        so one that this Live lacks does not stop the rest."""
        app = self.application()
        song = self._song
        info = {}

        def put(key, fn):
            try:
                info[key] = fn()
            except Exception as e:
                info[key] = None
                info.setdefault("unavailable", []).append("%s (%s)" % (key, str(e)[:60]))

        put("version", app.get_version_string)
        put("build", app.get_build_id)
        put("variant", app.get_variant)
        put("cpu_average", lambda: float(app.average_process_usage))
        put("cpu_peak", lambda: float(app.peak_process_usage))
        put("features_this_edition_lacks", lambda: [str(f) for f in app.unavailable_features])
        put("open_dialogs", lambda: int(app.open_dialog_count))
        if info.get("open_dialogs"):
            put("dialog_message", lambda: app.current_dialog_message)
            put("dialog_button_count", lambda: int(app.current_dialog_button_count))
        put("is_playing", lambda: bool(song.is_playing))
        put("tempo", lambda: float(song.tempo))
        put("exclusive_arm", lambda: bool(song.exclusive_arm))
        put("exclusive_solo", lambda: bool(song.exclusive_solo))
        put("last_event_time", lambda: float(song.last_event_time))
        put("can_capture_midi", lambda: bool(song.can_capture_midi))
        put("automation_overridden", lambda: bool(song.re_enable_automation_enabled))
        put("punch_in", lambda: bool(song.punch_in))
        put("punch_out", lambda: bool(song.punch_out))
        put("arrangement_overdub", lambda: bool(song.arrangement_overdub))
        put("record_mode", lambda: bool(song.record_mode))
        put("count_in_duration", lambda: int(song.count_in_duration))
        impact = []
        for kind, tracks in (("track", song.tracks), ("return", song.return_tracks)):
            for i, t in enumerate(tracks):
                try:
                    value = float(t.performance_impact)
                except Exception:
                    continue
                impact.append({"kind": kind, "index": i, "name": t.name, "performance_impact": value})
        impact.sort(key=lambda r: -r["performance_impact"])
        info["track_performance_impact"] = impact
        return info

    def _press_dialog_button(self, button_index, expected_message):
        """Press a button of the dialog Live is showing (a modal "Couldn't create track", say).

        Both guards are required: button_index (0-based; Live reports the button COUNT, not
        their labels) and expected_message, a piece of the dialog's own text that must be in it,
        so a different dialog that appeared in the meantime is never answered by mistake.
        """
        try:
            app = self.application()
            if isinstance(button_index, bool) or not isinstance(button_index, int):
                raise TypeError("button_index must be an integer")
            if not isinstance(expected_message, str) or not expected_message.strip():
                raise ValueError("expected_message is required: a piece of the dialog's text "
                                 "(read it with get_live_status)")
            if int(app.open_dialog_count) < 1:
                raise ValueError("No dialog is open")
            message = app.current_dialog_message
            if expected_message.lower() not in message.lower():
                raise ValueError("The open dialog says %r, not something containing %r; nothing was pressed"
                                 % (message, expected_message))
            count = int(app.current_dialog_button_count)
            if button_index < 0 or button_index >= count:
                raise IndexError("button_index %d out of range: the dialog has %d button(s)" % (button_index, count))
            app.press_current_dialog_button(button_index)
            return {"pressed": button_index, "dialog": message, "button_count": count,
                    "open_dialogs_after": int(app.open_dialog_count)}
        except Exception as e:
            self.log_message("Error pressing a dialog button: " + str(e))
            raise

    # ── Devices by name, key and scale, scene tempo, grooves, warp markers, clip copies ──
    # All of these were measured on Live 12.4 Lite (2026-10-24): Track.insert_device takes a native
    # device name (Live Lite refuses "EQ Eight" and "Glue Compressor": "not available"),
    # Song.move_device returns the new position, Clip.WarpMarker takes (seconds in the file, beat),
    # Clip.duplicate_loop doubles the loop with its notes, Clip.duplicate_region copies notes with a
    # transposition, ClipSlot.duplicate_clip_to copies a Session clip to another slot.

    NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    FLAT_NAMES = {"DB": 1, "EB": 3, "GB": 6, "AB": 8, "BB": 10}

    def _named_track(self, track_index, expected_name, track_type="track"):
        self._require_expected_name(expected_name, "track")
        track = self._resolve_track(track_index, track_type)
        if track.name != expected_name:
            raise ValueError("Track %s is '%s', not '%s'; nothing was changed."
                             % (track_index, track.name, expected_name))
        return track

    def _named_device(self, track, device_index, expected_device_name):
        self._require_expected_name(expected_device_name, "device")
        if isinstance(device_index, bool) or not isinstance(device_index, int):
            raise TypeError("device_index must be an integer")
        devices = list(track.devices)
        if device_index < 0 or device_index >= len(devices):
            raise IndexError("device index %d out of range (the track has %d)" % (device_index, len(devices)))
        if devices[device_index].name != expected_device_name:
            raise ValueError("Device %d is '%s', not '%s'; nothing was changed."
                             % (device_index, devices[device_index].name, expected_device_name))
        return devices[device_index]

    def _insert_device(self, track_index, device_name, index=-1, track_type="track", expected_name=None):
        """Insert a native Live device by name at a chain position (-1 = the end). Instruments, effects
        and MIDI effects that exist in this edition; Live answers 'not available' for the rest."""
        try:
            track = self._named_track(track_index, expected_name, track_type)
            if not isinstance(device_name, str) or not device_name.strip():
                raise ValueError("device_name is required, e.g. 'Compressor' or 'Reverb'")
            if isinstance(index, bool) or not isinstance(index, int) or index < -1 or index > len(list(track.devices)):
                raise ValueError("index must be -1 (the end) or a position 0..%d" % len(list(track.devices)))
            if not hasattr(track, "insert_device"):
                raise RuntimeError("This version of Live has no Track.insert_device (needs Live 12.3 or newer); "
                                   "use search_browser_items and load_instrument_or_effect")
            before = [d.name for d in track.devices]
            try:
                device = track.insert_device(device_name) if index == -1 else track.insert_device(device_name, index)
            except Exception as e:
                raise ValueError(str(e).strip())
            after = [d.name for d in track.devices]
            return {"track_name": track.name, "device": getattr(device, "name", device_name),
                    "position": after.index(device.name) if device is not None and device.name in after else None,
                    "devices_before": before, "devices": after}
        except Exception as e:
            self.log_message("Error inserting device: " + str(e))
            raise

    def _move_device(self, track_index, device_index, new_index, expected_name, expected_device_name,
                     track_type="track", to_track_index=None, to_track_type="track", to_expected_name=None):
        """Move a device inside its chain, or to another track (Live refuses combinations that make no
        sense, for example an instrument after an effect). Returns the chains afterwards."""
        try:
            track = self._named_track(track_index, expected_name, track_type)
            device = self._named_device(track, device_index, expected_device_name)
            if isinstance(new_index, bool) or not isinstance(new_index, int) or new_index < 0:
                raise ValueError("new_index must be a chain position >= 0")
            target = track
            if to_track_index is not None or to_expected_name is not None:
                target = self._named_track(to_track_index, to_expected_name, to_track_type)
            if new_index > len(list(target.devices)):
                raise ValueError("new_index %d is past the end of the chain (%d devices)" % (new_index, len(list(target.devices))))
            before = [d.name for d in track.devices]
            try:
                position = self._song.move_device(device, target, new_index)
            except Exception as e:
                raise ValueError("Live refused the move: %s" % str(e).strip())
            result = {"device": expected_device_name, "from_track": track.name, "to_track": target.name,
                      "position": position, "devices_before": before,
                      "devices": [d.name for d in target.devices]}
            if target is not track:
                result["source_devices"] = [d.name for d in track.devices]
            return result
        except Exception as e:
            self.log_message("Error moving device: " + str(e))
            raise

    def _duplicate_device(self, track_index, device_index, expected_name, expected_device_name, track_type="track"):
        """Duplicate a device; the copy goes right after it."""
        try:
            track = self._named_track(track_index, expected_name, track_type)
            self._named_device(track, device_index, expected_device_name)
            before = [d.name for d in track.devices]
            try:
                track.duplicate_device(device_index)
            except Exception as e:
                raise ValueError("Live refused to duplicate the device: %s" % str(e).strip())
            return {"track_name": track.name, "devices_before": before, "devices": [d.name for d in track.devices]}
        except Exception as e:
            self.log_message("Error duplicating device: " + str(e))
            raise

    def _scale_view(self):
        song = self._song
        root = int(song.root_note)
        intervals = [int(i) for i in song.scale_intervals]
        return {"root_note": root, "root_name": self.NOTE_NAMES[root % 12],
                "scale_name": song.scale_name, "scale_mode": bool(song.scale_mode),
                "scale_intervals": intervals,
                "scale_notes": [self.NOTE_NAMES[(root + i) % 12] for i in intervals]}

    def _get_song_scale(self):
        """The set's key and scale (what Live uses to highlight in-key notes, and what Scale-aware
        devices follow): root note, scale name, whether scale mode is on, and the notes of the scale."""
        try:
            return self._scale_view()
        except Exception as e:
            self.log_message("Error reading the song scale: " + str(e))
            raise

    def _set_song_scale(self, root_note=None, scale_name=None, scale_mode=None):
        """Set the set's key and/or scale. root_note: 0-11 or a name ('C', 'F#', 'Bb'); scale_name as Live
        shows it ('Major', 'Minor', 'Dorian', 'Minor Pentatonic', 'Harmonic Minor', ...); scale_mode
        switches Live's in-key highlighting."""
        try:
            if root_note is None and scale_name is None and scale_mode is None:
                raise ValueError("Give root_note, scale_name and/or scale_mode")
            before = self._scale_view()
            if root_note is not None:
                if isinstance(root_note, bool):
                    raise TypeError("root_note must be 0-11 or a note name")
                if isinstance(root_note, str):
                    key = root_note.strip().upper()
                    if key in self.FLAT_NAMES:
                        value = self.FLAT_NAMES[key]
                    elif key.title() in self.NOTE_NAMES or key in self.NOTE_NAMES:
                        value = self.NOTE_NAMES.index(key if key in self.NOTE_NAMES else key.title())
                    else:
                        raise ValueError("Unknown root note %r (use C, C#, D, Eb, ... or 0-11)" % root_note)
                else:
                    value = int(root_note)
                if not 0 <= value <= 11:
                    raise ValueError("root_note must be 0-11 (0 = C)")
                self._song.root_note = value
            if scale_name is not None:
                if not isinstance(scale_name, str) or not scale_name.strip():
                    raise ValueError("scale_name must be a name such as 'Minor' or 'Dorian'")
                names_hint = ("Names are the ones Live shows: Major, Minor, Dorian, Mixolydian, Lydian, Phrygian, "
                              "Locrian, Whole Tone, Minor Pentatonic, Major Pentatonic, Harmonic Minor, "
                              "Melodic Minor, ...")
                previous_name = before["scale_name"]
                try:
                    self._song.scale_name = scale_name
                except Exception as e:
                    raise ValueError("Live did not accept the scale %r (%s). %s"
                                     % (scale_name, str(e).strip()[:80], names_hint))
                # Live does not raise for an unknown name: it falls back to Major. Read it back.
                if str(self._song.scale_name).lower() != scale_name.strip().lower():
                    got = self._song.scale_name
                    try:
                        self._song.scale_name = previous_name
                    except Exception:
                        pass
                    raise ValueError("Live does not know a scale called %r (it answered %r); the scale was put "
                                     "back to %r. %s" % (scale_name, got, previous_name, names_hint))
            if scale_mode is not None:
                if not isinstance(scale_mode, bool):
                    raise TypeError("scale_mode must be true or false")
                self._song.scale_mode = scale_mode
            return {"before": {k: before[k] for k in ("root_name", "scale_name", "scale_mode")},
                    "after": self._scale_view()}
        except Exception as e:
            self.log_message("Error setting the song scale: " + str(e))
            raise

    def _set_scene_tempo(self, scene_index, tempo=None, numerator=None, denominator=None, clear=False,
                         expected_name=None):
        """Give a scene its own tempo and/or time signature (launching it changes the set's), or clear them."""
        try:
            scenes = list(self._song.scenes)
            if isinstance(scene_index, bool) or not isinstance(scene_index, int) or not 0 <= scene_index < len(scenes):
                raise IndexError("scene index out of range (have %d)" % len(scenes))
            scene = scenes[scene_index]
            if expected_name is not None and scene.name != expected_name:
                raise ValueError("Scene %d is '%s', not '%s'; nothing was changed." % (scene_index, scene.name, expected_name))
            if not isinstance(clear, bool):
                raise TypeError("clear must be true or false")
            if not clear and tempo is None and numerator is None and denominator is None:
                raise ValueError("Give tempo and/or numerator and denominator, or clear=true")
            if clear:
                scene.tempo_enabled = False
                scene.time_signature_enabled = False
            else:
                if tempo is not None:
                    value = self._require_finite_number(tempo, "tempo")
                    if value < 20 or value > 999:
                        raise ValueError("tempo must be between 20 and 999 BPM")
                    scene.tempo = value
                    scene.tempo_enabled = True
                if numerator is not None or denominator is not None:
                    if numerator is None or denominator is None:
                        raise ValueError("Give both numerator and denominator")
                    for label, v in (("numerator", numerator), ("denominator", denominator)):
                        if isinstance(v, bool) or not isinstance(v, int):
                            raise TypeError("%s must be an integer" % label)
                    if not 1 <= numerator <= 99 or denominator not in (1, 2, 4, 8, 16):
                        raise ValueError("numerator 1-99 and denominator 1, 2, 4, 8 or 16")
                    scene.time_signature_numerator = numerator
                    scene.time_signature_denominator = denominator
                    scene.time_signature_enabled = True
            return {"scene_index": scene_index, "name": scene.name, "tempo": scene.tempo,
                    "tempo_enabled": bool(scene.tempo_enabled),
                    "time_signature": [scene.time_signature_numerator, scene.time_signature_denominator],
                    "time_signature_enabled": bool(scene.time_signature_enabled)}
        except Exception as e:
            self.log_message("Error setting the scene tempo: " + str(e))
            raise

    def _groove_row(self, index, g):
        return {"index": index, "name": g.name, "timing_amount": float(g.timing_amount),
                "quantization_amount": float(g.quantization_amount),
                "random_amount": float(g.random_amount), "velocity_amount": float(g.velocity_amount)}

    def _get_grooves(self):
        """The groove pool (grooves loaded in the set, with their four amounts) and the global groove
        and swing amounts. A clip uses a groove through set_clip_groove."""
        try:
            song = self._song
            pool = list(song.groove_pool.grooves)
            return {"groove_amount": float(song.groove_amount), "swing_amount": float(song.swing_amount),
                    "grooves": [self._groove_row(i, g) for i, g in enumerate(pool)]}
        except Exception as e:
            self.log_message("Error reading the grooves: " + str(e))
            raise

    def _set_groove(self, groove_index=None, timing_amount=None, quantization_amount=None,
                    random_amount=None, velocity_amount=None, groove_amount=None):
        """Change one groove's amounts and/or the global groove amount. Returns the values read back."""
        try:
            fields = (("timing_amount", timing_amount), ("quantization_amount", quantization_amount),
                      ("random_amount", random_amount), ("velocity_amount", velocity_amount))
            if groove_amount is None and all(v is None for _, v in fields):
                raise ValueError("Give groove_amount (global) and/or the amounts of one groove")
            if groove_amount is not None:
                value = self._require_finite_number(groove_amount, "groove_amount")
                if value < 0 or value > 1.3:
                    raise ValueError("groove_amount is 0 to 1.3 (1.0 = 100%)")
                self._song.groove_amount = value
            if any(v is not None for _, v in fields):
                pool = list(self._song.groove_pool.grooves)
                if isinstance(groove_index, bool) or not isinstance(groove_index, int) or not 0 <= groove_index < len(pool):
                    raise IndexError("groove_index required, 0..%d (read get_grooves)" % (len(pool) - 1))
                groove = pool[groove_index]
                for label, v in fields:
                    if v is not None:
                        setattr(groove, label, self._require_finite_number(v, label))
            return self._get_grooves()
        except Exception as e:
            self.log_message("Error setting the groove: " + str(e))
            raise

    def _set_clip_groove(self, track_index, clip_index, groove_index=None, clip_start_time=None):
        """Give a clip a groove from the pool. The API cannot take a groove away (Live refuses None); a new clip
        may already report the pool's groove, which does nothing while the global groove amount is 0."""
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            pool = list(self._song.groove_pool.grooves)
            before = clip.groove.name if getattr(clip, "has_groove", False) and clip.groove is not None else None
            if groove_index is None:
                raise ValueError("groove_index is required: Live's API cannot take a groove away from a clip "
                                 "(it refuses None). To silence one, set its timing, random and velocity amounts to "
                                 "0 with set_groove, or the global groove_amount to 0, or choose None by hand in "
                                 "the clip's Groove box.")
            if isinstance(groove_index, bool) or not isinstance(groove_index, int) or not 0 <= groove_index < len(pool):
                raise IndexError("groove_index must be 0..%d (read get_grooves)" % (len(pool) - 1))
            clip.groove = pool[groove_index]
            now = clip.groove.name if getattr(clip, "has_groove", False) and clip.groove is not None else None
            return {"track_name": track.name, "clip_name": clip.name, "groove_before": before, "groove": now}
        except Exception as e:
            self.log_message("Error setting the clip groove: " + str(e))
            raise

    def _warp_marker_rows(self, clip):
        return [{"beat_time": round(float(m.beat_time), 4), "seconds": round(float(m.sample_time), 4)}
                for m in clip.warp_markers]

    def _edit_warp_marker(self, track_index, clip_index, action, beat_time=None, seconds=None,
                          distance=None, clip_start_time=None):
        """Edit the warp markers of a warped audio clip, to line a recording up with the grid.

        action "add": the audio at `seconds` into the FILE plays at `beat_time` (clip beats). "move": the
        marker at `beat_time` moves by `distance` beats (later or earlier). "remove": the marker at
        `beat_time`. The reply has the markers afterwards. Time stretches the audio between markers.
        """
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            if not getattr(clip, "is_audio_clip", False):
                raise ValueError("Warp markers belong to audio clips")
            if not clip.warping:
                raise ValueError("The clip is not warped; turn warping on with set_audio_clip_warp first")
            if action not in ("add", "move", "remove"):
                raise ValueError("action must be 'add', 'move' or 'remove'")
            beat = self._require_finite_number(beat_time, "beat_time")
            before = self._warp_marker_rows(clip)
            if action == "add":
                secs = self._require_finite_number(seconds, "seconds")
                if secs < 0:
                    raise ValueError("seconds must be >= 0 (position inside the audio file)")
                try:
                    import Live
                    marker = Live.Clip.WarpMarker(secs, beat)
                except Exception:
                    marker = types.SimpleNamespace(sample_time=secs, beat_time=beat)
                clip.add_warp_marker(marker)
            elif action == "move":
                dist = self._require_finite_number(distance, "distance")
                if not any(abs(m["beat_time"] - beat) < 1e-3 for m in before):
                    raise ValueError("No warp marker at beat %s. Markers: %s"
                                     % (beat, ", ".join(str(m["beat_time"]) for m in before)))
                clip.move_warp_marker(beat, dist)
            else:
                if not any(abs(m["beat_time"] - beat) < 1e-3 for m in before):
                    raise ValueError("No warp marker at beat %s. Markers: %s"
                                     % (beat, ", ".join(str(m["beat_time"]) for m in before)))
                clip.remove_warp_marker(beat)
            return {"track_name": track.name, "clip_name": clip.name, "action": action,
                    "markers_before": before, "markers": self._warp_marker_rows(clip)}
        except Exception as e:
            self.log_message("Error editing a warp marker: " + str(e))
            raise

    def _duplicate_clip_loop(self, track_index, clip_index, clip_start_time=None):
        """Make a MIDI clip's loop twice as long, copying its notes (and envelopes) into the new half.
        Undoable. The loop of an Arrangement clip is its content loop; its extent on the timeline is unchanged."""
        try:
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)
            before = {"loop_end": float(clip.loop_end), "length": float(clip.length), "notes": self._count_clip_notes(clip)}
            clip.duplicate_loop()
            after = {"loop_end": float(clip.loop_end), "length": float(clip.length), "notes": self._count_clip_notes(clip)}
            return {"track_name": track.name, "clip_name": clip.name, "before": before, "after": after}
        except Exception as e:
            self.log_message("Error duplicating the clip loop: " + str(e))
            raise

    def _copy_note_region(self, track_index, clip_index, region_start, region_length, destination_time,
                          pitch=-1, transposition=0, clip_start_time=None):
        """Copy the notes inside a stretch of a MIDI clip to another time in the same clip, optionally of
        one pitch only and transposed by semitones: repeat a motif a fifth higher with transposition=7."""
        try:
            track, clip = self._session_clip(track_index, clip_index, midi=True, clip_start_time=clip_start_time)
            start = self._require_finite_number(region_start, "region_start")
            length = self._require_finite_number(region_length, "region_length")
            dest = self._require_finite_number(destination_time, "destination_time")
            clip_len = float(clip.length)
            if start < 0 or length <= 0 or start + length > clip_len + 1e-9:
                raise ValueError("The region must lie inside the clip (0 to %s beats)" % clip_len)
            if dest < 0 or dest >= clip_len - 1e-9:
                raise ValueError("destination_time must start inside the clip (0 to %s beats): a copy at or after "
                                 "the end would never play" % clip_len)
            if isinstance(pitch, bool) or not isinstance(pitch, int) or not -1 <= pitch <= 127:
                raise ValueError("pitch must be -1 (all pitches) or 0-127")
            if isinstance(transposition, bool) or not isinstance(transposition, int) or not -127 <= transposition <= 127:
                raise ValueError("transposition must be an integer number of semitones")
            before = self._count_clip_notes(clip)
            clip.duplicate_region(start, length, dest, pitch, transposition)
            after = self._count_clip_notes(clip)
            return {"track_name": track.name, "clip_name": clip.name, "notes_before": before,
                    "notes_after": after, "copied": (after - before) if before is not None and after is not None else None}
        except Exception as e:
            self.log_message("Error copying a note region: " + str(e))
            raise

    def _copy_clip_to_slot(self, track_index, clip_index, to_track_index, to_clip_index, overwrite=False):
        """Copy a Session clip into another slot (the same track, or another track of the same kind).
        The destination slot must be empty unless overwrite is true."""
        try:
            if not isinstance(overwrite, bool):
                raise TypeError("overwrite must be true or false")
            track, clip = self._session_clip(track_index, clip_index)
            for label, v in (("to_track_index", to_track_index), ("to_clip_index", to_clip_index)):
                if isinstance(v, bool) or not isinstance(v, int):
                    raise TypeError("%s must be an integer" % label)
            if to_track_index < 0 or to_track_index >= len(self._song.tracks):
                raise IndexError("to_track_index out of range")
            dest_track = self._song.tracks[to_track_index]
            if to_clip_index < 0 or to_clip_index >= len(dest_track.clip_slots):
                raise IndexError("to_clip_index out of range")
            dest = dest_track.clip_slots[to_clip_index]
            if dest.has_clip:
                if not overwrite:
                    raise ValueError("Slot %d of '%s' already holds a clip ('%s'); pass overwrite=true to replace it"
                                     % (to_clip_index, dest_track.name, dest.clip.name))
                dest.delete_clip()
            try:
                track.clip_slots[clip_index].duplicate_clip_to(dest)
            except Exception as e:
                raise ValueError("Live refused to copy the clip: %s" % str(e).strip())
            return {"from": "%s / slot %d" % (track.name, clip_index),
                    "to": "%s / slot %d" % (dest_track.name, to_clip_index),
                    "copied": bool(dest.has_clip), "clip_name": dest.clip.name if dest.has_clip else None}
        except Exception as e:
            self.log_message("Error copying a clip to a slot: " + str(e))
            raise

    SIMPLER_MODES = {"classic": 0, "one-shot": 1, "oneshot": 1, "slicing": 2}
    SIMPLER_SLICING = {"mono": 0, "poly": 1, "thru": 2}

    def _simpler_state(self, device):
        state = {"device": device.name, "class": device.class_name}
        for key, attr, names in (("playback_mode", "playback_mode", self.SIMPLER_MODES),
                                 ("slicing_playback_mode", "slicing_playback_mode", self.SIMPLER_SLICING)):
            try:
                value = int(getattr(device, attr))
                state[key] = next((n for n, v in names.items() if v == value and n != "oneshot"), value)
            except Exception:
                pass
        try:
            state["retrigger"] = bool(device.retrigger)
        except Exception:
            pass
        try:
            state["sample_file"] = device.sample.file_path
        except Exception:
            state["sample_file"] = None
        return state

    def _configure_simpler(self, track_index, device_index, expected_name, expected_device_name,
                           sample_path=None, playback_mode=None, retrigger=None,
                           slicing_playback_mode=None, track_type="track"):
        """Put a sample of your own into a Simpler and set how it plays.

        sample_path: absolute path of an audio file (replaces the loaded sample; the file's own timing).
        playback_mode: "classic" (key held plays it, envelopes shape it), "one-shot" (plays to the end
        on a note-on, a drum hit) or "slicing". retrigger: a repeated note restarts the sample.
        slicing_playback_mode: "mono", "poly" or "thru". Returns the state read back.
        """
        try:
            track = self._named_track(track_index, expected_name, track_type)
            device = self._named_device(track, device_index, expected_device_name)
            if getattr(device, "class_name", "") != "OriginalSimpler":
                raise ValueError("Device '%s' is a %s, not a Simpler (class OriginalSimpler)"
                                 % (device.name, getattr(device, "class_name", "?")))
            if sample_path is None and playback_mode is None and retrigger is None and slicing_playback_mode is None:
                raise ValueError("Give sample_path, playback_mode, retrigger and/or slicing_playback_mode")
            before = self._simpler_state(device)
            if sample_path is not None:
                if not isinstance(sample_path, str) or not os.path.isabs(sample_path) or not os.path.isfile(sample_path):
                    raise ValueError("sample_path must be the absolute path of an existing audio file, got %r" % (sample_path,))
                if not hasattr(device, "replace_sample"):
                    raise RuntimeError("This version of Live has no Simpler.replace_sample")
                try:
                    device.replace_sample(sample_path)
                except Exception as e:
                    raise ValueError("Live could not load that file into the Simpler: %s" % str(e).strip()[:120])
            if playback_mode is not None:
                key = str(playback_mode).strip().lower()
                if key not in self.SIMPLER_MODES:
                    raise ValueError("playback_mode must be classic, one-shot or slicing")
                device.playback_mode = self.SIMPLER_MODES[key]
            if retrigger is not None:
                if not isinstance(retrigger, bool):
                    raise TypeError("retrigger must be true or false")
                device.retrigger = retrigger
            if slicing_playback_mode is not None:
                key = str(slicing_playback_mode).strip().lower()
                if key not in self.SIMPLER_SLICING:
                    raise ValueError("slicing_playback_mode must be mono, poly or thru")
                device.slicing_playback_mode = self.SIMPLER_SLICING[key]
            return {"track_name": track.name, "before": before, "after": self._simpler_state(device)}
        except Exception as e:
            self.log_message("Error configuring the Simpler: " + str(e))
            raise

    # ── A/B compare, clip automation overview, crop, take lanes, UI state, song state ──
    # Measured on Live 12.4 Lite (2026-10-24): Device.save_preset_to_compare_ab_slot copies the
    # current settings into the OTHER slot, is_using_compare_preset_b then swaps between the two;
    # Clip.automation_envelopes lists the automated parameters (each envelope has .parameter);
    # Song.View and Application.View accept the selections written below; TakeLane has a name and
    # arrangement_clips; Application.show_on_the_fly_message opens a MODAL dialog that blocks Live's
    # main thread, so it is not offered.

    AB_ACTIONS = ("status", "save", "switch", "use_a", "use_b")

    def _compare_device_ab(self, track_index, device_index, expected_name, expected_device_name,
                           action="status", track_type="track"):
        """A/B compare of a device's settings (the small A/B button in its title bar).

        status: say which slot is in use. save: copy the CURRENT settings into the other slot (then
        change the current ones and `switch` to compare). switch / use_a / use_b: change slot.
        """
        try:
            track = self._named_track(track_index, expected_name, track_type)
            device = self._named_device(track, device_index, expected_device_name)
            key = str(action).strip().lower()
            if key not in self.AB_ACTIONS:
                raise ValueError("action must be one of %s" % ", ".join(self.AB_ACTIONS))
            if not getattr(device, "can_compare_ab", False):
                raise ValueError("Device '%s' has no A/B compare" % device.name)
            was_b = bool(device.is_using_compare_preset_b)
            if key == "save":
                device.save_preset_to_compare_ab_slot()
            elif key == "switch":
                device.is_using_compare_preset_b = not was_b
            elif key in ("use_a", "use_b"):
                device.is_using_compare_preset_b = key == "use_b"
            now_b = bool(device.is_using_compare_preset_b)
            return {"track_name": track.name, "device": device.name, "action": key,
                    "was_on": "B" if was_b else "A", "now_on": "B" if now_b else "A"}
        except Exception as e:
            self.log_message("Error comparing a device A/B: " + str(e))
            raise

    def _clip_envelope_owner(self, track, parameter):
        """Where an automated parameter lives: the mixer or one of the track's devices."""
        mixer = track.mixer_device
        mixer_params = [("volume", mixer.volume), ("pan", mixer.panning)]
        mixer_params += [("send " + chr(ord("A") + i), s) for i, s in enumerate(mixer.sends)]
        for label, p in mixer_params:
            if p == parameter:
                return {"parameter": label, "owner": "mixer"}
        for device_index, device in enumerate(track.devices):
            for p in device.parameters:
                if p == parameter:
                    return {"parameter": p.name, "owner": "device", "device_index": device_index,
                            "device_name": device.name}
        return {"parameter": self._safe_attr(parameter, "name", str, "?"), "owner": "unknown"}

    def _list_clip_envelopes(self, track_index, clip_index):
        """Which parameters of a Session clip are automated (name and owner), nothing else."""
        try:
            track, clip = self._envelope_clip(track_index, clip_index, None, False, None)
            envelopes = list(getattr(clip, "automation_envelopes", None) or [])
            rows = []
            for env in envelopes:
                row = self._clip_envelope_owner(track, env.parameter)
                row["min"], row["max"] = float(env.parameter.min), float(env.parameter.max)
                rows.append(row)
            return {"track_name": track.name, "clip_name": clip.name, "count": len(rows),
                    "envelopes": rows}
        except Exception as e:
            self.log_message("Error listing clip envelopes: " + str(e))
            raise

    def _clear_all_clip_envelopes(self, track_index, clip_index, expected_name, confirm=False):
        """Preview or remove ALL of a Session clip's automation (Live's undo can bring it back)."""
        try:
            do_apply = self._require_confirm_flag(confirm)
            self._require_expected_name(expected_name, "track")
            track, clip = self._envelope_clip(track_index, clip_index, expected_name, False, None)
            before = self._list_clip_envelopes(track_index, clip_index)
            info = {"track_name": track.name, "clip_name": clip.name, "would_remove": before["envelopes"],
                    "applied": False, "dry_run": not do_apply}
            if not do_apply:
                return info
            clip.clear_all_envelopes()
            info["applied"] = True
            info["remaining"] = len(list(getattr(clip, "automation_envelopes", None) or []))
            return info
        except Exception as e:
            self.log_message("Error clearing all clip envelopes: " + str(e))
            raise

    def _crop_clip(self, track_index, clip_index, expected_name, confirm=False, clip_start_time=None):
        """Preview or crop a clip to its loop (looping) or to its start and end markers (not looping).

        Everything outside is thrown away: notes, and for an audio clip the audio itself becomes a
        new, shorter file. Live's undo can bring it back.
        """
        try:
            do_apply = self._require_confirm_flag(confirm)
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            self._require_expected_name(expected_name, "track")
            if track.name != expected_name:
                raise ValueError("Track %s is '%s', not '%s'; nothing was changed."
                                 % (track_index, track.name, expected_name))
            looping = bool(getattr(clip, "looping", False))
            keep = ((float(clip.loop_start), float(clip.loop_end)) if looping
                    else (float(clip.start_marker), float(clip.end_marker)))
            info = {"track_name": track.name, "clip_name": clip.name, "is_audio_clip": bool(clip.is_audio_clip),
                    "looping": looping, "keeps_from": keep[0], "keeps_to": keep[1],
                    "length_before": float(clip.length), "applied": False, "dry_run": not do_apply}
            if not do_apply:
                return info
            clip.crop()
            info["applied"] = True
            info["length_after"] = float(clip.length)
            return info
        except Exception as e:
            self.log_message("Error cropping a clip: " + str(e))
            raise

    def _get_take_lanes(self, track_index):
        """The take lanes of a track and the clips each holds (the takes of a comp)."""
        try:
            track = self._resolve_track(track_index, "track")
            if getattr(track, "is_foldable", False):
                raise ValueError("Track '%s' is a group track and has no take lanes" % track.name)
            lanes = []
            for lane_index, lane in enumerate(list(getattr(track, "take_lanes", None) or [])):
                clips = []
                for clip in list(getattr(lane, "arrangement_clips", None) or []):
                    clips.append({"name": clip.name, "start_time": float(clip.start_time),
                                  "end_time": float(clip.end_time), "is_audio_clip": bool(clip.is_audio_clip)})
                lanes.append({"index": lane_index, "name": self._safe_attr(lane, "name", str, ""),
                              "clip_count": len(clips), "clips": clips})
            return {"track_index": track_index, "track_name": track.name, "lane_count": len(lanes),
                    "lanes": lanes}
        except Exception as e:
            self.log_message("Error reading take lanes: " + str(e))
            raise

    def _create_take_lane(self, track_index, expected_name):
        """Add an empty take lane to a track (Live's undo removes it)."""
        try:
            track = self._named_track(track_index, expected_name)
            if getattr(track, "is_foldable", False) or not hasattr(track, "create_take_lane"):
                raise ValueError("Track '%s' cannot have take lanes" % track.name)
            before = len(list(track.take_lanes))
            track.create_take_lane()
            return {"track_name": track.name, "lanes_before": before, "lanes_after": len(list(track.take_lanes))}
        except Exception as e:
            self.log_message("Error creating a take lane: " + str(e))
            raise

    def _set_track_fold(self, track_index, expected_name, folded):
        """Fold (collapse) or unfold a group track in the Arrangement and Session."""
        try:
            track = self._named_track(track_index, expected_name)
            if not getattr(track, "is_foldable", False):
                raise ValueError("Track '%s' is not a group track; only groups fold" % track.name)
            if not isinstance(folded, bool):
                raise TypeError("folded must be true or false")
            before = bool(track.fold_state)
            track.fold_state = folded
            return {"track_name": track.name, "was_folded": before, "folded": bool(track.fold_state)}
        except Exception as e:
            self.log_message("Error folding a group: " + str(e))
            raise

    UI_VIEWS = ("Browser", "Arranger", "Session", "Detail", "Detail/Clip", "Detail/DeviceChain")

    def _track_reference(self, track):
        """{kind, index} of a track, return track or the master, or None."""
        song = self._song
        for kind, tracks in (("track", song.tracks), ("return", song.return_tracks)):
            for i, t in enumerate(tracks):
                if t == track:
                    return {"track_type": kind, "index": i, "name": t.name}
        if track == song.master_track:
            return {"track_type": "master", "index": None, "name": song.master_track.name}
        return None

    def _get_ui_state(self):
        """What the user is looking at: the focused view, which panels are open, the selected track,
        scene, clip, device and parameter. Each field is read on its own."""
        app = self.application()
        view, sv, song = app.view, self._song.view, self._song
        info = {}

        def put(key, fn):
            try:
                info[key] = fn()
            except Exception:
                info[key] = None

        put("focused_view", lambda: str(view.focused_document_view))
        put("open_views", lambda: [name for name in self.UI_VIEWS if view.is_view_visible(name)])
        put("selected_track", lambda: self._track_reference(sv.selected_track))
        put("selected_scene", lambda: next((i for i, sc in enumerate(song.scenes) if sc == sv.selected_scene), None))

        def detail_clip():
            clip = sv.detail_clip
            if clip is None:
                return None
            row = {"name": clip.name, "is_arrangement_clip": bool(clip.is_arrangement_clip),
                   "start_time": float(clip.start_time) if clip.is_arrangement_clip else None}
            for i, t in enumerate(song.tracks):
                found = [k for k, slot in enumerate(t.clip_slots) if slot.has_clip and slot.clip == clip]
                if found:
                    row.update({"track_index": i, "track_name": t.name, "clip_index": found[0]})
                    break
                if clip.is_arrangement_clip and any(c == clip for c in t.arrangement_clips):
                    row.update({"track_index": i, "track_name": t.name})
                    break
            return row

        put("detail_clip", detail_clip)
        put("selected_parameter", lambda: (sv.selected_parameter.name if sv.selected_parameter is not None else None))
        put("selected_device", lambda: (sv.selected_track.view.selected_device.name
                                        if sv.selected_track.view.selected_device is not None else None))
        put("follow_song", lambda: bool(sv.follow_song))
        put("draw_mode", lambda: bool(sv.draw_mode))
        return info

    def _show_in_ui(self, track_index=None, track_type="track", scene_index=None, clip_index=None,
                    device_index=None, view_name=None, envelope_parameter=None, envelope_device_index=None):
        """Move Live's own selection and views, so the user sees what is being talked about.

        track_index (+track_type): select that track. scene_index: select that scene. clip_index: select
        that Session clip and show it in the Detail view (needs track_index). device_index: select that
        device of the track and show the device chain. view_name: focus Arranger, Session, Browser, or
        a Detail panel ("Detail/Clip", "Detail/DeviceChain"). envelope_parameter (with clip_index): show
        that parameter's automation in the clip's envelope view. Nothing in the Set changes.
        """
        try:
            app = self.application()
            sv = self._song.view
            did = []
            track = None
            if track_index is not None:
                track = self._resolve_track(track_index, track_type)
                sv.selected_track = track
                did.append("track '%s'" % track.name)
            if scene_index is not None:
                scenes = list(self._song.scenes)
                if isinstance(scene_index, bool) or not isinstance(scene_index, int) or not 0 <= scene_index < len(scenes):
                    raise IndexError("scene_index out of range (the Set has %d scenes)" % len(scenes))
                sv.selected_scene = scenes[scene_index]
                did.append("scene %d" % scene_index)
            if clip_index is not None:
                if track is None or (track_type or "track") != "track":
                    raise ValueError("clip_index needs a regular track_index")
                if isinstance(clip_index, bool) or not isinstance(clip_index, int) or not 0 <= clip_index < len(track.clip_slots):
                    raise IndexError("clip_index out of range")
                slot = track.clip_slots[clip_index]
                sv.highlighted_clip_slot = slot
                if slot.has_clip:
                    sv.detail_clip = slot.clip
                    did.append("clip %d" % clip_index)
                    if envelope_parameter is not None:
                        target = self._automation_target(track, envelope_parameter, envelope_device_index)
                        slot.clip.view.show_envelope()
                        slot.clip.view.select_envelope_parameter(target)
                        did.append("envelope '%s'" % target.name)
                else:
                    did.append("empty slot %d" % clip_index)
            if device_index is not None:
                if track is None:
                    raise ValueError("device_index needs track_index")
                devices = list(track.devices)
                if isinstance(device_index, bool) or not isinstance(device_index, int) or not 0 <= device_index < len(devices):
                    raise IndexError("device_index out of range (the track has %d devices)" % len(devices))
                sv.select_device(devices[device_index])
                did.append("device '%s'" % devices[device_index].name)
            if view_name is not None:
                wanted = [n for n in self.UI_VIEWS if n.lower() == str(view_name).strip().lower()]
                if not wanted:
                    raise ValueError("view_name must be one of %s" % ", ".join(self.UI_VIEWS))
                app.view.focus_view(wanted[0])
                did.append("view %s" % wanted[0])
            if not did:
                raise ValueError("Give something to show: track_index, scene_index, clip_index, device_index or view_name")
            state = self._get_ui_state()
            state["did"] = did
            return state
        except Exception as e:
            self.log_message("Error showing something in Live: " + str(e))
            raise

    def _re_enable_automation(self):
        """Give automation back to the lanes: Live's 'Re-Enable Automation' button (an automated
        parameter that was moved by hand stops following its lane until this)."""
        try:
            song = self._song
            before = bool(song.re_enable_automation_enabled)
            if before:
                song.re_enable_automation()
            return {"was_needed": before, "needed_now": bool(song.re_enable_automation_enabled)}
        except Exception as e:
            self.log_message("Error re-enabling automation: " + str(e))
            raise

    def _capture_midi(self, destination="auto"):
        """Capture the MIDI just played (on an armed or monitored MIDI track) into a clip, like Live's
        Capture MIDI button. Needs material: can_capture_midi must be true."""
        try:
            song = self._song
            key = str(destination).strip().lower()
            if key not in ("auto", "session", "arrangement"):
                raise ValueError("destination must be auto, session or arrangement")
            if not hasattr(song, "capture_midi"):
                raise RuntimeError("This version of Live has no Song.capture_midi")
            if not bool(song.can_capture_midi):
                raise ValueError("Nothing to capture: Live has heard no MIDI played on a monitored MIDI "
                                 "track (arm a MIDI track, play, then call this)")
            import Live
            song.capture_midi(getattr(Live.Song.CaptureDestination, key))
            return {"captured": True, "destination": key, "can_capture_midi_now": bool(song.can_capture_midi)}
        except Exception as e:
            self.log_message("Error capturing MIDI: " + str(e))
            raise


    # ── Transport options, return delete, drum pads, macro variations, previews, plug-in windows ──
    # Measured on Live 12.4 Lite (2026-10-24): Song flags such as punch_in, punch_out and
    # arrangement_overdub are applied on the NEXT tick (a read in the same call still shows the old
    # value), so the writer waits and reads back; Song.delete_return_track(index); DrumPad has note,
    # name, mute, solo, chains; Rack.store_variation adds a variation (selected_variation_index must
    # be set before recall_selected_variation); PluginDevice.is_editor_open opens and closes the
    # plug-in's own window; Browser.preview_item / stop_preview play an item.

    CLIP_TRIGGER_QUANTIZATION = [
        ("none", "q_no_q"), ("8 bars", "q_8_bars"), ("4 bars", "q_4_bars"), ("2 bars", "q_2_bars"),
        ("bar", "q_bar"), ("half", "q_half"), ("half triplet", "q_half_triplet"),
        ("quarter", "q_quarter"), ("quarter triplet", "q_quarter_triplet"), ("eighth", "q_eight"),
        ("eighth triplet", "q_eight_triplet"), ("sixteenth", "q_sixtenth"),
        ("sixteenth triplet", "q_sixtenth_triplet"), ("thirtysecond", "q_thirtytwoth")]
    MIDI_RECORDING_QUANTIZATION = [
        ("none", "rec_q_no_q"), ("quarter", "rec_q_quarter"), ("eighth", "rec_q_eight"),
        ("eighth triplet", "rec_q_eight_triplet"), ("eighth and eighth triplet", "rec_q_eight_eight_triplet"),
        ("sixteenth", "rec_q_sixtenth"), ("sixteenth triplet", "rec_q_sixtenth_triplet"),
        ("sixteenth and sixteenth triplet", "rec_q_sixtenth_sixtenth_triplet"),
        ("thirtysecond", "rec_q_thirtysecond")]

    def _quantization_name(self, table, value):
        import Live
        owner = Live.Song.Quantization if table is self.CLIP_TRIGGER_QUANTIZATION else Live.Song.RecordingQuantization
        for name, attr in table:
            if getattr(owner, attr, None) is not None and int(getattr(owner, attr)) == int(value):
                return name
        return int(value)

    def _quantization_value(self, table, name, label):
        import Live
        owner = Live.Song.Quantization if table is self.CLIP_TRIGGER_QUANTIZATION else Live.Song.RecordingQuantization
        key = str(name).strip().lower().replace("_", " ")
        for label_name, attr in table:
            if label_name == key:
                return getattr(owner, attr)
        raise ValueError("%s must be one of: %s" % (label, ", ".join(n for n, _ in table)))

    def _transport_options_state(self):
        song = self._song
        return {"punch_in": bool(song.punch_in), "punch_out": bool(song.punch_out),
                "arrangement_overdub": bool(song.arrangement_overdub),
                "clip_trigger_quantization": self._quantization_name(
                    self.CLIP_TRIGGER_QUANTIZATION, song.clip_trigger_quantization),
                "midi_recording_quantization": self._quantization_name(
                    self.MIDI_RECORDING_QUANTIZATION, song.midi_recording_quantization),
                "loop": bool(song.loop), "count_in_duration": int(song.count_in_duration)}

    def _set_transport_options(self, punch_in=None, punch_out=None, arrangement_overdub=None,
                               clip_trigger_quantization=None, midi_recording_quantization=None):
        """Read (no arguments) or set the recording and launch options: punch in/out, Arrangement
        overdub, the clip launch quantization and the quantization of recorded MIDI. Does NOT start
        recording. Live applies these on the next tick, so the change is read back after a short wait."""
        try:
            wanted = {}
            for key, value in (("punch_in", punch_in), ("punch_out", punch_out),
                               ("arrangement_overdub", arrangement_overdub)):
                if value is not None:
                    if not isinstance(value, bool):
                        raise TypeError("%s must be true or false" % key)
                    wanted[key] = value
            if clip_trigger_quantization is not None:
                wanted["clip_trigger_quantization"] = clip_trigger_quantization
            if midi_recording_quantization is not None:
                wanted["midi_recording_quantization"] = midi_recording_quantization

            def first():
                state = self._transport_options_state()
                song = self._song
                # both names are checked before anything is set, so a bad one changes nothing
                trigger = (self._quantization_value(
                    self.CLIP_TRIGGER_QUANTIZATION, wanted["clip_trigger_quantization"], "clip_trigger_quantization")
                    if "clip_trigger_quantization" in wanted else None)
                recording = (self._quantization_value(
                    self.MIDI_RECORDING_QUANTIZATION, wanted["midi_recording_quantization"],
                    "midi_recording_quantization") if "midi_recording_quantization" in wanted else None)
                for key in ("punch_in", "punch_out", "arrangement_overdub"):
                    if key in wanted:
                        setattr(song, key, wanted[key])
                if trigger is not None:
                    song.clip_trigger_quantization = trigger
                if recording is not None:
                    song.midi_recording_quantization = recording
                return state

            before = self._call_on_main_thread(first)
            if wanted:
                time.sleep(0.3)
            after = self._call_on_main_thread(self._transport_options_state)
            result = {"before": before, "after": after}
            if wanted:
                def norm(v):
                    return str(v).strip().lower().replace("_", " ") if isinstance(v, str) else v
                result["not_applied"] = [k for k, v in wanted.items() if norm(after.get(k)) != norm(v)]
            return result
        except Exception as e:
            self.log_message("Error with the transport options: " + str(e))
            raise

    def _delete_return_track(self, index, expected_name, confirm=False):
        """Preview or delete one return track (its sends vanish from every track; undo brings it back)."""
        try:
            do_apply = self._require_confirm_flag(confirm)
            self._require_expected_name(expected_name, "return track")
            returns = list(self._song.return_tracks)
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(returns):
                raise IndexError("return index %r out of range (the Set has %d return tracks)" % (index, len(returns)))
            track = returns[index]
            if track.name != expected_name:
                raise ValueError("Return %d is '%s', not '%s'; nothing was deleted."
                                 % (index, track.name, expected_name))
            info = {"index": index, "name": track.name, "devices": [d.name for d in track.devices],
                    "tracks_sending_to_it": sum(1 for t in self._song.tracks
                                                if index < len(list(t.mixer_device.sends))
                                                and float(list(t.mixer_device.sends)[index].value) > 0.0),
                    "applied": False, "dry_run": not do_apply}
            if not do_apply:
                return info
            self._song.delete_return_track(index)
            info["applied"] = True
            info["return_tracks_after"] = self._return_tracks_summary()
            return info
        except Exception as e:
            self.log_message("Error deleting a return track: " + str(e))
            raise

    def _rack_device(self, track_index, device_index, expected_name, expected_device_name, track_type="track"):
        track = self._named_track(track_index, expected_name, track_type)
        return track, self._named_device(track, device_index, expected_device_name)

    def _get_drum_pads(self, track_index, device_index, track_type="track", include_empty=False):
        """The pads of a Drum Rack: the MIDI note, name, mute, solo and how many chains each holds.
        Empty pads are left out unless include_empty."""
        try:
            track = self._resolve_track(track_index, track_type)
            devices = list(track.devices)
            if isinstance(device_index, bool) or not isinstance(device_index, int) or not 0 <= device_index < len(devices):
                raise IndexError("device index out of range (the track has %d)" % len(devices))
            device = devices[device_index]
            if not getattr(device, "can_have_drum_pads", False):
                raise ValueError("Device '%s' is not a Drum Rack" % device.name)
            pads = []
            for pad in list(device.drum_pads):
                chains = list(pad.chains)
                if chains or include_empty:
                    pads.append({"note": int(pad.note), "name": pad.name, "mute": bool(pad.mute), "solo": bool(pad.solo),
                                 "chain_count": len(chains),
                                 "devices": [d.name for c in chains for d in c.devices][:6]})
            visible = [int(p.note) for p in list(device.visible_drum_pads)]
            return {"track_name": track.name, "device": device.name, "pad_count_with_sound": sum(
                1 for pad in device.drum_pads if list(pad.chains)), "visible_notes": visible, "pads": pads}
        except Exception as e:
            self.log_message("Error reading drum pads: " + str(e))
            raise

    def _set_drum_pad(self, track_index, device_index, expected_name, expected_device_name, note,
                      mute=None, solo=None, track_type="track"):
        """Mute and/or solo one pad of a Drum Rack, by its MIDI note (36 is the first pad)."""
        try:
            track, device = self._rack_device(track_index, device_index, expected_name, expected_device_name, track_type)
            if not getattr(device, "can_have_drum_pads", False):
                raise ValueError("Device '%s' is not a Drum Rack" % device.name)
            if mute is None and solo is None:
                raise ValueError("Give mute and/or solo")
            for key, value in (("mute", mute), ("solo", solo)):
                if value is not None and not isinstance(value, bool):
                    raise TypeError("%s must be true or false" % key)
            if isinstance(note, bool) or not isinstance(note, int):
                raise TypeError("note must be a MIDI note number")
            pads = [p for p in device.drum_pads if int(p.note) == note]
            if not pads:
                raise ValueError("The Drum Rack has no pad for MIDI note %d" % note)
            pad = pads[0]
            if not list(pad.chains):
                raise ValueError("The pad for note %d has no sound; Live does not mute or solo an empty pad" % note)
            before = {"mute": bool(pad.mute), "solo": bool(pad.solo)}
            if mute is not None:
                pad.mute = mute
            if solo is not None:
                pad.solo = solo
            return {"track_name": track.name, "device": device.name, "note": note, "pad": pad.name,
                    "before": before, "after": {"mute": bool(pad.mute), "solo": bool(pad.solo)}}
        except Exception as e:
            self.log_message("Error setting a drum pad: " + str(e))
            raise

    RACK_ACTIONS = ("status", "store", "recall", "delete", "randomize")

    def _rack_variations(self, track_index, device_index, expected_name, expected_device_name,
                         action="status", index=None, confirm=False, track_type="track"):
        """The macro variations of an Instrument/Audio Effect/Drum Rack: store the current macro
        settings as a variation, recall one, delete one, or randomize the macros.

        delete and randomize preview unless confirm is exactly True. recall and delete need index.
        """
        try:
            track, device = self._rack_device(track_index, device_index, expected_name, expected_device_name, track_type)
            key = str(action).strip().lower()
            if key not in self.RACK_ACTIONS:
                raise ValueError("action must be one of %s" % ", ".join(self.RACK_ACTIONS))
            if not hasattr(device, "store_variation"):
                raise ValueError("Device '%s' is not a rack with macro variations" % device.name)

            def macros():
                return [{"name": p.name, "value": float(p.value)} for p in device.parameters
                        if str(p.name).startswith("Macro")]

            def state():
                return {"variation_count": int(device.variation_count),
                        "selected_variation_index": int(device.selected_variation_index),
                        "has_macro_mappings": bool(device.has_macro_mappings), "macros": macros()}

            before = state()
            info = {"track_name": track.name, "device": device.name, "action": key, "before": before}
            if key in ("recall", "delete"):
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < before["variation_count"]:
                    raise IndexError("index must be a variation 0..%d (the rack has %d)"
                                     % (before["variation_count"] - 1, before["variation_count"]))
            do_apply = True
            if key in ("delete", "randomize"):
                do_apply = self._require_confirm_flag(confirm)
                info["dry_run"] = not do_apply
            if not do_apply:
                info["applied"] = False
                return info
            if key == "store":
                device.store_variation()
                if not before["has_macro_mappings"]:
                    info["warning"] = "No macro is mapped to a parameter, so the variation holds nothing audible"
            elif key == "recall":
                device.selected_variation_index = index
                device.recall_selected_variation()
            elif key == "delete":
                device.selected_variation_index = index
                device.delete_selected_variation()
            elif key == "randomize":
                device.randomize_macros()
            if key != "status":
                info["applied"] = True
                info["after"] = state()
            return info
        except Exception as e:
            self.log_message("Error with the rack variations: " + str(e))
            raise

    def _preview_browser_item(self, uri):
        """Play a browser item (a sample, a preset) through Live's preview, like the headphone button.
        It plays until it ends or stop_browser_preview; nothing is loaded into the Set."""
        try:
            if not isinstance(uri, str) or not uri.strip():
                raise ValueError("uri is required (from search_browser_items or get_browser_items_at_path)")
            app = self.application()
            item = self._find_browser_item_by_uri(app.browser, uri)
            if item is None:
                raise ValueError("No browser item has the uri %r" % uri)
            if not hasattr(app.browser, "preview_item"):
                raise RuntimeError("This version of Live has no Browser.preview_item")
            app.browser.preview_item(item)
            return {"previewing": getattr(item, "name", ""), "uri": uri}
        except Exception as e:
            self.log_message("Error previewing a browser item: " + str(e))
            raise

    def _stop_browser_preview(self):
        try:
            self.application().browser.stop_preview()
            return {"stopped": True}
        except Exception as e:
            self.log_message("Error stopping the preview: " + str(e))
            raise

    def _set_plugin_window(self, track_index, device_index, expected_name, expected_device_name,
                           open_window, track_type="track"):
        """Open or close a VST/AU plug-in's own window (AmpliTube, Analog Lab)."""
        try:
            track, device = self._rack_device(track_index, device_index, expected_name, expected_device_name, track_type)
            if not hasattr(device, "is_editor_open"):
                raise ValueError("Device '%s' is not a VST/AU plug-in; it has no window of its own" % device.name)
            if not isinstance(open_window, bool):
                raise TypeError("open must be true or false")
            before = bool(device.is_editor_open)
            device.is_editor_open = open_window
            return {"track_name": track.name, "device": device.name, "was_open": before,
                    "open": bool(device.is_editor_open)}
        except Exception as e:
            self.log_message("Error with a plug-in window: " + str(e))
            raise


    # ── Clip launch settings (1.10.20) ────────────────────────────────────────
    # Measured on Live 12.4 Lite (2026-10-24): Clip.launch_quantization takes Live.Clip.ClipLaunchQuantization
    # (0 = follow the Set's global setting), launch_mode Live.Clip.LaunchMode (trigger, gate, toggle, repeat)
    # and legato; all three apply at once. Song.view / Track.muted_via_solo / is_frozen read as plain properties.

    CLIP_LAUNCH_QUANTIZATION = [
        ("global", "q_global"), ("none", "q_none"), ("8 bars", "q_8_bars"), ("4 bars", "q_4_bars"),
        ("2 bars", "q_2_bars"), ("bar", "q_bar"), ("half", "q_half"), ("half triplet", "q_half_triplet"),
        ("quarter", "q_quarter"), ("quarter triplet", "q_quarter_triplet"), ("eighth", "q_eighth"),
        ("eighth triplet", "q_eighth_triplet"), ("sixteenth", "q_sixteenth"),
        ("sixteenth triplet", "q_sixteenth_triplet"), ("thirtysecond", "q_thirtysecond")]
    CLIP_LAUNCH_MODES = ("trigger", "gate", "toggle", "repeat")

    def _clip_launch_state(self, clip):
        """launch_quantization (name), launch_mode (name) and legato of a Session clip; {} when this Live
        or this kind of clip does not expose them."""
        try:
            import Live
            state = {}
            quantization = int(clip.launch_quantization)
            owner = Live.Clip.ClipLaunchQuantization
            state["launch_quantization"] = next(
                (name for name, attr in self.CLIP_LAUNCH_QUANTIZATION
                 if getattr(owner, attr, None) is not None and int(getattr(owner, attr)) == quantization), quantization)
            mode = int(clip.launch_mode)
            state["launch_mode"] = next((name for name in self.CLIP_LAUNCH_MODES
                                         if int(getattr(Live.Clip.LaunchMode, name)) == mode), mode)
            state["legato"] = bool(clip.legato)
            return state
        except Exception:
            return {}

    def _set_clip_launch(self, track_index, clip_index, expected_name, launch_quantization=None,
                         launch_mode=None, legato=None):
        """How a Session clip launches: its own launch quantization (or "global" to follow the Set's),
        its launch mode (trigger, gate, toggle, repeat) and legato. Session clips only."""
        try:
            import Live
            self._require_expected_name(expected_name, "track")
            track, clip = self._envelope_clip(track_index, clip_index, expected_name, False, None)
            if launch_quantization is None and launch_mode is None and legato is None:
                raise ValueError("Give launch_quantization, launch_mode and/or legato")
            before = self._clip_launch_state(clip)
            if not before:
                raise RuntimeError("This Live does not expose the launch settings of this clip")
            quantization = None
            if launch_quantization is not None:
                key = str(launch_quantization).strip().lower().replace("_", " ")
                match = [attr for name, attr in self.CLIP_LAUNCH_QUANTIZATION if name == key]
                if not match:
                    raise ValueError("launch_quantization must be one of: %s"
                                     % ", ".join(n for n, _ in self.CLIP_LAUNCH_QUANTIZATION))
                quantization = getattr(Live.Clip.ClipLaunchQuantization, match[0])
            mode = None
            if launch_mode is not None:
                key = str(launch_mode).strip().lower()
                if key not in self.CLIP_LAUNCH_MODES:
                    raise ValueError("launch_mode must be one of: %s" % ", ".join(self.CLIP_LAUNCH_MODES))
                mode = getattr(Live.Clip.LaunchMode, key)
            if legato is not None and not isinstance(legato, bool):
                raise TypeError("legato must be true or false")
            if quantization is not None:
                clip.launch_quantization = quantization
            if mode is not None:
                clip.launch_mode = mode
            if legato is not None:
                clip.legato = legato
            return {"track_name": track.name, "clip_name": clip.name, "before": before,
                    "after": self._clip_launch_state(clip)}
        except Exception as e:
            self.log_message("Error setting clip launch settings: " + str(e))
            raise


    # ── Return tracks ─────────────────────────────────────────────────────────
    # create_return_track and load_device_on_return adapted from the open
    # upstream PR ahujasid/ableton-mcp#99 (Zachary May), with guards added.

    def _call_on_main_thread(self, fn, timeout=10.0):
        """Run fn() on Live's main thread and return its value (or raise)."""
        replies = queue.Queue()

        def task():
            try:
                replies.put(("ok", fn()))
            except Exception as e:
                replies.put(("error", e))

        try:
            self.schedule_message(0, task)
        except AssertionError:
            task()
        try:
            status, value = replies.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError("Timeout waiting for Live's main thread")
        if status == "error":
            raise value
        return value

    def _return_tracks_summary(self):
        """Index, name and device names of every return track."""
        return [{"index": i, "name": t.name,
                 "devices": [d.name for d in t.devices]}
                for i, t in enumerate(self._song.return_tracks)]

    def _create_return_track(self, name=""):
        """Add one return track to the Set and return the new return list.

        Side effects: the Set gains a return track (and so a new send on every
        track); undoable with Live's undo. Live Lite allows only 2 return
        tracks: when the Set is full (Live raises, or the count does not
        grow) this raises a readable error and nothing is changed. The
        optional name is applied to the new return; a rename failure does not
        undo the creation and is reported as name_error.
        """
        try:
            if name is None:
                name = ""
            if not isinstance(name, str):
                raise TypeError("name must be a string, got %r" % (name,))
            before = list(self._song.return_tracks)
            full_hint = (
                "No return track was created. Live Lite allows only 2 return "
                "tracks; this Set has %d (%s)."
                % (len(before), ", ".join(t.name for t in before) or "none"))
            try:
                self._song.create_return_track()
            except Exception as e:
                raise RuntimeError("Live refused to create a return track (%s). %s"
                                   % (e, full_hint))
            after = list(self._song.return_tracks)
            if len(after) <= len(before):
                raise RuntimeError(full_hint)
            fresh = [t for t in after if not any(t == b for b in before)]
            track = fresh[-1] if fresh else after[-1]
            result = {"created": True}
            if name:
                try:
                    track.name = name
                except Exception as e:
                    result["name_error"] = str(e)
            result["index"] = next(
                (i for i, t in enumerate(self._song.return_tracks) if t == track),
                len(after) - 1)
            result["name"] = track.name
            result["return_tracks"] = self._return_tracks_summary()
            return result
        except Exception as e:
            self.log_message("Error creating return track: " + str(e))
            raise

    def _load_device_on_return(self, return_track_index, uri):
        """Load a browser item onto a return track (main-thread step).

        Live loads a browser item onto the SELECTED track, so this selects the
        return, loads, then restores the previously selected track. Side
        effects: the Set's selected track briefly changes (restored in a
        finally block; selection_restored reports whether it worked), and the
        return track gains a device. The device list is read back by
        _verify_load_on_return after a settle delay, not here.
        """
        try:
            track = self._resolve_track(return_track_index, "return")
            if not isinstance(uri, str) or not uri:
                raise ValueError("uri is required")
            app = self.application()
            item = self._find_browser_item_by_uri(app.browser, uri)
            if not item:
                raise ValueError("Browser item with URI '%s' not found" % uri)
            view = self._song.view
            previous = view.selected_track
            devices_before = [d.name for d in track.devices]
            try:
                view.selected_track = track
                app.browser.load_item(item)
            finally:
                try:
                    view.selected_track = previous
                except Exception as e:
                    self.log_message("Could not restore track selection: " + str(e))
            return {
                "return_track_index": return_track_index,
                "return_track_name": track.name,
                "item_name": item.name,
                "uri": uri,
                "devices_before": devices_before,
                "selection_restored": view.selected_track == previous,
            }
        except Exception as e:
            self.log_message("Error loading device on return track: " + str(e))
            raise

    def _verify_load_on_track(self, result):
        """Settle, then read the track's device list back (never raises).

        Same idea as _verify_load_on_return, for a regular track: Live adds the
        device a moment after load_item, so a read in the same tick shows the
        chain as it was (upstream issue #134). loaded is true when the chain
        changed; an instrument that replaces one of the same name leaves the
        names unchanged, which is reported as a warning rather than a failure.
        """
        result = dict(result)
        try:
            time.sleep(LOAD_SETTLE_SECONDS)
            index = result["track_index"]

            def read():
                track = self._song.tracks[index]
                return track.name, [d.name for d in track.devices]

            name, after = self._call_on_main_thread(read)
            before = result.get("devices_before", [])
            remaining = list(before)
            new = []
            for device in after:
                if device in remaining:
                    remaining.remove(device)
                else:
                    new.append(device)
            result["devices_after"] = after
            result["new_devices"] = new
            result["loaded"] = after != before
            if not result["loaded"]:
                result["warning"] = (
                    "The track's device list did not change after loading; the item may not "
                    "be loadable on this track, may have replaced an identical device, or the "
                    "load has not finished.")
        except Exception as e:
            result["loaded"] = False
            result["warning"] = "Could not verify the load: %s" % e
        return result

    def _verify_song_time(self, result):
        """Settle, then read the playhead back (never raises); upstream issue #134."""
        result = dict(result)
        try:
            time.sleep(0.2)
            result["current_song_time"] = self._call_on_main_thread(
                lambda: self._song.current_song_time)
            if abs(result["current_song_time"] - result.get("requested", 0.0)) > 1e-3:
                result["warning"] = ("The playhead is at beat %s, not the requested %s"
                                     % (result["current_song_time"], result.get("requested")))
        except Exception as e:
            result["warning"] = "Could not read the playhead back: %s" % e
        return result

    def _verify_load_on_return(self, result):
        """Settle, then read the return's device list back (never raises).

        Runs on the client thread so Live's main thread is not blocked while
        waiting; the read itself is scheduled onto the main thread. loaded is
        true only when the device count grew.
        """
        result = dict(result)
        try:
            time.sleep(LOAD_SETTLE_SECONDS)
            index = result["return_track_index"]

            def read():
                track = self._resolve_track(index, "return")
                return track.name, [d.name for d in track.devices]

            name, after = self._call_on_main_thread(read)
            before = result.get("devices_before", [])
            result["devices_after"] = after
            result["loaded"] = len(after) > len(before) and name == result.get("return_track_name")
            if not result["loaded"]:
                result["warning"] = (
                    "The return track's device list did not grow after loading; "
                    "the item may not be loadable on a return track (for "
                    "example an instrument), or the load has not finished.")
        except Exception as e:
            result["loaded"] = False
            result["warning"] = "Could not verify the load: %s" % e
        return result

    # ── Transport ─────────────────────────────────────────────────────────────
    # Adapted from the open upstream PR ahujasid/ableton-mcp#99 (Zachary May):
    # time signature, metronome, arrangement loop, cue points and cue jumps,
    # with input validation and honest read-backs added. Record, overdub, tap
    # tempo, nudge, punch points and locator creation/deletion are NOT ported.

    def _is_int(self, value):
        return isinstance(value, int) and not isinstance(value, bool)

    def _beats(self, value, label):
        """A finite number of beats (bool and NaN/inf are rejected)."""
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise TypeError("%s must be a finite number of beats, got %r" % (label, value))
        return float(value)

    def _set_time_signature(self, numerator, denominator):
        """Set the Set's global time signature (undoable with Live's undo).

        numerator must be an integer 1-99 and denominator one of 1, 2, 4, 8,
        16. Nothing is changed unless both are valid.
        """
        try:
            if not self._is_int(numerator) or not 1 <= numerator <= 99:
                raise ValueError("numerator must be an integer from 1 to 99, got %r"
                                 % (numerator,))
            if not self._is_int(denominator) or denominator not in (1, 2, 4, 8, 16):
                raise ValueError("denominator must be one of 1, 2, 4, 8, 16, got %r"
                                 % (denominator,))
            self._song.signature_numerator = numerator
            self._song.signature_denominator = denominator
            now = (self._song.signature_numerator, self._song.signature_denominator)
            return {
                "requested": {"numerator": numerator, "denominator": denominator},
                "numerator": now[0],
                "denominator": now[1],
                "applied": now == (numerator, denominator),
            }
        except Exception as e:
            self.log_message("Error setting time signature: " + str(e))
            raise

    def _set_metronome(self, enabled):
        """Turn the metronome on or off (a Set-wide setting, audible at once).

        Live may apply boolean changes after this call returns, so read_back
        can still show the old value; metronome is the requested state.
        """
        try:
            if not isinstance(enabled, bool):
                raise TypeError("enabled must be true or false, got %r" % (enabled,))
            self._song.metronome = enabled
            return {"metronome": enabled, "read_back": bool(self._song.metronome)}
        except Exception as e:
            self.log_message("Error setting metronome: " + str(e))
            raise

    def _get_arrangement_loop(self):
        """Read the arrangement loop brace: on/off, start, length, end (beats)."""
        try:
            start = float(self._song.loop_start)
            length = float(self._song.loop_length)
            return {
                "loop": bool(self._song.loop),
                "loop_start": start,
                "loop_length": length,
                "loop_end": start + length,
            }
        except Exception as e:
            self.log_message("Error getting arrangement loop: " + str(e))
            raise

    def _set_arrangement_loop(self, loop_start=None, loop_length=None, enabled=None):
        """Set the arrangement loop brace and/or switch looping on or off.

        Side effects: changes the Set's loop region, which also changes what
        repeats if the transport is playing. At least one argument is needed;
        everything is validated before anything is written. loop_start is in
        beats and >= 0, loop_length in beats and > 0. Live may apply the
        boolean after this call returns, so "loop" is the requested state and
        loop_read_back what Live reported straight away.
        """
        try:
            if loop_start is None and loop_length is None and enabled is None:
                raise ValueError(
                    "Provide at least one of loop_start, loop_length, enabled")
            if loop_start is not None:
                loop_start = self._beats(loop_start, "loop_start")
                if loop_start < 0:
                    raise ValueError("loop_start must be >= 0 beats, got %r" % loop_start)
            if loop_length is not None:
                loop_length = self._beats(loop_length, "loop_length")
                if loop_length <= 0:
                    raise ValueError("loop_length must be > 0 beats, got %r" % loop_length)
            if enabled is not None and not isinstance(enabled, bool):
                raise TypeError("enabled must be true or false, got %r" % (enabled,))
            if loop_start is not None:
                self._song.loop_start = loop_start
            if loop_length is not None:
                self._song.loop_length = loop_length
            if enabled is not None:
                self._song.loop = enabled
            now = self._get_arrangement_loop()
            result = {
                "loop": enabled if enabled is not None else now["loop"],
                "loop_read_back": now["loop"],
                "loop_start": now["loop_start"],
                "loop_length": now["loop_length"],
                "loop_end": now["loop_end"],
                "applied": True,
            }
            if ((loop_start is not None and abs(now["loop_start"] - loop_start) > 1e-6)
                    or (loop_length is not None
                        and abs(now["loop_length"] - loop_length) > 1e-6)):
                result["applied"] = False
                result["warning"] = ("Live reports a different loop than requested "
                                     "(it may have adjusted or ignored the values).")
            return result
        except Exception as e:
            self.log_message("Error setting arrangement loop: " + str(e))
            raise

    def _get_cue_points(self):
        """List the arrangement's cue points (locators), sorted by time (beats)."""
        try:
            cues = sorted(self._serialize_cue_points(), key=lambda c: c["time"])
            return {"cue_points": cues, "count": len(cues)}
        except Exception as e:
            self.log_message("Error getting cue points: " + str(e))
            raise

    def _jump_to_cue(self, direction):
        """Move the playhead to the next or previous cue point.

        Side effect: the playhead moves (and playback continues from there if
        playing). direction must be "next" or "previous". When no cue exists
        in that direction nothing is called and an error is raised. Live
        performs the jump after this call returns, so the position is not
        read back: expected_time/expected_name come from the cue list instead.
        """
        try:
            if direction not in ("next", "previous"):
                raise ValueError("direction must be 'next' or 'previous', got %r"
                                 % (direction,))
            now = float(self._song.current_song_time)
            cues = self._get_cue_points()["cue_points"]
            tolerance = 1e-6
            if direction == "next":
                candidates = [c for c in cues if c["time"] > now + tolerance]
                target = candidates[0] if candidates else None
            else:
                candidates = [c for c in cues if c["time"] < now - tolerance]
                target = candidates[-1] if candidates else None
            if target is None:
                raise ValueError("No %s cue point from beat %s (the Set has %d cue "
                                 "point(s)); nothing was moved"
                                 % (direction, now, len(cues)))
            if direction == "next":
                self._song.jump_to_next_cue()
            else:
                self._song.jump_to_prev_cue()
            return {
                "direction": direction,
                "from_time": now,
                "expected_time": target["time"],
                "expected_name": target["name"],
            }
        except Exception as e:
            self.log_message("Error jumping to cue: " + str(e))
            raise

    # ── Browser implementations ───────────────────────────────────────────────

    def _get_browser_item(self, uri, path):
        """Get a browser item by URI or path"""
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            result = {
                "uri": uri,
                "path": path,
                "found": False
            }
            
            # Try to find by URI first if provided
            if uri:
                item = self._find_browser_item_by_uri(app.browser, uri)
                if item:
                    result["found"] = True
                    result["item"] = {
                        "name": item.name,
                        "is_folder": item.is_folder,
                        "is_device": item.is_device,
                        "is_loadable": item.is_loadable,
                        "uri": item.uri
                    }
                    return result
            
            # If URI not provided or not found, try by path
            if path:
                # Parse the path and navigate to the specified item
                path_parts = path.split("/")
                
                # Determine the root based on the first part
                current_item = None
                if path_parts[0].lower() == "instruments":
                    current_item = app.browser.instruments
                elif path_parts[0].lower() == "sounds":
                    current_item = app.browser.sounds
                elif path_parts[0].lower() == "drums":
                    current_item = app.browser.drums
                elif path_parts[0].lower() == "audio_effects":
                    current_item = app.browser.audio_effects
                elif path_parts[0].lower() == "midi_effects":
                    current_item = app.browser.midi_effects
                else:
                    # Default to instruments if not specified
                    current_item = app.browser.instruments
                    # Don't skip the first part in this case
                    path_parts = ["instruments"] + path_parts
                
                # Navigate through the path
                for i in range(1, len(path_parts)):
                    part = path_parts[i]
                    if not part:  # Skip empty parts
                        continue
                    
                    found = False
                    for child in current_item.children:
                        if child.name.lower() == part.lower():
                            current_item = child
                            found = True
                            break
                    
                    if not found:
                        result["error"] = "Path part '{0}' not found".format(part)
                        return result
                
                # Found the item
                result["found"] = True
                result["item"] = {
                    "name": current_item.name,
                    "is_folder": current_item.is_folder,
                    "is_device": current_item.is_device,
                    "is_loadable": current_item.is_loadable,
                    "uri": current_item.uri
                }
            
            return result
        except Exception as e:
            self._log_command_error("Error getting browser item", e)
            raise   
    
    
    
    def _load_instrument_or_effect(self, track_index, uri):
        """Load an instrument or effect onto a track by its browser URI.

        The command dispatcher above calls this method, but it was never
        defined — and "load_instrument_or_effect" was missing from the list of
        main-thread commands as well, so the command fell through to the final
        "Unknown command" branch. Loading a device is exactly what
        _load_browser_item does, so delegate to it; the only difference is the
        parameter name the MCP server uses ("uri" vs "item_uri").
        """
        return self._load_browser_item(track_index, uri)

    def _load_browser_item(self, track_index, item_uri):
        """Load a browser item onto a track by its URI"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            
            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))
            
            # Select the track
            self._song.view.selected_track = track
            
            devices_before = [d.name for d in track.devices]

            # Load the item
            app.browser.load_item(item)
            
            # Live adds the device a moment later; the dispatcher settles and reads
            # the chain back (_verify_load_on_track) before the reply goes out.
            result = {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "track_index": track_index,
                "uri": item_uri,
                "devices_before": devices_before,
            }
            return result
        except Exception as e:
            self._log_command_error("Error loading browser item", e)
            raise
    
    # Substring markers that point a URI at a likely root. Unmatched URIs fall
    # back to the default search order.
    _URI_ROOT_HINTS = (
        ('plugins',       ('vst:', 'vst3:', 'au:', 'query:plugins', 'plugin#')),
        ('max_for_live',  ('max for live', 'maxforlive', 'm4l', 'query:max')),
        ('user_library',  ('user library', 'userlibrary', 'query:user library', 'query:user-library')),
        ('packs',         ('query:packs', '/packs/')),
        ('samples',       ('query:samples', 'sample:', '/samples/')),
        ('drums',         ('query:drums', '/drums/')),
        ('instruments',   ('query:instruments', '/instruments/')),
        ('sounds',        ('query:sounds', '/sounds/')),
        ('audio_effects', ('query:audio effects', 'audioeffects', '/audio_effects/')),
        ('midi_effects',  ('query:midi effects', 'midieffects', '/midi_effects/')),
    )

    def _order_roots_by_uri(self, roots, uri):
        """Reorder ``roots`` so the URI's likely root is walked first."""
        if not isinstance(uri, (bytes, str)) or not uri:
            return roots
        lowered = uri.lower()
        for attr, markers in self._URI_ROOT_HINTS:
            if any(m in lowered for m in markers):
                head = [(a, r) for (a, r) in roots if a == attr]
                tail = [(a, r) for (a, r) in roots if a != attr]
                return head + tail
        return roots

    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI.

        Top-level lookups are memoised on ``self._uri_cache`` so repeated
        loads of the same URI don't re-walk the entire browser tree.
        """
        if current_depth == 0:
            cache = getattr(self, '_uri_cache', None)
            if cache is None:
                self._uri_cache = cache = {}
            if uri in cache:
                return cache[uri]
            result = self._walk_browser_for_uri(browser_or_item, uri, max_depth, 0)
            if result is not None:
                cache[uri] = result
            return result
        return self._walk_browser_for_uri(browser_or_item, uri, max_depth, current_depth)

    def _walk_browser_for_uri(self, browser_or_item, uri, max_depth, current_depth):
        """Recursive walk used by :py:meth:`_find_browser_item_by_uri`."""
        try:
            # Check if this is the item we're looking for
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item

            # Stop recursion if we've reached max depth
            if current_depth >= max_depth:
                return None

            # Check if this is a browser with root categories
            if hasattr(browser_or_item, 'instruments'):
                roots = [
                    ('instruments', browser_or_item.instruments),
                    ('sounds', browser_or_item.sounds),
                    ('drums', browser_or_item.drums),
                    ('audio_effects', browser_or_item.audio_effects),
                    ('midi_effects', browser_or_item.midi_effects),
                ]
                for extra_attr in ('plugins', 'max_for_live', 'user_library', 'packs', 'samples'):
                    if hasattr(browser_or_item, extra_attr):
                        try:
                            roots.append((extra_attr, getattr(browser_or_item, extra_attr)))
                        except (AttributeError, RuntimeError) as e:
                            self.log_message("Could not access browser.{0}: {1}".format(extra_attr, str(e)))

                for _attr, category in self._order_roots_by_uri(roots, uri):
                    item = self._find_browser_item_by_uri(category, uri, max_depth, current_depth + 1)
                    if item:
                        return item

                return None

            # Check if this item has children
            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item

            return None
        except Exception as e:
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None
    
    # Helper methods

    def _find_blend_parameter(self, device):
        """Find Dry/Wet, Mix, or Amount on a device for Magnitude mapping."""
        preferred = ("Dry/Wet", "Dry Wet", "Mix", "Amount")
        by_name = {}
        for param in device.parameters:
            try:
                by_name[param.name] = param
            except Exception:
                continue
        for name in preferred:
            if name in by_name:
                return by_name[name], name
        # Case-insensitive fallback
        lowered = dict((k.lower(), (v, k)) for k, v in by_name.items())
        for name in preferred:
            hit = lowered.get(name.lower())
            if hit:
                return hit[0], hit[1]
        return None, None

    def _inspect_rack(self, track_index, device_index=0):
        """Inspect a rack's nested devices and blend parameters."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        rack = track.devices[device_index]
        if not getattr(rack, "can_have_chains", False):
            raise ValueError("Device '{0}' is not a rack".format(rack.name))

        devices_info = []
        for chain_index, chain in enumerate(rack.chains):
            for nested in chain.devices:
                blend, blend_name = self._find_blend_parameter(nested)
                param_names = []
                try:
                    param_names = [p.name for p in nested.parameters]
                except Exception:
                    pass
                devices_info.append({
                    "chain_index": chain_index,
                    "name": nested.name,
                    "class_name": nested.class_name,
                    "blend_param": blend_name,
                    "parameters": param_names,
                })

        return {
            "track_index": track_index,
            "device_index": device_index,
            "rack_name": rack.name,
            "has_macro_map": hasattr(rack, "macro_map"),
            "has_rename_macro": hasattr(rack, "rename_macro"),
            "macros_mapped": list(getattr(rack, "macros_mapped", [])),
            "devices": devices_info,
        }

    def _map_rack_magnitude(self, track_index, device_index=0, macro_name="Magnitude"):
        """Rename Macro 1 and map nested Dry/Wet (or Mix/Amount) params to it."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        track = self._song.tracks[track_index]
        if device_index < 0 or device_index >= len(track.devices):
            raise IndexError("Device index out of range")
        rack = track.devices[device_index]
        if not getattr(rack, "can_have_chains", False):
            raise ValueError("Device '{0}' is not a rack".format(rack.name))
        if not hasattr(rack, "macro_map"):
            raise RuntimeError(
                "RackDevice.macro_map is unavailable in this Live version")

        # Ensure at least one macro is visible
        try:
            visible = int(getattr(rack, "visible_macro_count", 1) or 1)
            while visible < 1 and hasattr(rack, "add_macro"):
                rack.add_macro()
                visible = int(rack.visible_macro_count)
        except Exception as e:
            self.log_message("Could not adjust visible macros: {0}".format(e))

        if hasattr(rack, "rename_macro"):
            rack.rename_macro(0, macro_name)
        else:
            # Fallback: Macro 1 is usually parameters[1] (0 = Device On)
            try:
                if len(rack.parameters) > 1:
                    rack.parameters[1].name = macro_name
            except Exception:
                pass

        mapped = []
        skipped = []
        for chain_index, chain in enumerate(rack.chains):
            for nested in chain.devices:
                blend, blend_name = self._find_blend_parameter(nested)
                if not blend:
                    skipped.append({
                        "device": nested.name,
                        "reason": "no Dry/Wet, Mix, or Amount parameter",
                    })
                    continue
                try:
                    rack.macro_map(0, blend)
                    mapped.append({
                        "device": nested.name,
                        "parameter": blend_name,
                        "chain_index": chain_index,
                    })
                except Exception as e:
                    skipped.append({
                        "device": nested.name,
                        "parameter": blend_name,
                        "reason": str(e),
                    })

        return {
            "rack_name": rack.name,
            "macro_name": macro_name,
            "macro_index": 0,
            "mapped": mapped,
            "skipped": skipped,
            "macros_mapped": list(getattr(rack, "macros_mapped", [])),
        }
    
    def _get_device_type(self, device):
        """Get the type of a device"""
        try:
            # Simple heuristic - in a real implementation you'd look at the device class
            if device.can_have_drum_pads:
                return "drum_machine"
            elif device.can_have_chains:
                return "rack"
            elif "instrument" in device.class_display_name.lower():
                return "instrument"
            elif "audio_effect" in device.class_name.lower():
                return "audio_effect"
            elif "midi_effect" in device.class_name.lower():
                return "midi_effect"
            else:
                return "unknown"
        except:
            return "unknown"

    # ── Passive human-UI listeners ──────────────────────────────────────────────

    def _enqueue_passive(self, event_type, detail=None, track_index=None, clip_index=None):
        """Append a coarse human-UI event (capped FIFO)."""
        evt = {
            "type": event_type,
            "ts": time.time(),
            "track_index": track_index,
            "clip_index": clip_index,
            "detail": detail if detail is not None else {},
        }
        with self._passive_lock:
            self._passive_events.append(evt)
            if len(self._passive_events) > self._passive_max:
                self._passive_events = self._passive_events[-self._passive_max:]

    def _drain_passive_events(self):
        """Return and clear the passive event queue (called by MCP poller)."""
        with self._passive_lock:
            events = list(self._passive_events)
            self._passive_events = []
        return {"events": events, "count": len(events)}

    def _safe_add_listener(self, obj, add_name, callback):
        try:
            if obj is not None and hasattr(obj, add_name):
                getattr(obj, add_name)(callback)
                return True
        except Exception as e:
            self.log_message("add listener %s failed: %s" % (add_name, str(e)))
        return False

    def _safe_remove_listener(self, obj, remove_name, callback):
        try:
            if obj is not None and hasattr(obj, remove_name):
                getattr(obj, remove_name)(callback)
        except Exception:
            pass

    def _setup_passive_listeners(self):
        """Register high-signal LOM listeners for Mode C / assisted human edits."""
        song = self._song

        def on_tempo():
            try:
                self._enqueue_passive("tempo_changed", {"tempo": float(song.tempo)})
            except Exception:
                self._enqueue_passive("tempo_changed")

        def on_sig_num():
            try:
                self._enqueue_passive(
                    "time_signature_changed",
                    {
                        "signature_numerator": int(song.signature_numerator),
                        "signature_denominator": int(song.signature_denominator),
                    },
                )
            except Exception:
                self._enqueue_passive("time_signature_changed")

        def on_sig_den():
            on_sig_num()

        def on_is_playing():
            try:
                self._enqueue_passive(
                    "playback_changed",
                    {"is_playing": bool(song.is_playing)},
                )
            except Exception:
                self._enqueue_passive("playback_changed")

        def on_tracks():
            count = len(song.tracks)
            previous = getattr(self, "_passive_track_count", None)
            self._passive_track_count = count
            detail = {"track_count": count}
            if previous is not None:
                detail["previous_count"] = previous
                detail["removed"] = count < previous
                detail["added"] = count > previous
            self._enqueue_passive("tracks_changed", detail)
            try:
                self._rebind_track_listeners()
            except Exception as e:
                self.log_message("rebind track listeners failed: " + str(e))

        self._safe_add_listener(song, "add_tempo_listener", on_tempo)
        self._safe_add_listener(song, "add_signature_numerator_listener", on_sig_num)
        self._safe_add_listener(song, "add_signature_denominator_listener", on_sig_den)
        self._safe_add_listener(song, "add_is_playing_listener", on_is_playing)
        self._safe_add_listener(song, "add_tracks_listener", on_tracks)

        self._song_passive_callbacks = [
            ("tempo_listener", on_tempo),
            ("signature_numerator_listener", on_sig_num),
            ("signature_denominator_listener", on_sig_den),
            ("is_playing_listener", on_is_playing),
            ("tracks_listener", on_tracks),
        ]

        self._rebind_track_listeners()
        self.log_message("Passive LOM listeners registered")

    def _teardown_passive_listeners(self):
        song = getattr(self, "_song", None)
        for suffix, cb in getattr(self, "_song_passive_callbacks", []):
            self._safe_remove_listener(song, "remove_" + suffix, cb)
        self._clear_track_listeners()

    def _clear_track_listeners(self):
        for track, bindings in getattr(self, "_passive_track_bindings", []):
            for add_name, callback in bindings:
                remove_name = "remove_" + add_name[len("add_"):]
                target = getattr(callback, "_passive_target", None)
                if target is not None:
                    self._safe_remove_listener(target, remove_name, callback)
                else:
                    self._safe_remove_listener(track, remove_name, callback)
        self._passive_track_bindings = []

    def _rebind_track_listeners(self):
        self._clear_track_listeners()
        song = self._song
        for track_index, track in enumerate(song.tracks):
            bindings = []

            def make_track_cb(kind, t_index):
                def _cb():
                    detail = {}
                    try:
                        t = song.tracks[t_index]
                        if kind == "name_changed":
                            detail["name"] = t.name
                        elif kind == "mute_changed":
                            detail["mute"] = bool(t.mute)
                        elif kind == "solo_changed":
                            detail["solo"] = bool(t.solo)
                        elif kind == "arm_changed":
                            detail["arm"] = self._safe_arm(t)
                        elif kind == "devices_changed":
                            detail["device_count"] = len(t.devices)
                        elif kind == "volume_changed":
                            detail["volume"] = float(t.mixer_device.volume.value)
                        elif kind == "panning_changed":
                            detail["panning"] = float(t.mixer_device.panning.value)
                    except Exception:
                        pass
                    self._enqueue_passive(kind, detail, track_index=t_index)
                return _cb

            pairs = [
                ("add_name_listener", "name_changed"),
                ("add_mute_listener", "mute_changed"),
                ("add_solo_listener", "solo_changed"),
                ("add_arm_listener", "arm_changed"),
                ("add_devices_listener", "devices_changed"),
            ]
            for add_name, kind in pairs:
                cb = make_track_cb(kind, track_index)
                if self._safe_add_listener(track, add_name, cb):
                    bindings.append((add_name, cb))

            try:
                mixer = track.mixer_device
                vol_cb = make_track_cb("volume_changed", track_index)
                vol_cb._passive_target = mixer.volume
                if self._safe_add_listener(mixer.volume, "add_value_listener", vol_cb):
                    bindings.append(("add_value_listener", vol_cb))
                pan_cb = make_track_cb("panning_changed", track_index)
                pan_cb._passive_target = mixer.panning
                if self._safe_add_listener(mixer.panning, "add_value_listener", pan_cb):
                    bindings.append(("add_value_listener", pan_cb))
            except Exception as e:
                self.log_message("mixer listeners failed on track %d: %s" % (track_index, str(e)))

            try:
                for clip_index, slot in enumerate(track.clip_slots):
                    def make_slot_cb(t_index, c_index):
                        def _cb():
                            has = False
                            try:
                                has = bool(song.tracks[t_index].clip_slots[c_index].has_clip)
                            except Exception:
                                pass
                            self._enqueue_passive(
                                "clip_slot_changed",
                                {"has_clip": has},
                                track_index=t_index,
                                clip_index=c_index,
                            )
                            try:
                                self._bind_clip_listeners(t_index, c_index)
                            except Exception:
                                pass
                        return _cb

                    slot_cb = make_slot_cb(track_index, clip_index)
                    slot_cb._passive_target = slot
                    if self._safe_add_listener(slot, "add_has_clip_listener", slot_cb):
                        bindings.append(("add_has_clip_listener", slot_cb))
                    if slot.has_clip:
                        self._bind_clip_listeners(track_index, clip_index, bindings)
            except Exception as e:
                self.log_message("clip slot listeners failed on track %d: %s" % (track_index, str(e)))

            self._passive_track_bindings.append((track, bindings))

    def _bind_clip_listeners(self, track_index, clip_index, bindings=None):
        try:
            track = self._song.tracks[track_index]
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                return
            clip = slot.clip

            def on_name():
                name = ""
                try:
                    name = clip.name
                except Exception:
                    pass
                self._enqueue_passive(
                    "clip_name_changed",
                    {"name": name},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            def on_notes():
                self._enqueue_passive(
                    "clip_notes_changed",
                    {},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            def on_playing():
                playing = False
                try:
                    playing = bool(clip.is_playing)
                except Exception:
                    pass
                self._enqueue_passive(
                    "clip_playing_changed",
                    {"is_playing": playing},
                    track_index=track_index,
                    clip_index=clip_index,
                )

            for add_name, cb in [
                ("add_name_listener", on_name),
                ("add_notes_listener", on_notes),
                ("add_playing_status_listener", on_playing),
            ]:
                cb._passive_target = clip
                if self._safe_add_listener(clip, add_name, cb):
                    if bindings is not None:
                        bindings.append((add_name, cb))
        except Exception as e:
            self.log_message(
                "bind clip listeners %d/%d failed: %s"
                % (track_index, clip_index, str(e))
            )

    # ── Dataset / state snapshot helpers ──────────────────────────────────────

    def _safe_attr(self, obj, attr, cast=None, default=None):
        try:
            val = getattr(obj, attr)
            if callable(val):
                return default
            if cast is not None:
                return cast(val)
            return val
        except Exception:
            return default

    def _notes_from_clip(self, clip):
        """Extract MIDI notes from a clip (incl. MPE/expression when available)."""
        notes = []
        if not clip or not getattr(clip, "is_midi_clip", False):
            return notes

        if hasattr(clip, "get_notes_extended"):
            try:
                raw = clip.get_notes_extended(0, 128, 0.0, float(clip.length) + 1.0)
                for n in raw:
                    entry = {
                        "pitch": int(getattr(n, "pitch", 0)),
                        "start_time": float(getattr(n, "start_time", 0.0)),
                        "duration": float(getattr(n, "duration", 0.0)),
                        "velocity": float(getattr(n, "velocity", 0)),
                        "mute": bool(getattr(n, "mute", False)),
                    }
                    for opt, caster in [
                        ("probability", float),
                        ("velocity_deviation", float),
                        ("release_velocity", float),
                        ("note_id", int),
                    ]:
                        if hasattr(n, opt):
                            try:
                                entry[opt] = caster(getattr(n, opt))
                            except Exception:
                                pass
                    for opt in ("pitch_bend_range", "pressure", "timbre", "slide"):
                        if hasattr(n, opt):
                            try:
                                entry[opt] = float(getattr(n, opt))
                            except Exception:
                                pass
                    notes.append(entry)
                return notes
            except Exception as e:
                self.log_message("get_notes_extended failed, falling back: " + str(e))

        if hasattr(clip, "get_notes"):
            try:
                raw = clip.get_notes(0.0, 0, float(clip.length) + 1.0, 128)
                for n in raw:
                    notes.append({
                        "pitch": int(n[0]),
                        "start_time": float(n[1]),
                        "duration": float(n[2]),
                        "velocity": float(n[3]),
                        "mute": bool(n[4]) if len(n) > 4 else False,
                    })
            except Exception as e:
                self.log_message("get_notes failed: " + str(e))
        return notes

    def _warp_markers_from_clip(self, clip):
        markers = []
        try:
            raw = getattr(clip, "warp_markers", None)
            if not raw:
                return markers
            for m in raw:
                markers.append({
                    "beat_time": float(getattr(m, "beat_time", getattr(m, "time", 0.0))),
                    "sample_time": float(
                        getattr(m, "sample_time", getattr(m, "time", 0.0))
                    ),
                })
        except Exception as e:
            self.log_message("warp_markers read failed: " + str(e))
        return markers

    def _automated_params_for_device(self, device):
        automated = []
        try:
            for param in device.parameters:
                is_auto = False
                try:
                    if hasattr(param, "automation_state"):
                        is_auto = int(param.automation_state) != 0
                    elif hasattr(param, "is_automated"):
                        is_auto = bool(param.is_automated)
                except Exception:
                    continue
                if is_auto:
                    automated.append(param.name)
        except Exception:
            pass
        return automated

    # Racks nest, and a pathological project could nest deeply. Cap the walk so
    # a snapshot can never blow the stack or the payload size.
    _MAX_CHAIN_DEPTH = 4

    def _serialize_device(self, device, device_index, include_params=True, depth=0,
                          with_display=False, name_filter=None, param_limit=None,
                          include_chains=True):
        info = {
            "index": device_index,
            "name": device.name,
            "class_name": device.class_name,
            "type": self._get_device_type(device),
        }
        automated = self._automated_params_for_device(device)
        if automated:
            info["automated_parameters"] = automated
            info["automation_enabled"] = True
        else:
            info["automation_enabled"] = False

        if with_display:
            # Only the detailed read: the session snapshot stays as small as it was.
            for key, attr, kind in (("is_active", "is_active", bool), ("latency_ms", "latency_in_ms", float)):
                value = self._safe_attr(device, attr, kind, None)
                if value is not None and (key == "is_active" or value):
                    info[key] = value

        if include_params:
            params = []
            matched = 0
            total = 0
            needle = name_filter.lower() if name_filter else None
            try:
                for p_index, param in enumerate(device.parameters):
                    total += 1
                    try:
                        if needle is not None and needle not in str(param.name).lower():
                            continue
                        matched += 1
                        if param_limit is not None and len(params) >= param_limit:
                            continue
                        entry = {
                            "index": p_index,
                            "name": param.name,
                            "value": float(param.value),
                            "min": float(param.min),
                            "max": float(param.max),
                            "is_enabled": bool(getattr(param, "is_enabled", True)),
                            "is_quantized": bool(getattr(param, "is_quantized", False)),
                        }
                        if entry["is_quantized"]:
                            try:
                                entry["items"] = [str(x) for x in param.value_items]
                            except Exception:
                                pass
                        else:
                            try:
                                entry["default"] = float(param.default_value)
                            except Exception:
                                pass
                        if with_display:
                            display = self._param_display(param)
                            if display is not None:
                                entry["display"] = display
                            display_value = self._param_display_value(param)
                            if display_value is not None:
                                entry["display_value"] = display_value
                        if hasattr(param, "value_string"):
                            entry["value_string"] = str(param.value_string)
                        if hasattr(param, "automation_state"):
                            try:
                                entry["automation_state"] = int(param.automation_state)
                            except Exception:
                                pass
                        params.append(entry)
                    except Exception:
                        continue
            except Exception as e:
                self.log_message("Error reading device parameters: " + str(e))
            info["parameters"] = params
            if needle is not None or param_limit is not None:
                info["parameters_total"] = total
                info["parameters_matched"] = matched
                info["parameters_truncated"] = matched > len(params)

        # Devices inside a rack carry the actual sound design — a drum rack's
        # nested Operator, an instrument rack's filter. Without this walk a rack
        # contributes only its 8 macros and the timbral state is invisible.
        if include_chains and getattr(device, "can_have_chains", False):
            if depth >= self._MAX_CHAIN_DEPTH:
                info["chains_truncated"] = True
            else:
                info["chains"] = self._serialize_chains(
                    device, include_params=include_params, depth=depth,
                    with_display=with_display, name_filter=name_filter,
                    param_limit=param_limit,
                )
        return info

    def _serialize_chains(self, rack, include_params=True, depth=0,
                          with_display=False, name_filter=None, param_limit=None):
        chains = []
        try:
            chain_lists = [("chains", getattr(rack, "chains", []))]
            returns = getattr(rack, "return_chains", None)
            if returns:
                chain_lists.append(("return_chains", returns))

            for kind, chain_list in chain_lists:
                for chain_index, chain in enumerate(chain_list):
                    entry = {
                        "index": chain_index,
                        "kind": kind,
                        "chain_name": self._safe_attr(chain, "name", str, ""),
                        "mute": bool(self._safe_attr(chain, "mute", bool, False)),
                        "solo": bool(self._safe_attr(chain, "solo", bool, False)),
                    }
                    try:
                        mixer = chain.mixer_device
                        entry["volume"] = float(mixer.volume.value)
                        entry["panning"] = float(mixer.panning.value)
                    except Exception:
                        pass

                    # Drum racks expose the pad's note, which is what ties a
                    # nested device back to the kick/snare/hat it voices.
                    note = self._safe_attr(chain, "out_note", int, None)
                    if note is not None:
                        entry["out_note"] = note

                    nested = []
                    try:
                        for d_i, dev in enumerate(chain.devices):
                            nested.append(
                                self._serialize_device(
                                    dev,
                                    d_i,
                                    include_params=include_params,
                                    depth=depth + 1,
                                    with_display=with_display,
                                    name_filter=name_filter,
                                    param_limit=param_limit,
                                )
                            )
                    except Exception as e:
                        self.log_message("Error reading chain devices: " + str(e))
                    entry["devices"] = nested
                    chains.append(entry)
        except Exception as e:
            self.log_message("Error serializing rack chains: " + str(e))
        return chains

    def _serialize_clip_common(self, clip):
        info = {
            "looping": bool(self._safe_attr(clip, "looping", bool, False)),
            "loop_start": self._safe_attr(clip, "loop_start", float, None),
            "loop_end": self._safe_attr(clip, "loop_end", float, None),
            "warping": bool(self._safe_attr(clip, "warping", bool, False)),
            "warp_mode": self._safe_attr(clip, "warp_mode", int, None),
            "gain": self._safe_attr(clip, "gain", float, None),
            "pitch_coarse": self._safe_attr(clip, "pitch_coarse", int, None),
            "pitch_fine": self._safe_attr(clip, "pitch_fine", int, None),
            "launch_mode": self._safe_attr(clip, "launch_mode", int, None),
        }
        for attr in ("file_path", "file_path_relative"):
            path = self._safe_attr(clip, attr, str, None)
            if path:
                info["file_path"] = path
                break
        markers = self._warp_markers_from_clip(clip)
        if markers:
            info["warp_markers"] = markers
            info["warp_marker_count"] = len(markers)
        return dict((k, v) for k, v in info.items() if v is not None)

    def _serialize_session_clip(self, clip, include_notes=True):
        info = {
            "name": clip.name,
            "length": float(clip.length),
            "is_playing": bool(clip.is_playing),
            "is_recording": bool(getattr(clip, "is_recording", False)),
            "is_midi_clip": bool(getattr(clip, "is_midi_clip", False)),
            "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
            "color": int(getattr(clip, "color", 0)),
        }
        info.update(self._serialize_clip_common(clip))
        if include_notes and info["is_midi_clip"]:
            info["notes"] = self._notes_from_clip(clip)
            info["note_count"] = len(info["notes"])
        return info

    def _serialize_arrangement_clip(self, clip, include_notes=True):
        info = {
            "name": clip.name,
            "start_time": float(clip.start_time),
            "end_time": float(clip.end_time),
            "length": float(clip.length),
            "color": int(getattr(clip, "color", 0)),
            "is_midi_clip": bool(getattr(clip, "is_midi_clip", False)),
            "is_audio_clip": bool(getattr(clip, "is_audio_clip", False)),
            "is_playing": bool(getattr(clip, "is_playing", False)),
        }
        info.update(self._serialize_clip_common(clip))
        if include_notes and info["is_midi_clip"]:
            info["notes"] = self._notes_from_clip(clip)
            info["note_count"] = len(info["notes"])
        return info

    def _serialize_sends(self, track):
        sends = []
        try:
            for i, send in enumerate(track.mixer_device.sends):
                sends.append({
                    "index": i,
                    "value": float(send.value),
                    "name": str(getattr(send, "name", "Send %d" % i)),
                })
        except Exception:
            pass
        return sends

    def _serialize_scenes(self):
        scenes = []
        try:
            for i, scene in enumerate(self._song.scenes):
                scenes.append({
                    "index": i,
                    "name": str(scene.name),
                    "tempo": self._safe_attr(scene, "tempo", float, None),
                    "is_triggered": bool(self._safe_attr(scene, "is_triggered", bool, False)),
                })
        except Exception as e:
            self.log_message("scenes serialize failed: " + str(e))
        return scenes

    def _serialize_cue_points(self):
        cues = []
        try:
            for cue in self._song.cue_points:
                cues.append({
                    "name": str(getattr(cue, "name", "")),
                    "time": float(getattr(cue, "time", 0.0)),
                })
        except Exception as e:
            self.log_message("cue_points serialize failed: " + str(e))
        return cues

    def _serialize_return_tracks(self, include_params=True):
        returns = []
        try:
            for i, track in enumerate(self._song.return_tracks):
                devices = []
                for d_i, device in enumerate(track.devices):
                    devices.append(
                        self._serialize_device(device, d_i, include_params=include_params)
                    )
                returns.append({
                    "index": i,
                    "name": track.name,
                    "mute": bool(track.mute),
                    "solo": bool(track.solo),
                    "volume": float(track.mixer_device.volume.value),
                    "panning": float(track.mixer_device.panning.value),
                    "devices": devices,
                })
        except Exception as e:
            self.log_message("return_tracks serialize failed: " + str(e))
        return returns

    def _serialize_master_track(self, include_params=True):
        """Master chain — the bus compressor/limiter that shapes the final sound."""
        try:
            track = self._song.master_track
            devices = []
            for d_i, device in enumerate(track.devices):
                devices.append(
                    self._serialize_device(device, d_i, include_params=include_params)
                )
            return {
                "volume": float(track.mixer_device.volume.value),
                "panning": float(track.mixer_device.panning.value),
                "devices": devices,
            }
        except Exception as e:
            self.log_message("master_track serialize failed: " + str(e))
            return None

    def _get_clip_notes(self, track_index, clip_index, clip_start_time=None):
        try:
            track, clip = self._session_clip(track_index, clip_index, clip_start_time=clip_start_time)
            if not getattr(clip, "is_midi_clip", False):
                raise Exception("Clip is not a MIDI clip")
            notes = self._notes_from_clip(clip)
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "clip_name": clip.name,
                "length": float(clip.length),
                "note_count": len(notes),
                "notes": notes,
            }
        except Exception as e:
            self.log_message("Error getting clip notes: " + str(e))
            raise

    # A rack's chains (and everything nested in them) are what make
    # get_device_parameters payloads reach hundreds of KB; the summary lists
    # only this many chains.
    _RACK_SUMMARY_MAX_CHAINS = 32

    def _get_device_parameters(self, track_index, device_index, name_contains=None,
                               limit=None, include_racks=False, track_type="track"):
        """Parameters of one device, each with Live's display string.

        name_contains: case-insensitive substring filter on parameter names.
        limit: keep at most this many parameters per device (after filtering).
        include_racks: racks (and drum racks) are returned as a compact summary
        (their own macro parameters plus a list of chain and device names)
        unless this is true, because walking every chain returns payloads of
        hundreds of KB. Non-racks are unaffected.
        Parameter "index" is always the index into device.parameters, so a
        filtered result can be passed straight to set_device_parameter.
        """
        try:
            if name_contains is not None and not isinstance(name_contains, str):
                raise TypeError("name_contains must be a string")
            if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)
                                      or limit < 0):
                raise ValueError("limit must be a non-negative integer")
            track = self._resolve_track(track_index, track_type)
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            is_rack = bool(getattr(device, "can_have_chains", False))
            summarise = is_rack and not include_racks
            info = self._serialize_device(
                device, device_index, include_params=True, with_display=True,
                name_filter=name_contains, param_limit=limit,
                include_chains=not summarise)
            if summarise:
                info["rack_summary"] = self._rack_summary(device)
            return {"track_index": track_index, "device": info}
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _param_display_value(self, param):
        """The value in the unit Live shows it in (Hz, ms, dB, %, semitones), or None.

        Live's display_value is the number behind the display string: 1000.0 for "1.00 kHz",
        1456.0 for "1.46 s" (times are in ms). None for a quantized parameter, a parameter
        without one, or an infinite display such as a compressor ratio of "inf : 1".
        """
        try:
            if getattr(param, "is_quantized", False):
                return None
            number = float(param.display_value)
        except Exception:
            return None
        if number != number or abs(number) > 1e30:
            return None
        return number

    def _param_display(self, param):
        """Live's own display string for a parameter's current value ("-6.0 dB",
        "1/8", "Sine"), or None when it cannot be read."""
        try:
            text = param.str_for_value(param.value)
            if text is not None:
                return str(text)
        except Exception:
            pass
        try:
            text = str(param)
            # An unhelpful default repr means __str__ is not a display string.
            if text and not text.startswith("<"):
                return text
        except Exception:
            pass
        return None

    def _rack_summary(self, rack):
        chains = []
        total_devices = 0
        chain_lists = [("chains", list(getattr(rack, "chains", None) or [])),
                       ("return_chains", list(getattr(rack, "return_chains", None) or []))]
        for kind, chain_list in chain_lists:
            for chain_index, chain in enumerate(chain_list):
                device_names = [self._safe_attr(d, "name", str, "")
                                for d in (self._safe_attr(chain, "devices", list, []) or [])]
                total_devices += len(device_names)
                if len(chains) < self._RACK_SUMMARY_MAX_CHAINS:
                    chains.append({
                        "index": chain_index,
                        "kind": kind,
                        "chain_name": self._safe_attr(chain, "name", str, ""),
                        "device_names": device_names,
                    })
        count = sum(len(c) for _, c in chain_lists)
        return {
            "chain_count": len(chain_lists[0][1]),
            "return_chain_count": len(chain_lists[1][1]),
            "nested_device_count": total_devices,
            "chains": chains,
            "chains_truncated": count > len(chains),
            "hint": ("Rack contents omitted to keep the reply small. Pass "
                     "include_racks=true for every chain parameter (can be "
                     "hundreds of KB), or read a nested device directly."),
        }

    def _get_session_snapshot(self, include_notes=True, include_params=True):
        """Full v2 project state dump for trajectory dataset recording."""
        try:
            session = self._get_session_info()
            tracks = []
            for track_index, track in enumerate(self._song.tracks):
                clip_slots = []
                for slot_index, slot in enumerate(track.clip_slots):
                    clip_info = None
                    if slot.has_clip:
                        clip_info = self._serialize_session_clip(
                            slot.clip, include_notes=include_notes
                        )
                    clip_slots.append({
                        "index": slot_index,
                        "has_clip": bool(slot.has_clip),
                        "clip": clip_info,
                    })

                devices = []
                for device_index, device in enumerate(track.devices):
                    devices.append(
                        self._serialize_device(
                            device, device_index, include_params=include_params
                        )
                    )

                arrangement_clips = []
                try:
                    for clip in track.arrangement_clips:
                        arrangement_clips.append(
                            self._serialize_arrangement_clip(
                                clip, include_notes=include_notes
                            )
                        )
                except Exception as e:
                    self.log_message(
                        "arrangement_clips unavailable on track %d: %s"
                        % (track_index, str(e))
                    )

                tracks.append({
                    "index": track_index,
                    "name": track.name,
                    "is_audio_track": bool(track.has_audio_input),
                    "is_midi_track": bool(track.has_midi_input),
                    "mute": bool(track.mute),
                    "solo": bool(track.solo),
                    "arm": self._safe_arm(track),
                    "volume": float(track.mixer_device.volume.value),
                    "panning": float(track.mixer_device.panning.value),
                    "sends": self._serialize_sends(track),
                    "clip_slots": clip_slots,
                    "devices": devices,
                    "arrangement_clips": arrangement_clips,
                })

            return {
                "schema": "ableton_mcp_snapshot_v2",
                "session": session,
                "tracks": tracks,
                "scenes": self._serialize_scenes(),
                "return_tracks": self._serialize_return_tracks(
                    include_params=include_params
                ),
                "master_track": self._serialize_master_track(
                    include_params=include_params
                ),
                "cue_points": self._serialize_cue_points(),
                "include_notes": bool(include_notes),
                "include_params": bool(include_params),
            }
        except Exception as e:
            self.log_message("Error getting session snapshot: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_index, value,
                              track_type="track", display_value=None):
        """Set one parameter, by raw value or by display_value (the unit Live shows: Hz, ms, dB, %).

        display_value is the way to say "80 Hz" or "-6 dB" without knowing the parameter's curve; Live
        clamps a number outside the parameter's range without an error, so the reply says "clamped".
        """
        try:
            track = self._resolve_track(track_index, track_type)
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[parameter_index]
            if (value is None) == (display_value is None):
                raise ValueError("Give exactly one of value (Live's raw units) or display_value (the unit shown: Hz, ms, dB, %)")
            old = float(param.value)
            old_display = self._param_display(param)
            clamped = False
            if display_value is not None:
                if isinstance(display_value, bool) or not isinstance(display_value, (int, float)):
                    raise TypeError("display_value must be a number")
                if getattr(param, "is_quantized", False):
                    raise ValueError("Parameter '%s' is a choice (quantized); set its position with value (see items in get_device_parameters)" % param.name)
                if not hasattr(param, "display_value"):
                    raise RuntimeError("This version of Live has no DeviceParameter.display_value")
                try:
                    param.display_value = float(display_value)
                except Exception as e:
                    raise ValueError("Live would not take display_value %s for '%s': %s" % (display_value, param.name, str(e).strip()[:100]))
                landed = self._param_display_value(param)
                if landed is not None:
                    clamped = abs(landed - float(display_value)) > 1e-3 * max(1.0, abs(float(display_value)))
            else:
                value = float(value)
                if not float(param.min) <= value <= float(param.max):
                    raise ValueError(
                        "Value {0} is outside the range of parameter '{1}' ({2} to {3})".format(
                            value, param.name, float(param.min), float(param.max)))
                param.value = value
            result = {
                "track_index": track_index,
                "track_type": (track_type or "track").lower(),
                "device_index": device_index,
                "parameter_index": parameter_index,
                "name": param.name,
                "old_value": old,
                "value": float(param.value),
                "min": float(param.min),
                "max": float(param.max),
            }
            display = self._param_display(param)
            if display is not None:
                result["display"] = display
                result["old_display"] = old_display
            landed = self._param_display_value(param)
            if landed is not None:
                result["display_value"] = landed
            if display_value is not None:
                result["clamped"] = clamped
            return result
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    def get_browser_tree(self, category_type="all"):
        """
        Get a simplified tree of browser categories.
        
        Args:
            category_type: Type of categories to get ('all', 'instruments', 'sounds', etc.)
            
        Returns:
            Dictionary with the browser tree structure
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
            
            result = {
                "type": category_type,
                "categories": [],
                "available_categories": browser_attrs
            }
            
            # The full browser is far too large to serialise, so descend one
            # level and mark anything deeper with has_more. The MCP server
            # renders that as "[...]" and get_browser_items_at_path walks on
            # from there.
            max_depth = 1
            max_children = 64
            folder_count = [0]

            def process_item(item, depth=0):
                if not item:
                    return None

                children = getattr(item, 'children', None) or []
                is_folder = bool(children)
                if is_folder:
                    folder_count[0] += 1

                node = {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": is_folder,
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }

                if is_folder and depth >= max_depth:
                    node["has_more"] = True
                    return node

                for child in children[:max_children]:
                    try:
                        processed = process_item(child, depth + 1)
                    except Exception as e:
                        self.log_message("Error processing browser child: {0}".format(str(e)))
                        continue
                    if processed:
                        node["children"].append(processed)
                if len(children) > max_children:
                    node["has_more"] = True

                return node

            # Process based on category type and available attributes
            if (category_type == "all" or category_type == "instruments") and hasattr(app.browser, 'instruments'):
                try:
                    instruments = process_item(app.browser.instruments)
                    if instruments:
                        instruments["name"] = "Instruments"  # Ensure consistent naming
                        result["categories"].append(instruments)
                except Exception as e:
                    self.log_message("Error processing instruments: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "sounds") and hasattr(app.browser, 'sounds'):
                try:
                    sounds = process_item(app.browser.sounds)
                    if sounds:
                        sounds["name"] = "Sounds"  # Ensure consistent naming
                        result["categories"].append(sounds)
                except Exception as e:
                    self.log_message("Error processing sounds: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "drums") and hasattr(app.browser, 'drums'):
                try:
                    drums = process_item(app.browser.drums)
                    if drums:
                        drums["name"] = "Drums"  # Ensure consistent naming
                        result["categories"].append(drums)
                except Exception as e:
                    self.log_message("Error processing drums: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "audio_effects") and hasattr(app.browser, 'audio_effects'):
                try:
                    audio_effects = process_item(app.browser.audio_effects)
                    if audio_effects:
                        audio_effects["name"] = "Audio Effects"  # Ensure consistent naming
                        result["categories"].append(audio_effects)
                except Exception as e:
                    self.log_message("Error processing audio_effects: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "midi_effects") and hasattr(app.browser, 'midi_effects'):
                try:
                    midi_effects = process_item(app.browser.midi_effects)
                    if midi_effects:
                        midi_effects["name"] = "MIDI Effects"
                        result["categories"].append(midi_effects)
                except Exception as e:
                    self.log_message("Error processing midi_effects: {0}".format(str(e)))
            
            # Try to process other potentially available categories
            for attr in browser_attrs:
                if attr not in ['instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects'] and \
                   (category_type == "all" or category_type == attr):
                    try:
                        item = getattr(app.browser, attr)
                        if hasattr(item, 'children') or hasattr(item, 'name'):
                            category = process_item(item)
                            if category:
                                category["name"] = attr.capitalize()
                                result["categories"].append(category)
                    except Exception as e:
                        self.log_message("Error processing {0}: {1}".format(attr, str(e)))
            
            # The MCP server reports this back to the caller; without it the
            # header always claimed zero folders.
            result["total_folders"] = folder_count[0]

            self.log_message("Browser tree generated for {0} with {1} root categories".format(
                category_type, len(result['categories'])))
            return result
            
        except Exception as e:
            self._log_command_error("Error getting browser tree", e)
            raise
    
    def get_browser_items_at_path(self, path):
        """
        Get browser items at a specific path.
        
        Args:
            path: Path in the format "category/folder/subfolder"
                 where category is one of: instruments, sounds, drums, audio_effects, midi_effects
                 or any other available browser category
                 
        Returns:
            Dictionary with items at the specified path
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
                
            # Parse the path
            path_parts = path.split("/")
            if not path_parts:
                raise ValueError("Invalid path")
            
            # Determine the root category
            root_category = path_parts[0].lower()
            current_item = None
            
            # Check standard categories first
            if root_category == "instruments" and hasattr(app.browser, 'instruments'):
                current_item = app.browser.instruments
            elif root_category == "sounds" and hasattr(app.browser, 'sounds'):
                current_item = app.browser.sounds
            elif root_category == "drums" and hasattr(app.browser, 'drums'):
                current_item = app.browser.drums
            elif root_category == "audio_effects" and hasattr(app.browser, 'audio_effects'):
                current_item = app.browser.audio_effects
            elif root_category == "midi_effects" and hasattr(app.browser, 'midi_effects'):
                current_item = app.browser.midi_effects
            else:
                # Try to find the category in other browser attributes
                found = False
                for attr in browser_attrs:
                    if attr.lower() == root_category:
                        try:
                            current_item = getattr(app.browser, attr)
                            found = True
                            break
                        except Exception as e:
                            self.log_message("Error accessing browser attribute {0}: {1}".format(attr, str(e)))
                
                if not found:
                    # If we still haven't found the category, return available categories
                    return {
                        "path": path,
                        "error": "Unknown or unavailable category: {0}".format(root_category),
                        "available_categories": browser_attrs,
                        "items": []
                    }
            
            # Navigate through the path
            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:  # Skip empty parts
                    continue
                
                if not hasattr(current_item, 'children'):
                    return {
                        "path": path,
                        "error": "Item at '{0}' has no children".format('/'.join(path_parts[:i])),
                        "items": []
                    }
                
                found = False
                for child in current_item.children:
                    if hasattr(child, 'name') and child.name.lower() == part.lower():
                        current_item = child
                        found = True
                        break
                
                if not found:
                    return {
                        "path": path,
                        "error": "Path part '{0}' not found".format(part),
                        "items": []
                    }
            
            # Get items at the current path
            items = []
            if hasattr(current_item, 'children'):
                for child in current_item.children:
                    item_info = {
                        "name": child.name if hasattr(child, 'name') else "Unknown",
                        "is_folder": hasattr(child, 'children') and bool(child.children),
                        "is_device": hasattr(child, 'is_device') and child.is_device,
                        "is_loadable": hasattr(child, 'is_loadable') and child.is_loadable,
                        "uri": child.uri if hasattr(child, 'uri') else None
                    }
                    items.append(item_info)
            
            result = {
                "path": path,
                "name": current_item.name if hasattr(current_item, 'name') else "Unknown",
                "uri": current_item.uri if hasattr(current_item, 'uri') else None,
                "is_folder": hasattr(current_item, 'children') and bool(current_item.children),
                "is_device": hasattr(current_item, 'is_device') and current_item.is_device,
                "is_loadable": hasattr(current_item, 'is_loadable') and current_item.is_loadable,
                "items": items
            }
            
            self.log_message("Retrieved {0} items at path: {1}".format(len(items), path))
            return result
            
        except Exception as e:
            self._log_command_error("Error getting browser items at path", e)
            raise
