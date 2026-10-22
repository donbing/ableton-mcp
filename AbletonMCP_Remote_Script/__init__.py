# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import os
import socket
import json
import re
import math
import threading
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

# Bumped whenever the TCP command surface changes; the MCP server compares
# this to EXPECTED_REMOTE_SCRIPT_VERSION.
SCRIPT_VERSION = "1.10.1"

# Shown on every undo / redo reply. Live merges edits made through the API into
# a single undo step, so one undo can revert several MCP changes.
UNDO_WARNING = (
    "WARNING: Live merges API-originated edits into ONE undo step, so a single "
    "undo/redo may revert SEVERAL MCP changes (everything since the user's last "
    "manual action) and also the user's own recent manual edits. Verify the "
    "session state afterwards.")
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
                response["result"] = self._get_track_info(track_index)
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
                    params.get("seconds", 2.0), params.get("hz", 20))
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
                                 "create_locator",
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
                            result = self._create_audio_clip(track_index, clip_index, path)
                        elif command_type == "add_notes_to_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_clip(track_index, clip_index, notes)
                        elif command_type == "clear_notes_from_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._clear_notes_from_clip(track_index, clip_index)
                        elif command_type == "remove_notes_from_clip":
                            result = self._remove_notes_from_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("from_time"),
                                params.get("time_span"),
                                params.get("from_pitch"),
                                params.get("pitch_span"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True))
                        elif command_type == "apply_note_modifications":
                            result = self._apply_note_modifications(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("notes"),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True))
                        elif command_type == "quantize_clip":
                            result = self._quantize_clip(
                                params.get("track_index", 0),
                                params.get("clip_index", 0),
                                params.get("grid"),
                                params.get("amount", 1.0),
                                # Preview unless the caller explicitly opts out.
                                params.get("dry_run", True))
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
                        elif command_type == "create_locator":
                            name = params.get("name", "")
                            time_val = params.get("time", 0.0)
                            result = self._create_locator(name, time_val)
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
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})
                
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
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
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
                response["result"] = self._get_clip_notes(track_index, clip_index)
            elif command_type == "get_clip_info":
                response["result"] = self._get_clip_info(
                    params.get("track_index", 0), params.get("clip_index", 0))
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(
                    track_index, device_index,
                    name_contains=params.get("name_contains"),
                    limit=params.get("limit"),
                    include_racks=params.get("include_racks", False))
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
                    try:
                        result = self._set_device_parameter(
                            params.get("track_index", 0),
                            params.get("device_index", 0),
                            params.get("parameter_index", 0),
                            params.get("value", 0.0),
                        )
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})

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
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
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
    
    def _get_meters(self, seconds=2.0, hz=20):
        """Sample output_meter_left/right of every track over a time window.

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
                    stats.append({
                        "group": group, "index": index, "track": track,
                        "name": self._safe_attr(track, "name", str, ""),
                        "peak_left": 0.0, "peak_right": 0.0,
                        "sum_left": 0.0, "sum_right": 0.0, "n": 0,
                        "available": True,
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
                        left = float(st["track"].output_meter_left)
                        right = float(st["track"].output_meter_right)
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
            return result
        except Exception as e:
            self.log_message("Error getting meters: " + str(e))
            raise

    def _get_track_info(self, track_index):
        """Get information about a track"""
        try:
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

    def _create_audio_clip(self, track_index, clip_index, path):
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

            clip_slot.create_audio_clip(path)

            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length,
                "is_audio_clip": clip_slot.clip.is_audio_clip
            }
            return result
        except Exception as e:
            self.log_message("Error creating audio clip: " + str(e))
            raise

    def _add_notes_to_clip(self, track_index, clip_index, notes):
        """Add MIDI notes to a clip"""
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
            
            # Convert note data to Live's format
            live_notes = []
            for note in notes:
                pitch = note.get("pitch", 60)
                start_time = note.get("start_time", 0.0)
                duration = note.get("duration", 0.25)
                velocity = note.get("velocity", 100)
                mute = note.get("mute", False)
                
                live_notes.append((pitch, start_time, duration, velocity, mute))
            
            # Add the notes
            clip.set_notes(tuple(live_notes))
            
            result = {
                "note_count": len(notes)
            }
            return result
        except Exception as e:
            self.log_message("Error adding notes to clip: " + str(e))
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

            # Members first, group last. After each delete the indices have
            # moved, and Live may also drop a group once its last member is
            # gone, so re-find every victim by identity right before deleting
            # it and skip any that no longer exists. Never trust a stale index
            # on a destructive call.
            for victim in reversed(doomed):
                current = list(self._song.tracks)
                at = next((i for i, t in enumerate(current) if t == victim), None)
                if at is not None:
                    self._song.delete_track(at)
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
            self._song.current_song_time = float(time_val)
            return {"current_song_time": self._song.current_song_time}
        except Exception as e:
            self.log_message("Error setting current song time: " + str(e))
            raise

    def _get_arrangement_clips(self, track_index):
        """Return all clips placed in the Arrangement timeline for a track.

        Each clip dict contains:
          name, start_time, end_time, length, color,
          is_midi_clip, is_audio_clip, is_playing
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
                    "is_playing": clip.is_playing
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

    def _clear_notes_from_clip(self, track_index, clip_index):
        """Remove all MIDI notes from a Session clip.

        Pairs with _add_notes_to_clip to make a real replace (clear, then add),
        which the write-only API otherwise can't do. Counts notes first so the
        result can report how many were removed.
        """
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

    def _session_clip(self, track_index, clip_index, midi=False):
        """Return (track, clip) for a Session clip slot, with strict checks.

        Indices must be real integers (a bool or float is an error rather than
        silently coerced). midi=True also requires a MIDI clip.
        """
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

    def _get_clip_info(self, track_index, clip_index):
        """Read-only facts about one Session clip (MIDI or audio)."""
        try:
            track, clip = self._session_clip(track_index, clip_index)
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
                                from_pitch, pitch_span, dry_run=True):
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
            track, clip = self._session_clip(track_index, clip_index, midi=True)

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
            unknown = sorted(set(entry) - set(NOTE_EDIT_FIELDS) - set(["note_id"]))
            if unknown:
                raise ValueError(
                    "%s has unknown field(s) %s; allowed: note_id, %s"
                    % (label, ", ".join(unknown), ", ".join(NOTE_EDIT_FIELDS)))
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
            if not changes:
                raise ValueError(
                    "%s changes nothing; give at least one of %s"
                    % (label, ", ".join(NOTE_EDIT_FIELDS)))
            edits[note_id] = changes
        return edits

    def _apply_note_modifications(self, track_index, clip_index, notes, dry_run=True):
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
            track, clip = self._session_clip(track_index, clip_index, midi=True)
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
            live_notes = list(getter(0, 128, 0.0, read_span))
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
                before = self._note_summary(note)
                after = dict(before)
                for field, value in edits[note_id].items():
                    after[field] = value
                if all(before[f] == after[f] for f in NOTE_EDIT_FIELDS):
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

            for change, note in zip(changes, to_apply):
                for field in NOTE_EDIT_FIELDS:
                    if change["after"][field] != change["before"][field]:
                        setattr(note, field, change["after"][field])
            method = self._apply_modified_notes(clip, applier, to_apply, live_notes, changes)
            result["method"] = method

            reread = {}
            reread_notes = list(getter(0, 128, 0.0, read_span))
            for note in reread_notes:
                note_id = getattr(note, "note_id", None)
                if note_id is not None:
                    reread[int(note_id)] = self._note_summary(note)
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
                for field in NOTE_EDIT_FIELDS:
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

    def _apply_modified_notes(self, clip, applier, to_apply, live_notes, changes):
        """Hand edited notes to Live and return the method that worked.

        Real Live 12 Lite rejected both a list and a tuple of just the edited
        notes ("did not match C++ signature", run of 2026-10-22), so try the
        shapes in turn: the edited notes, then every note that was read (the
        pattern AbletonOSC uses), then remove + set_notes as a last resort
        (this one drops extra note fields such as probability and the note id).
        """
        errors = []
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

    def _quantize_clip(self, track_index, clip_index, grid, amount=1.0, dry_run=True):
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
            track, clip = self._session_clip(track_index, clip_index, midi=True)
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

    def _create_locator(self, name, time_val):
        """Create (or rename) a named locator at the given beat position.

        Uses Live's Song.set_or_delete_cue(), which toggles a cue at the
        current_song_time. We temporarily move the playhead, toggle, then
        restore. If a cue already exists at that time we just rename it
        instead of toggling (which would delete it).
        """
        try:
            song = self._song
            target_time = float(time_val)
            tolerance = 1e-3

            # See if a cue already exists at (or near) the target time
            existing = None
            for cue in song.cue_points:
                if abs(cue.time - target_time) < tolerance:
                    existing = cue
                    break

            original_time = song.current_song_time

            if existing is None:
                # Move playhead, toggle to create, then locate the new cue
                song.current_song_time = target_time
                song.set_or_delete_cue()
                for cue in song.cue_points:
                    if abs(cue.time - target_time) < tolerance:
                        existing = cue
                        break
                # Restore playhead
                try:
                    song.current_song_time = original_time
                except Exception:
                    pass

            if existing is None:
                raise Exception("Failed to create cue at time " + str(target_time))

            if name:
                try:
                    existing.name = str(name)
                except Exception as e:
                    self.log_message("Could not rename locator: " + str(e))

            return {
                "success": True,
                "time": existing.time,
                "name": existing.name,
            }
        except Exception as e:
            self.log_message("Error creating locator: " + str(e))
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
            self.log_message("Error getting browser item: " + str(e))
            self.log_message(traceback.format_exc())
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
            
            # Load the item
            app.browser.load_item(item)
            
            result = {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "uri": item_uri
            }
            return result
        except Exception as e:
            self.log_message("Error loading browser item: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
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
                        if with_display:
                            display = self._param_display(param)
                            if display is not None:
                                entry["display"] = display
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

    def _get_clip_notes(self, track_index, clip_index):
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            slot = track.clip_slots[clip_index]
            if not slot.has_clip:
                raise Exception("No clip in slot")
            clip = slot.clip
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
                               limit=None, include_racks=False):
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
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
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

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[parameter_index]
            old = float(param.value)
            param.value = float(value)
            return {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "name": param.name,
                "old_value": old,
                "value": float(param.value),
                "min": float(param.min),
                "max": float(param.max),
            }
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
            self.log_message("Error getting browser tree: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
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
            self.log_message("Error getting browser items at path: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
