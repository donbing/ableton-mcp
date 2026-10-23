# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
import socket
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Optional, Union

from .telemetry import record_startup
from .telemetry_decorator import telemetry_tool, rich_telemetry_tool
from .dataset import dataset_enabled, get_recorder
from .dataset.trajectory_decorator import trajectory_tool

ABLETON_HOST = os.environ.get("ABLETON_HOST", "localhost")
ABLETON_PORT = int(os.environ.get("ABLETON_PORT", "9877"))

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")

@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None

    # One socket, several threads: tool calls run on the MCP worker while the
    # passive poller drains events on its own thread. Serialise so their
    # sendall/recv pairs cannot interleave.
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        if self.sock:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton at {self.host}:{self.port}: {str(e)}")
            self.disconnect()
            return False
    
    def disconnect(self):
        """Disconnect from the Ableton Remote Script"""
        with self._lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception as e:
                    logger.error(f"Error disconnecting from Ableton: {str(e)}")
                finally:
                    self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive one JSON response using the command's socket timeout."""
        data = bytearray()
        while True:
            chunk = sock.recv(buffer_size)
            if not chunk:
                raise ConnectionError("Connection closed before receiving a complete response")
            data.extend(chunk)

            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError as e:
                # A TCP chunk may end between the bytes of a UTF-8 character.
                # Invalid bytes elsewhere are an error, not an incomplete frame.
                if e.reason == "unexpected end of data" and e.end == len(data):
                    continue
                raise

            try:
                json.loads(decoded)
            except json.JSONDecodeError:
                continue
            logger.info("Received complete response (%d bytes)", len(data))
            return bytes(data)

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response.

        Serialised on ``self._lock``: the request and its response are one
        indivisible exchange on a shared socket. Holding the lock across the
        whole round-trip (including reconnect) is what keeps a concurrent
        caller from reading someone else's reply.
        """
        with self._lock:
            return self._send_command_locked(command_type, params)

    def _send_command_locked(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")

        command = {
            "type": command_type,
            "params": params or {}
        }
        
        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "set_track_volume", "set_track_panning", "set_send",
            "set_track_mute", "set_track_solo", "set_track_arm",
            "set_audio_clip_warp", "set_audio_clip_gain", "set_audio_clip_pitch",
            "create_clip", "create_audio_clip", "add_notes_to_clip", "set_clip_name",
            "delete_clip",
            "delete_track",
            "delete_locator",
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
            "press_dialog_button",
            "set_track_monitoring", "duplicate_track",
            "replace_clip_notes", "set_color",
            "set_device_routing", "set_clip_envelope", "clear_clip_envelope",
            "back_to_arrangement", "set_track_routing",
            "clear_arrangement_range",
            "trim_arrangement_clip",
            "split_arrangement_clip",
            "move_arrangement_clip",
            "create_arrangement_clip",
            "create_scene", "delete_scene", "duplicate_scene", "fire_scene",
            "set_scene_name", "stop_all_clips",
            "delete_arrangement_clips", "delete_device",
            "clear_notes_from_clip",
            "set_clip_loop",
            "remove_notes_from_clip",
            "apply_note_modifications",
            "quantize_clip",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            "undo", "redo",
            # Arrangement view commands
            "switch_to_arrangement_view", "set_current_song_time",
            "duplicate_session_clip_to_arrangement",
            "create_locator",
            "create_return_track", "load_device_on_return",
            "set_time_signature", "set_metronome", "set_arrangement_loop",
            "jump_to_cue",
        ]

        # Commands whose work on Live's main thread can take noticeably longer
        # than the default modifying-command budget (e.g. importing/decoding a
        # large audio file). Give them a wider socket timeout so we don't time
        # out before the Remote Script's own queue does.
        long_running_commands = {"create_audio_clip": 65.0, "get_meters": 20.0}
        
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # Set timeout based on command type
            if command_type in long_running_commands:
                timeout = long_running_commands[command_type]
            else:
                timeout = 15.0 if is_modifying_command else 10.0
            self.sock.settimeout(timeout)

            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")

            # Parse the response
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")

            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Ableton"))
            
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.disconnect()
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.disconnect()
            raise Exception(f"Connection to Ableton lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.disconnect()
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.disconnect()
            raise Exception(f"Communication error with Ableton: {str(e)}")

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

        # Record startup event for telemetry
        try:
            record_startup()
        except Exception as e:
            logger.debug(f"Failed to record startup telemetry: {e}")

        script_info = None
        try:
            ableton = get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
            from .script_handshake import handshake

            script_info = handshake(ableton.send_command)
        except Exception as e:
            logger.warning(f"Could not connect to Ableton on startup: {str(e)}")
            logger.warning("Make sure the Ableton Remote Script is running")

        if dataset_enabled():
            try:
                recorder = get_recorder()
                if recorder:
                    logger.info(
                        "Dataset recording enabled → Supabase session %s",
                        recorder.session_id,
                    )
                from .script_handshake import script_has_capability
                from .dataset.passive_poller import start_passive_poller

                # Runs even without Live-UI events: it also settles implicit
                # preferences for agent actions.
                start_passive_poller()
                if not script_has_capability("drain_passive_events"):
                    logger.warning(
                        "Passive Live listeners unavailable — Remote Script outdated "
                        "or not loaded. Restart Ableton after script update."
                    )
            except Exception as e:
                logger.warning(f"Failed to start dataset recorder: {e}")
        else:
            reason = "unknown"
            try:
                from .config import telemetry_config  # noqa: F401
                from .telemetry import get_telemetry_consent, is_telemetry_enabled

                if not is_telemetry_enabled():
                    reason = "telemetry disabled (config.enabled=False or DISABLE_TELEMETRY)"
                elif not get_telemetry_consent():
                    reason = "no dataset consent yet — the user has not opted in"
                else:
                    reason = "ABLETON_MCP_DISABLE_DATASET or unexpected gate failure"
            except Exception:
                reason = "MCP_Server/config.py missing or unreadable (gitignored; required for Supabase)"
            logger.info("Dataset recording off — %s", reason)

        yield {"script_info": script_info}
    finally:
        global _ableton_connection
        try:
            from .dataset.passive_poller import stop_passive_poller

            stop_passive_poller()
        except Exception as e:
            logger.debug(f"Failed to stop passive poller: {e}")
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        try:
            recorder = get_recorder()
            if recorder:
                # Bounded wait so queued rows land before the daemon worker
                # is killed at exit.
                recorder.end(timeout=float(
                    os.environ.get("ABLETON_MCP_DATASET_FLUSH_SEC", "5")
                ))
        except Exception as e:
            logger.debug(f"Failed to end dataset session: {e}")
        logger.info("AbletonMCP server shut down")

# Create the MCP server with lifespan support
mcp = FastMCP(
    "AbletonMCP",
    lifespan=server_lifespan
)

# Global connection for resources
_ableton_connection = None

def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection

    if _ableton_connection is not None and _ableton_connection.sock is not None:
        try:
            # Check if the socket is still alive by peeking for data
            # MSG_PEEK + MSG_DONTWAIT will raise BlockingIOError if alive but no data,
            # or return b'' if the remote end has closed the connection.
            _ableton_connection.sock.setblocking(False)
            try:
                data = _ableton_connection.sock.recv(1, socket.MSG_PEEK)
                if data == b'':
                    raise ConnectionError("Remote end closed")
            except BlockingIOError:
                pass  # Socket is alive, just no data waiting — this is normal
            finally:
                _ableton_connection.sock.setblocking(True)
            return _ableton_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None
            # Passive events stop arriving while disconnected, so any cached
            # state hash may describe a Live session that has since moved on.
            try:
                recorder = get_recorder()
                if recorder:
                    recorder.invalidate_cached_state()
            except Exception:
                pass
    
    # Connection doesn't exist or is invalid, create a new one
    if _ableton_connection is None:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to Ableton at {ABLETON_HOST}:{ABLETON_PORT} (attempt {attempt}/{max_attempts})...")
                _ableton_connection = AbletonConnection(host=ABLETON_HOST, port=ABLETON_PORT)
                if _ableton_connection.connect():
                    logger.info("Created new persistent connection to Ableton")
                    return _ableton_connection
                else:
                    _ableton_connection = None
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {str(e)}")
                if _ableton_connection:
                    _ableton_connection.disconnect()
                    _ableton_connection = None

            if attempt < max_attempts:
                import time
                time.sleep(1.0)
        
        # If we get here, all connection attempts failed
        if _ableton_connection is None:
            logger.error("Failed to connect to Ableton after multiple attempts")
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")
    
    return _ableton_connection


# Core Tool endpoints

@mcp.tool()
def set_dataset_consent(ctx: Context, consent: bool, user_said: str = "") -> str:
    """Record the user's answer to the dataset consent question.

    Call this ONLY after the user has answered in their own words. Never infer
    the answer, never call it on their behalf, and never call it because
    contributing seems helpful — consent the user did not give is not consent.
    If they have not been asked yet, ask first and wait for their reply.

    Parameters:
    - consent: True if the user agreed to contribute, False if they declined
    - user_said: The user's reply, quoted as closely as possible
    """
    # Intentionally undecorated: recording this call would mean collecting data
    # from someone who may have just declined.
    try:
        from .dataset.consent import record_consent

        state = record_consent(consent, quote=user_said)
    except Exception as e:
        logger.error(f"Could not record dataset consent: {str(e)}")
        return f"Error recording consent: {str(e)}"

    if not consent:
        return (
            "Recorded: dataset contribution declined. Nothing is uploaded, and "
            "you will not be asked again."
        )

    try:
        from .telemetry import refresh_consent_from_dataset

        refresh_consent_from_dataset()
        recorder = get_recorder()
        # Under opt-in the poller is almost never started at boot — consent did
        # not exist yet — so a grant has to start it here or passive Live events
        # would be missed for the rest of the session. Idempotent and
        # self-gating, so this is safe even if startup did start it.
        from .dataset.passive_poller import start_passive_poller

        start_passive_poller()
    except Exception as e:
        logger.error(f"Consent saved but recording failed to start: {str(e)}")
        return (
            "Consent saved, but recording could not start in this session. "
            "It will begin after a restart."
        )

    if recorder is None:
        return (
            "Consent saved, but recording is unavailable (telemetry may be "
            f"disabled). State: {state}."
        )
    return (
        "Thank you — this session is now being contributed to the open dataset. "
        "Say so at any time to stop, or set ABLETON_MCP_DISABLE_DATASET=1."
    )


@mcp.tool()
@telemetry_tool("get_session_info")
@trajectory_tool("get_session_info")
def get_session_info(ctx: Context, user_prompt: str = "") -> str:
    """Get detailed information about the current Ableton session

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"


@mcp.tool()
@telemetry_tool("get_remote_script_info")
@trajectory_tool("get_remote_script_info", modifying=False)
def get_remote_script_info(ctx: Context, user_prompt: str = "") -> str:
    """
    Report Ableton Remote Script version and capabilities (handshake).

    Use this to verify the Live-side bridge matches this MCP server package.
    """
    try:
        from .remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION
        from .script_handshake import get_cached_script_info, handshake

        ableton = get_ableton_connection()
        info = handshake(ableton.send_command)
        cached = dict(get_cached_script_info() or info)
        cached["expected_version"] = EXPECTED_REMOTE_SCRIPT_VERSION
        return json.dumps(cached, indent=2)
    except Exception as e:
        logger.error(f"Error getting remote script info: {str(e)}")
        return f"Error getting remote script info: {str(e)}"

@mcp.tool()
@telemetry_tool("get_track_info")
@trajectory_tool("get_track_info")
def get_track_info(ctx: Context, track_index: int, track_type: str = "track",
                   user_prompt: str = "") -> str:
    """
    Get detailed information about a specific track in Ableton.

    Parameters:
    - track_index: The index of the track to get information about (ignored for "master")
    - track_type: "track" (default), "return" or "master". Returns and the master give
      their name, mixer and device list (no clips)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        params = {"track_index": track_index}
        if track_type != "track":
            params["track_type"] = track_type
        result = ableton.send_command("get_track_info", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track info from Ableton: {str(e)}")
        return f"Error getting track info: {str(e)}"


@mcp.tool()
@telemetry_tool("get_meters")
@trajectory_tool("get_meters")
def get_meters(
    ctx: Context,
    seconds: float = 2.0,
    hz: int = 20,
    user_prompt: str = "",
) -> str:
    """
    Measure output levels of every track, every return track and the master over
    a short time window, and report per-track peak and mean level.

    Samples Live's output meters (left and right) `hz` times a second for
    `seconds` seconds. Start playback first: meters read 0 when nothing plays.
    The call takes about `seconds` to return; it does not freeze Live.

    Raw values (peak, mean, peak_left, ...) are Live's own 0..1 meter readings.
    They are approximately LINEAR IN dB, NOT linear amplitude (about 0.01325 per
    dB, and roughly 0.85 = 0 dBFS, like a fader). Never convert with
    20*log10(raw): that is wrong by tens of dB. Each entry also carries
    peak_db_approx / mean_db_approx = (raw - 0.85) / 0.01325, measured on
    Live 12 Lite: accurate to about +-1 dB (1 sigma; single readings up to about +-4 dB) inside roughly -37..-7 dB and
    extrapolated (unverified) outside it. null means silence (raw <= 0.03).
    The response's `scale` object restates this. Use it for relative changes
    and rough levels, not as a calibrated meter.

    Parameters:
    - seconds: Window length, default 2.0, capped at 10
    - hz: Samples per second, default 20, clamped to 1..50
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_meters")
        if missing:
            return missing
        if seconds <= 0 or hz <= 0:
            return "Error getting meters: seconds and hz must be positive"
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_meters", {"seconds": min(float(seconds), 10.0), "hz": hz})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting meters: {str(e)}")
        return f"Error getting meters: {str(e)}"


def _clip_ref(track_index: int, clip_index: int, clip_start_time: Optional[float] = None) -> dict:
    """Which clip a note tool means: a Session slot, or an Arrangement clip by its start beat."""
    ref = {"track_index": track_index, "clip_index": clip_index}
    if clip_start_time is not None:
        ref["clip_start_time"] = clip_start_time
    return ref


@mcp.tool()
@telemetry_tool("get_clip_notes")
@trajectory_tool("get_clip_notes")
def get_clip_notes(
    ctx: Context,
    track_index: int,
    clip_index: int,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Read all MIDI notes from a clip: a Session clip, or an Arrangement MIDI clip with
    clip_start_time.

    Returns pitch, start_time, duration, velocity, mute (and extended fields when
    available). Times are in the clip's CONTENT, in beats: a clip that was trimmed
    or split at its head keeps all its notes and starts playing at start_marker
    (see get_arrangement_clips), so a note before start_marker is not heard.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_clip_notes")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_clip_notes",
            _clip_ref(track_index, clip_index, clip_start_time),
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip notes: {str(e)}")
        return f"Error getting clip notes: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@telemetry_tool("get_clip_info")
@trajectory_tool("get_clip_info")
def get_clip_info(
    ctx: Context,
    track_index: int,
    clip_index: int,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Read the facts about one Session clip: name, length (beats), looping,
    loop_start / loop_end and start_marker / end_marker (beats), is_playing,
    muted, color_index, and for MIDI clips the note count. Fields Live does not
    report are null. Read-only.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_clip_info")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_clip_info",
            _clip_ref(track_index, clip_index, clip_start_time),
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting clip info: {str(e)}")
        return f"Error getting clip info: {str(e)}"


@mcp.tool()
@telemetry_tool("get_device_parameters")
@trajectory_tool("get_device_parameters")
def get_device_parameters(
    ctx: Context,
    track_index: int,
    device_index: int,
    name_contains: Optional[str] = None,
    limit: Optional[int] = None,
    include_racks: bool = False,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Read the parameters of a device on a track, a return track or the master: name, value, min, max, and
    `display`, the string Live shows for the current value ("-6.0 dB", "1/8",
    "Sine", "2.4 kHz"). Use `display` to understand what a raw value means
    before changing it with set_device_parameter.

    Racks (Instrument, Audio Effect and Drum Racks) are returned as a compact
    summary by default: their own macro parameters plus chain and device names.
    Walking every chain can return hundreds of KB. Pass include_racks=true when
    you need the parameters of the devices nested inside.

    Each parameter's `index` is its index in device.parameters, even when the
    list is filtered, so it can be passed straight to set_device_parameter.

    Parameters:
    - track_index: Track that owns the device
    - device_index: Index into the track's device chain
    - name_contains: Optional case-insensitive filter on parameter names
      (for example "cutoff" or "attack")
    - limit: Optional maximum number of parameters returned per device
    - include_racks: false (default) summarises racks; true returns full chain contents
    - track_type: "track" (default), "return" or "master"; track_index is then the index
      among the returns (ignored for the master)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if name_contains is not None or limit is not None:
            from .script_handshake import require_capability

            missing = require_capability("get_device_parameters_v2")
            if missing:
                return missing
        if limit is not None and limit < 0:
            return "Error getting device parameters: limit must not be negative"
        params: Dict[str, Any] = {
            "track_index": track_index,
            "device_index": device_index,
        }
        if name_contains:
            params["name_contains"] = name_contains
        if limit is not None:
            params["limit"] = limit
        if include_racks:
            params["include_racks"] = True
        if track_type != "track":
            params["track_type"] = track_type
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_parameters", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return f"Error getting device parameters: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_device_parameter")
@trajectory_tool("set_device_parameter")
def set_device_parameter(
    ctx: Context,
    track_index: int,
    device_index: int,
    parameter_index: int,
    value: float,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Set a device parameter to a specific value (on a track, a return track or the master).

    Use get_device_parameters first to discover parameter indices and ranges.

    Parameters:
    - track_index: Track that owns the device (index among the returns when track_type is "return")
    - device_index: Index into the track's device chain
    - parameter_index: Index into device.parameters
    - value: New parameter value (Live parameter units)
    - track_type: "track" (default), "return" or "master" (track_index is ignored for the master)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "value": value,
        }
        if track_type != "track":
            params["track_type"] = track_type
        result = ableton.send_command("set_device_parameter", params)
        return (
            f"Set {result.get('name', 'parameter')} "
            f"{result.get('old_value')} → {result.get('value')}"
        )
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"


@mcp.tool()
@telemetry_tool("get_session_snapshot")
@trajectory_tool("get_session_snapshot")
def get_session_snapshot(
    ctx: Context,
    include_notes: bool = True,
    include_params: bool = True,
    user_prompt: str = "",
) -> str:
    """
    Capture a full project state snapshot for trajectory recording.

    Includes session metadata, every track (mixer, devices, session clips,
    arrangement clips), optional MIDI notes, and optional device parameters.
    Used to version musical state S_t → S_{t+1}.

    Parameters:
    - include_notes: Include MIDI note arrays in clips (default True)
    - include_params: Include device parameter values (default True)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_session_snapshot")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "get_session_snapshot",
            {
                "include_notes": include_notes,
                "include_params": include_params,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session snapshot: {str(e)}")
        return f"Error getting session snapshot: {str(e)}"


@mcp.tool()
@telemetry_tool("create_midi_track")
@trajectory_tool("create_midi_track")
def create_midi_track(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
    """
    Create a new MIDI track in the Ableton session.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_midi_track", {"index": index})
        return f"Created new MIDI track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating MIDI track: {str(e)}")
        return f"Error creating MIDI track: {str(e)}"


@mcp.tool()
@telemetry_tool("create_audio_track")
@trajectory_tool("create_audio_track")
def create_audio_track(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
    """
    Create a new audio track in the Ableton session.

    Use this for recorded or imported audio (samples, stems, vocals). For MIDI
    instruments use create_midi_track instead.

    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_audio_track", {"index": index})
        return f"Created new audio track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating audio track: {str(e)}")
        return f"Error creating audio track: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_track_name")
@trajectory_tool("set_track_name")
def set_track_name(ctx: Context, track_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a track.

    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"

def _set_track_flag(command: str, flag: str, track_index: int, enabled: bool,
                    track_type: str, expected_name: Optional[str]) -> str:
    """Shared body of set_track_mute / set_track_solo / set_track_arm."""
    try:
        from .script_handshake import require_capability

        missing = require_capability(command)
        if missing:
            return missing
        params: Dict[str, Any] = {
            "track_index": track_index,
            "enabled": enabled,
            "track_type": track_type,
        }
        if expected_name is not None:
            params["expected_name"] = expected_name
        result = get_ableton_connection().send_command(command, params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting track {flag}: {str(e)}")
        return f"Error setting track {flag}: {str(e)}"


@mcp.tool()
@telemetry_tool("set_track_mute")
@trajectory_tool("set_track_mute")
def set_track_mute(
    ctx: Context,
    track_index: int,
    mute: bool,
    track_type: str = "track",
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Mute or unmute a track. Works on regular, group and return tracks; the
    master track cannot be muted. Returns the previous and the new value.

    Parameters:
    - track_index: Index within the chosen track_type (ignored for "master")
    - mute: True to mute, False to unmute
    - track_type: "track" (default) or "return"
    - expected_name: Optional safety check. If given, the call fails unless the
      track at track_index currently has exactly this name (guards against
      stale indices)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _set_track_flag("set_track_mute", "mute", track_index, mute,
                           track_type, expected_name)


@mcp.tool()
@telemetry_tool("set_track_solo")
@trajectory_tool("set_track_solo")
def set_track_solo(
    ctx: Context,
    track_index: int,
    solo: bool,
    track_type: str = "track",
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Solo or unsolo a track. Works on regular, group and return tracks; the
    master track cannot be soloed. Returns the previous and the new value.
    With Live's "Exclusive Solo" preference on, soloing one track unsolos the
    others.

    Parameters:
    - track_index: Index within the chosen track_type (ignored for "master")
    - solo: True to solo, False to unsolo
    - track_type: "track" (default) or "return"
    - expected_name: Optional safety check. If given, the call fails unless the
      track at track_index currently has exactly this name (guards against
      stale indices)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _set_track_flag("set_track_solo", "solo", track_index, solo,
                           track_type, expected_name)


@mcp.tool()
@telemetry_tool("set_track_arm")
@trajectory_tool("set_track_arm")
def set_track_arm(
    ctx: Context,
    track_index: int,
    arm: bool,
    track_type: str = "track",
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Arm or disarm a track for recording. Only tracks that can be armed
    (MIDI and audio tracks) are accepted; group, return and master tracks have
    no arm state and are refused with an explanation. Returns the previous and
    the new value (read back from Live, so a refused arm shows as unchanged).
    With Live's "Exclusive Arm" preference on, arming one track disarms others.

    Parameters:
    - track_index: Index of the track
    - arm: True to arm, False to disarm
    - track_type: "track" (default)
    - expected_name: Optional safety check. If given, the call fails unless the
      track at track_index currently has exactly this name (guards against
      stale indices)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _set_track_flag("set_track_arm", "arm", track_index, arm,
                           track_type, expected_name)


@mcp.tool()
@rich_telemetry_tool("create_clip")
@trajectory_tool("create_clip")
def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0, user_prompt: str = "") -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.

    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_clip", {
            "track_index": track_index, 
            "clip_index": clip_index, 
            "length": length
        })
        return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
    except Exception as e:
        logger.error(f"Error creating clip: {str(e)}")
        return f"Error creating clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("create_audio_clip")
@trajectory_tool("create_audio_clip")
def create_audio_clip(ctx: Context, track_index: int, clip_index: int, path: str,
                      warping: Optional[bool] = None, user_prompt: str = "") -> str:
    """
    Create a new audio clip in an audio track's clip slot by importing a file.

    Requires Ableton Live 12.0.5 or newer — the underlying
    ClipSlot.create_audio_clip Live API was introduced in 12.0.5 and is not
    available in earlier 12.0.x releases.

    Live imports with auto-warp ON, which can round the clip's length to a
    whole-bar / power-of-two number of beats, so the clip drifts against the set.
    The reply says whether the clip is warped, the file's own length, and warns
    when the two disagree; pass warping=false to keep the file's own timing (the
    clip's length then reads in seconds).

    Parameters:
    - track_index: The index of the audio track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - path: Absolute path to a supported audio file (e.g. a .wav). The target
      track must be an audio track and the clip slot must be empty.
    - warping: Optional. false = switch warp off after importing, true = leave it on;
      leave out to keep Live's default (on)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        params = {"track_index": track_index, "clip_index": clip_index, "path": path}
        if warping is not None:
            params["warping"] = warping
        result = ableton.send_command("create_audio_clip", params)
        unit = result.get("length_unit", "beats")
        message = (f"Created audio clip '{result.get('name', 'clip')}' at track {track_index}, "
                   f"slot {clip_index} (length {result.get('length', '?')} {unit})")
        if "warping" in result:
            message += f", warping {'on' if result['warping'] else 'off'}"
        if result.get("file_seconds") is not None:
            message += f", file {result['file_seconds']:.3f} s"
        if result.get("warning"):
            message += f". WARNING: {result['warning']}"
        return message
    except Exception as e:
        logger.error(f"Error creating audio clip: {str(e)}")
        return f"Error creating audio clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("add_notes_to_clip", capture_notes=True)
@trajectory_tool("add_notes_to_clip")
def add_notes_to_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]],
    clip_start_time: Optional[float] = None,
    user_prompt: str = ""
) -> str:
    """
    Add MIDI notes to a clip. The reply says how many notes the clip really holds
    afterwards and lists any note that was refused.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries. Fields: pitch, start_time (beats from the
      clip start), duration, velocity, mute, and optionally probability (0-1),
      velocity_deviation (-127..127), release_velocity (0-127). An unknown field
      is an error. A note that starts before 0 or at or after the clip's end
      would never play, so it is NOT added and is listed in the reply.
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        params = _clip_ref(track_index, clip_index, clip_start_time)
        params["notes"] = notes
        result = ableton.send_command("add_notes_to_clip", params)
        added = result.get("note_count", len(notes)) if isinstance(result, dict) else len(notes)
        message = f"Added {added} notes to clip at track {track_index}, slot {clip_index}"
        rejected = result.get("rejected") if isinstance(result, dict) else None
        if rejected:
            details = "; ".join(
                f"note {r['index']} (pitch {r['pitch']}, start {r['start_time']}): {r['reason']}"
                for r in rejected)
            message += f". NOT added ({len(rejected)} of {len(notes)}): {details}"
        if isinstance(result, dict) and result.get("warning"):
            message += f". WARNING: {result['warning']}"
        return message
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("clear_notes_from_clip")
def clear_notes_from_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    clip_start_time: Optional[float] = None,
    user_prompt: str = ""
) -> str:
    """
    Remove all MIDI notes from a Session clip.

    Writes are additive (add_notes_to_clip only appends), so to truly *modify*
    a clip you clear it first, then add the new notes. Use this with
    get_clip_notes and add_notes_to_clip for a real read -> modify -> write
    loop: read the notes, edit the list, clear_notes_from_clip, then
    add_notes_to_clip the edited notes.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("clear_notes_from_clip")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "clear_notes_from_clip", _clip_ref(track_index, clip_index, clip_start_time))
        return "Cleared {n} note(s) from clip '{name}' (track {t}, slot {c})".format(
            n=result.get("cleared_count", "?"),
            name=result.get("clip_name", "clip"),
            t=track_index,
            c=clip_index,
        )
    except Exception as e:
        logger.error(f"Error clearing notes from clip: {str(e)}")
        return f"Error clearing notes from clip: {str(e)}"

@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("remove_notes_from_clip")
@trajectory_tool("remove_notes_from_clip")
def remove_notes_from_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    from_time: float,
    time_span: float,
    from_pitch: int,
    pitch_span: int,
    confirm: bool = False,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Remove the MIDI notes inside a time and pitch window of a Session clip, in
    two steps. DESTRUCTIVE (Live's undo, Cmd/Ctrl+Z, can bring them back).

    Step 1: call with confirm=false (the default). Nothing is removed; you get
    the number of notes the window selects and a sample of them.
    Step 2: call again with the same arguments and confirm=true to remove them.

    The window is from_time/time_span in beats and from_pitch/pitch_span,
    evaluated by Live's own note query; the preview runs the same query as the
    removal, so it shows exactly what would go (Live decides how notes that
    straddle the window edge count). All four window values are required. To
    empty the whole clip use clear_notes_from_clip instead.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - from_time: Window start in beats (>= 0)
    - time_span: Window length in beats (> 0)
    - from_pitch: Lowest MIDI pitch in the window (0-127)
    - pitch_span: Number of pitches in the window (1-128; from_pitch + pitch_span <= 128)
    - confirm: false = preview only (default), true = remove
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("remove_notes_from_clip")
        if missing:
            return missing
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "from_time": from_time,
            "time_span": time_span,
            "from_pitch": from_pitch,
            "pitch_span": pitch_span,
        }
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        if not confirm:
            preview = ableton.send_command(
                "remove_notes_from_clip", dict(params, dry_run=True))
            return (
                "NOT REMOVED (preview only). This window selects "
                + json.dumps(preview, indent=2)
                + "\nTo remove these notes, call remove_notes_from_clip again with "
                "the same arguments and confirm=true."
            )
        result = ableton.send_command(
            "remove_notes_from_clip", dict(params, dry_run=False))
        return "Removed notes. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error removing notes from clip: {str(e)}")
        return f"Error removing notes from clip: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("apply_note_modifications")
@trajectory_tool("apply_note_modifications")
def apply_note_modifications(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Union[int, float, bool]]],
    confirm: bool = False,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Edit EXISTING notes of a Session MIDI clip in place, by note_id, in two
    steps. This rewrites notes (Live's undo, Cmd/Ctrl+Z, reverts it).

    Read the clip with get_clip_notes first: every note has a note_id. Each
    entry here is {"note_id": 12, ...} plus any of pitch, start_time (beats),
    duration (beats), velocity (1-127) and mute; only the fields you give
    change. An unknown note_id is an error and nothing changes. Ids are only
    valid until notes are added or removed, so re-read before editing.

    Step 1: call with confirm=false (the default). Nothing changes; you get the
    before and the proposed after of every note that would change.
    Step 2: call again with the same notes and confirm=true to apply them. The
    result lists before and after as read back from Live, and flags any value
    Live did not keep.

    Needs Live 11 or newer. To add notes use add_notes_to_clip; to delete
    notes use remove_notes_from_clip.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - notes: List of {"note_id": int, and any of "pitch", "start_time", "duration", "velocity", "mute"}
    - confirm: false = preview only (default), true = apply
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("apply_note_modifications")
        if missing:
            return missing
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes,
        }
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        if not confirm:
            preview = ableton.send_command(
                "apply_note_modifications", dict(params, dry_run=True))
            return (
                "NOT APPLIED (preview only). These notes would change: "
                + json.dumps(preview, indent=2)
                + "\nTo apply, call apply_note_modifications again with the same "
                "notes and confirm=true."
            )
        result = ableton.send_command(
            "apply_note_modifications", dict(params, dry_run=False))
        return "Applied note modifications. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error applying note modifications: {str(e)}")
        return f"Error applying note modifications: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("quantize_clip")
@trajectory_tool("quantize_clip")
def quantize_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    grid: str,
    amount: float = 1.0,
    confirm: bool = False,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Quantize a Session MIDI clip to a grid, in two steps. REWRITES the start
    time of the notes in the whole clip (Live's undo, Cmd/Ctrl+Z, reverts it).

    Step 1: call with confirm=false (the default). Nothing changes; you get how
    many notes would move and a sample of their estimated new starts.
    Step 2: call again with the same arguments and confirm=true. The result
    lists the starts as read back from Live.

    Grids: 1/4, 1/8, 1/8T (eighth triplet), 1/16, 1/16T (sixteenth triplet),
    1/32. amount runs from 0 (no movement) to 1 (every start lands on the grid);
    lower values pull notes only part of the way, which keeps some feel.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - grid: One of 1/4, 1/8, 1/8T, 1/16, 1/16T, 1/32
    - amount: 0.0 to 1.0, default 1.0
    - confirm: false = preview only (default), true = quantize
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("quantize_clip")
        if missing:
            return missing
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "grid": grid,
            "amount": amount,
        }
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        if not confirm:
            preview = ableton.send_command("quantize_clip", dict(params, dry_run=True))
            return (
                "NOT QUANTIZED (preview only). This would happen: "
                + json.dumps(preview, indent=2)
                + "\nTo quantize, call quantize_clip again with the same arguments "
                "and confirm=true."
            )
        result = ableton.send_command("quantize_clip", dict(params, dry_run=False))
        return "Quantized clip. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error quantizing clip: {str(e)}")
        return f"Error quantizing clip: {str(e)}"


@mcp.tool()
@telemetry_tool("set_clip_loop")
@trajectory_tool("set_clip_loop")
def set_clip_loop(
    ctx: Context,
    track_index: int,
    clip_index: int,
    loop_start: float,
    loop_end: float,
    looping: Optional[bool] = None,
    user_prompt: str = "",
) -> str:
    """
    Set the loop range of a Session clip, in beats, and optionally turn
    looping on or off. Notes are not touched (a shorter loop only stops the
    later notes from playing).

    loop_start must be >= 0 and before loop_end. The Remote Script writes the
    two markers in an order Live accepts, then reads the clip back; if Live
    did not keep the values the previous loop is restored and an error is
    returned. Use get_clip_info to see the current loop first.

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot index
    - loop_start: Loop start in beats from the clip start
    - loop_end: Loop end in beats; must be greater than loop_start
    - looping: true/false to switch clip looping, omit to leave it unchanged
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_clip_loop")
        if missing:
            return missing
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "clip_index": clip_index,
            "loop_start": loop_start,
            "loop_end": loop_end,
        }
        if looping is not None:
            params["looping"] = looping
        result = ableton.send_command("set_clip_loop", params)
        return "Loop set. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting clip loop: {str(e)}")
        return f"Error setting clip loop: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_clip_name")
@trajectory_tool("set_clip_name")
def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting clip name: {str(e)}")
        return f"Error setting clip name: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_arrangement_clip_name")
@trajectory_tool("set_arrangement_clip_name")
def set_arrangement_clip_name(ctx: Context, track_index: int, clip_index: int, name: str, user_prompt: str = "") -> str:
    """
    Set the name of a clip placed in the Arrangement timeline.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip within track.arrangement_clips, in the
      same order returned by get_arrangement_clips (i.e. ordered by start_time)
    - name: The new name for the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed arrangement clip at track {track_index}, index {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting arrangement clip name: {str(e)}")
        return f"Error setting arrangement clip name: {str(e)}"

def _audio_clip_call(command: str, label: str, params: Dict[str, Any]) -> str:
    """Shared body of the audio clip tools: handshake, send, JSON result."""
    try:
        from .script_handshake import require_capability

        missing = require_capability(command)
        if missing:
            return missing
        result = get_ableton_connection().send_command(command, params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error {label}: {str(e)}")
        return f"Error {label}: {str(e)}"


@mcp.tool()
@telemetry_tool("get_audio_clip_info")
@trajectory_tool("get_audio_clip_info")
def get_audio_clip_info(
    ctx: Context,
    track_index: int,
    clip_index: int,
    arrangement: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Read an audio clip's properties: name, length (beats), warping, warp_mode
    (number and name), gain (raw 0..1 plus Live's display string), pitch_coarse
    (semitones), pitch_fine (cents), loop_start/loop_end, start_marker/end_marker,
    file_path and the warp marker list. Use it to find out whether Live
    auto-warped or length-rounded a clip made by create_audio_clip. MIDI clips
    and empty slots are refused with an error.

    Parameters:
    - track_index: The index of the track
    - clip_index: Session slot index, or (arrangement=True) the position in the
      track's arrangement clips, the same order get_arrangement_clips returns
    - arrangement: False (default) reads a Session slot, True an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _audio_clip_call("get_audio_clip_info", "getting audio clip info", {
        "track_index": track_index, "clip_index": clip_index,
        "arrangement": arrangement})


@mcp.tool()
@telemetry_tool("set_audio_clip_warp")
@trajectory_tool("set_audio_clip_warp")
def set_audio_clip_warp(
    ctx: Context,
    track_index: int,
    clip_index: int,
    warping: bool,
    warp_mode: Optional[Union[str, int]] = None,
    arrangement: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Turn warping on or off for an audio clip and optionally choose the warp
    mode. Returns the previous and the new value. WARNING: changing warp on a
    clip can change what plays (timing, pitch and length behaviour); check the
    result and listen. MIDI clips and empty slots are refused.

    Parameters:
    - track_index: The index of the track
    - clip_index: Session slot index, or (arrangement=True) the position in the
      track's arrangement clips, the same order get_arrangement_clips returns
    - warping: True to warp the clip, False to play it unwarped
    - warp_mode: Optional. One of Beats (0), Tones (1), Texture (2), Re-Pitch (3),
      Complex (4), Complex Pro (6), given as the name or the number. Anything
      else is refused. Left unchanged when omitted
    - arrangement: False (default) for a Session slot, True for an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    params: Dict[str, Any] = {
        "track_index": track_index, "clip_index": clip_index,
        "warping": warping, "arrangement": arrangement}
    if warp_mode is not None:
        params["warp_mode"] = warp_mode
    return _audio_clip_call("set_audio_clip_warp", "setting audio clip warp", params)


@mcp.tool()
@telemetry_tool("set_audio_clip_gain")
@trajectory_tool("set_audio_clip_gain")
def set_audio_clip_gain(
    ctx: Context,
    track_index: int,
    clip_index: int,
    gain: float,
    arrangement: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Set an audio clip's gain. The value is Live's raw Clip.gain in 0.0..1.0, NOT
    dB and not linear amplitude; the result includes gain_display_string, the
    text Live shows for it, so read that to see the dB. Values outside 0..1 are
    refused. Returns the previous and the new value. MIDI clips and empty slots
    are refused.

    Parameters:
    - track_index: The index of the track
    - clip_index: Session slot index, or (arrangement=True) the position in the
      track's arrangement clips, the same order get_arrangement_clips returns
    - gain: Raw gain, 0.0 to 1.0
    - arrangement: False (default) for a Session slot, True for an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _audio_clip_call("set_audio_clip_gain", "setting audio clip gain", {
        "track_index": track_index, "clip_index": clip_index, "gain": gain,
        "arrangement": arrangement})


@mcp.tool()
@telemetry_tool("set_audio_clip_pitch")
@trajectory_tool("set_audio_clip_pitch")
def set_audio_clip_pitch(
    ctx: Context,
    track_index: int,
    clip_index: int,
    pitch_coarse: Optional[int] = None,
    pitch_fine: Optional[float] = None,
    arrangement: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Transpose an audio clip. Give pitch_coarse (whole semitones, -48 to 48)
    and/or pitch_fine (cents, -50 to 50); out-of-range values are refused and
    nothing is changed. Returns the previous and the new values. The transpose
    may have no audible effect on a clip that is not warped. MIDI clips and
    empty slots are refused.

    Parameters:
    - track_index: The index of the track
    - clip_index: Session slot index, or (arrangement=True) the position in the
      track's arrangement clips, the same order get_arrangement_clips returns
    - pitch_coarse: Semitones, -48 to 48. Left unchanged when omitted
    - pitch_fine: Cents, -50.0 to 50.0. Left unchanged when omitted
    - arrangement: False (default) for a Session slot, True for an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    params: Dict[str, Any] = {
        "track_index": track_index, "clip_index": clip_index,
        "arrangement": arrangement}
    if pitch_coarse is not None:
        params["pitch_coarse"] = pitch_coarse
    if pitch_fine is not None:
        params["pitch_fine"] = pitch_fine
    return _audio_clip_call("set_audio_clip_pitch", "setting audio clip pitch", params)


@mcp.tool()
@rich_telemetry_tool("set_tempo")
@trajectory_tool("set_tempo")
def set_tempo(ctx: Context, tempo: float, user_prompt: str = "") -> str:
    """
    Set the tempo of the Ableton session.

    Parameters:
    - tempo: The new tempo in BPM
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_tempo", {"tempo": tempo})
        return f"Set tempo to {tempo} BPM"
    except Exception as e:
        logger.error(f"Error setting tempo: {str(e)}")
        return f"Error setting tempo: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("load_instrument_or_effect")
@trajectory_tool("load_instrument_or_effect")
def load_instrument_or_effect(ctx: Context, track_index: int, uri: str, user_prompt: str = "") -> str:
    """
    Load an instrument or effect onto a track using its URI.

    Parameters:
    - track_index: The index of the track to load the instrument on
    - uri: The URI of the instrument or effect to load (e.g., 'query:Synths#Instrument%20Rack:Bass:FileId_5116')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": uri
        })
        
        # Check if the instrument was loaded successfully
        if result.get("loaded", False):
            new_devices = result.get("new_devices", [])
            if new_devices:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
            else:
                devices = result.get("devices_after", [])
                return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices)}"
        else:
            warning = result.get("warning")
            detail = f": {warning}" if warning else ""
            return f"Failed to load instrument with URI '{uri}'{detail}"
    except Exception as e:
        logger.error(f"Error loading instrument by URI: {str(e)}")
        return f"Error loading instrument by URI: {str(e)}"

@mcp.tool()
@telemetry_tool("fire_clip")
@trajectory_tool("fire_clip")
def fire_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Start playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Started playing clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error firing clip: {str(e)}")
        return f"Error firing clip: {str(e)}"

@mcp.tool()
@telemetry_tool("stop_clip")
@trajectory_tool("stop_clip")
def stop_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Stop playing a clip.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Stopped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error stopping clip: {str(e)}")
        return f"Error stopping clip: {str(e)}"


@mcp.tool()
@telemetry_tool("delete_clip")
def delete_clip(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
    """
    Delete the clip in the given clip slot, freeing it for reuse.

    Use this before create_clip when you want to overwrite an existing clip
    (create_clip itself refuses to write into an occupied slot).

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot to clear
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_clip")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("delete_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting clip: {str(e)}")
        return f"Error deleting clip: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("delete_track")
@trajectory_tool("delete_track")
def delete_track(
    ctx: Context,
    track_index: int,
    expected_name: str,
    confirm: bool = False,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Delete one track, in two steps. DESTRUCTIVE: remaining track indices shift.

    Step 1: call with confirm=false (the default). Nothing is deleted; you get a
    preview with the track's name, type, devices, clip counts, any group members
    that would go with it, and the track list as it would look afterwards.
    Step 2: call again with the same track_index and expected_name and
    confirm=true to delete it.

    Deletion only happens when confirm=true AND expected_name equals the track's
    current name. A mismatch (usually a stale index) deletes nothing. Only regular
    tracks can be deleted: return and master tracks, and the last remaining track,
    are refused. Deleting a group track also deletes the tracks inside it. After a
    delete, use the returned track list: every later track moved down by one.
    Deletions go into Live's undo history (Cmd/Ctrl+Z); a group may need one
    undo per track.

    Parameters:
    - track_index: Index of the track to delete
    - expected_name: The track's exact current name (required safety check)
    - confirm: false = preview only (default), true = delete
    - track_type: "track" (default). "return" and "master" are refused.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_track")
        if missing:
            return missing
        if not expected_name:
            return ("Error deleting track: expected_name is required. Read the "
                    "track's current name with get_track_info and pass it exactly.")
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "expected_name": expected_name,
            "track_type": track_type,
        }
        if not confirm:
            preview = ableton.send_command("delete_track", dict(params, dry_run=True))
            return (
                "NOT DELETED (preview only). This would delete: "
                + json.dumps(preview, indent=2)
                + "\nTo delete, call delete_track again with the same track_index "
                "and expected_name and confirm=true."
            )
        result = ableton.send_command("delete_track", dict(params, dry_run=False))
        return "Deleted track. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting track: {str(e)}")
        return f"Error deleting track: {str(e)}"


# ── Session scenes ───────────────────────────────────────────────────────────
# Adapted from ahujasid/ableton-mcp#99 (Zachary May). Scene indices shift after
# every create, duplicate and delete, so each reply carries the re-indexed list.

def _scene_command(command: str, params: Dict[str, Any], doing: str) -> str:
    """Shared body of the scene tools: capability check, send, JSON reply."""
    try:
        from .script_handshake import require_capability

        missing = require_capability(command)
        if missing:
            return missing
        result = get_ableton_connection().send_command(command, params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error {doing}: {str(e)}")
        return f"Error {doing}: {str(e)}"


@mcp.tool()
@telemetry_tool("get_scenes")
@trajectory_tool("get_scenes", modifying=False)
def get_scenes(ctx: Context, user_prompt: str = "") -> str:
    """
    List the Session scenes (the rows of the Session view).

    Each scene has: index, name (an empty string means the scene is unnamed),
    tempo (-1 = the scene has no tempo of its own), is_triggered (queued to
    launch) and clip_count (clips it holds across all tracks).

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _scene_command("get_scenes", {}, "getting scenes")


@mcp.tool()
@telemetry_tool("create_scene")
@trajectory_tool("create_scene")
def create_scene(ctx: Context, index: int = -1, name: str = "",
                 user_prompt: str = "") -> str:
    """
    Create an empty scene. Scenes after it move down by one; the reply has the
    new, re-indexed scene list. Live Lite limits how many scenes a set may have:
    when Live refuses, this returns a readable error and changes nothing.

    Parameters:
    - index: Position for the new scene (-1, the default, appends at the end)
    - name: Optional name for the new scene
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    params: Dict[str, Any] = {"index": index}
    if name:
        params["name"] = name
    return _scene_command("create_scene", params, "creating scene")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("delete_scene")
@trajectory_tool("delete_scene")
def delete_scene(
    ctx: Context,
    scene_index: int,
    expected_name: str,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Delete one scene and the clips in it, in two steps. DESTRUCTIVE: later scene
    indices shift down by one.

    Step 1: call with confirm=false (the default). Nothing is deleted; you get a
    preview with the scene's name, tempo, how many clips it holds (and which),
    and the scene list as it would look afterwards.
    Step 2: call again with the same scene_index and expected_name and
    confirm=true to delete it.

    Deletion only happens when confirm=true AND expected_name equals the scene's
    current name. A mismatch (usually a stale index) deletes nothing. A scene
    with no name has the name "" (empty string): pass "" exactly. The last
    remaining scene is refused. Deletions go into Live's undo history
    (Cmd/Ctrl+Z).

    Parameters:
    - scene_index: Index of the scene to delete
    - expected_name: The scene's exact current name (required safety check)
    - confirm: false = preview only (default), true = delete
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_scene")
        if missing:
            return missing
        if expected_name is None:
            return ("Error deleting scene: expected_name is required. Read the "
                    "scene's current name with get_scenes and pass it exactly "
                    "(\"\" for an unnamed scene).")
        ableton = get_ableton_connection()
        params = {"scene_index": scene_index, "expected_name": expected_name}
        if not confirm:
            preview = ableton.send_command("delete_scene", dict(params, dry_run=True))
            return (
                "NOT DELETED (preview only). This would delete: "
                + json.dumps(preview, indent=2)
                + "\nTo delete, call delete_scene again with the same scene_index "
                "and expected_name and confirm=true."
            )
        result = ableton.send_command("delete_scene", dict(params, dry_run=False))
        return "Deleted scene. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting scene: {str(e)}")
        return f"Error deleting scene: {str(e)}"


@mcp.tool()
@telemetry_tool("duplicate_scene")
@trajectory_tool("duplicate_scene")
def duplicate_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
    """
    Duplicate a scene, clips included. The copy goes right after the original, so
    later scenes move down by one; the reply has the new scene list. Live Lite may
    refuse extra scenes: you then get a readable error and nothing changes.

    Parameters:
    - scene_index: Index of the scene to duplicate
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _scene_command("duplicate_scene", {"scene_index": scene_index},
                          "duplicating scene")


@mcp.tool()
@telemetry_tool("fire_scene")
@trajectory_tool("fire_scene")
def fire_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
    """
    Launch a scene: starts every clip in that row. THIS IS AUDIBLE and it starts
    playback if the set is stopped. Tracks with a clip in the scene also leave the
    Arrangement (they stay off it until the user presses Back to Arrangement), and
    clips already playing on those tracks are replaced. Launch timing follows the
    set's global launch quantization.

    Parameters:
    - scene_index: Index of the scene to launch
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _scene_command("fire_scene", {"scene_index": scene_index},
                          "firing scene")


@mcp.tool()
@telemetry_tool("set_scene_name")
@trajectory_tool("set_scene_name")
def set_scene_name(ctx: Context, scene_index: int, name: str,
                   user_prompt: str = "") -> str:
    """
    Rename a scene. Returns the previous name and the scene list.

    Parameters:
    - scene_index: Index of the scene
    - name: New name ("" clears it back to unnamed)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _scene_command("set_scene_name",
                          {"scene_index": scene_index, "name": name},
                          "setting scene name")


@mcp.tool()
@telemetry_tool("stop_all_clips")
@trajectory_tool("stop_all_clips")
def stop_all_clips(ctx: Context, user_prompt: str = "") -> str:
    """
    Stop every playing Session clip (like Live's Stop All Clips button). Audible:
    playing material goes quiet, according to each clip's launch quantization. The
    transport and the Arrangement are not touched.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _scene_command("stop_all_clips", {}, "stopping all clips")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("delete_arrangement_clips")
@trajectory_tool("delete_arrangement_clips")
def delete_arrangement_clips(
    ctx: Context,
    track_index: int,
    expected_name: str,
    start_time: float,
    end_time: float,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Delete Arrangement clips on one track, in two steps. DESTRUCTIVE.

    Selection rule: every clip whose START lies in [start_time, end_time) is
    selected (start inclusive, end exclusive). A clip that starts before
    start_time but runs into the range is NOT selected; neither is a clip that
    starts exactly at end_time. Units are BEATS, absolute from the start of the
    Arrangement (0.0 = the very beginning; 4.0 = bar 2 in 4/4). Use
    get_arrangement_clips first to see start times.

    Step 1: call with confirm=false (the default). Nothing is deleted; you get
    the clips that would be deleted and the clips that would remain.
    Step 2: call again with the same arguments and confirm=true.

    Deletion only happens when confirm=true AND expected_name equals the
    track's current name (a mismatch, usually a stale index, deletes nothing).
    Refused, with nothing deleted: start_time >= end_time, more than 64 matching
    clips, group tracks, return/master tracks (only regular tracks are
    addressed), and Live versions without Track.delete_clip. The reply lists
    the remaining clips, indexed as get_arrangement_clips indexes them: after a
    delete, later clips have new indices, so re-read before using clip_index.
    Session clips are not touched (use delete_clip for those).

    Parameters:
    - track_index: Index of the regular track
    - expected_name: The track's exact current name (required safety check)
    - start_time: Range start in beats from the start of the Arrangement
    - end_time: Range end in beats (exclusive); must be greater than start_time
    - confirm: false = preview only (default), true = delete
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_arrangement_clips")
        if missing:
            return missing
        if not expected_name:
            return ("Error deleting arrangement clips: expected_name is required. "
                    "Read the track's current name with get_track_info and pass "
                    "it exactly.")
        if start_time >= end_time:
            return ("Error deleting arrangement clips: start_time must be less "
                    "than end_time (both in beats). Nothing was deleted.")
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "expected_name": expected_name,
            "start_time": start_time,
            "end_time": end_time,
        }
        if not confirm:
            preview = ableton.send_command(
                "delete_arrangement_clips", dict(params, confirm=False))
            return (
                "NOT DELETED (preview only). This would delete: "
                + json.dumps(preview, indent=2)
                + "\nTo delete, call delete_arrangement_clips again with the "
                "same arguments and confirm=true."
            )
        result = ableton.send_command(
            "delete_arrangement_clips", dict(params, confirm=True))
        return "Deleted arrangement clips. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting arrangement clips: {str(e)}")
        return f"Error deleting arrangement clips: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("delete_device")
@trajectory_tool("delete_device")
def delete_device(
    ctx: Context,
    track_index: int,
    device_index: int,
    expected_name: str,
    expected_device_name: str,
    confirm: bool = False,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Delete one device from a track's device chain, in two steps. DESTRUCTIVE:
    later devices in the chain shift down by one.

    Step 1: call with confirm=false (the default). Nothing is deleted; you get
    the track's device chain with the target marked "to_delete".
    Step 2: call again with the same arguments and confirm=true.

    Deletion only happens when confirm=true AND both names match: expected_name
    is the track's exact current name and expected_device_name is the exact
    name of the device at device_index. Either mismatch (a stale index) deletes
    nothing. Only devices at the top level of the track's chain are addressed,
    not devices nested inside a rack's chains. The master track is refused.
    The reply carries the remaining chain with its new indices. Read the chain
    with get_track_info (track_type "track") first.

    Parameters:
    - track_index: Index of the track (in song.tracks, or return_tracks if track_type="return")
    - device_index: Index of the device in the track's chain
    - expected_name: The track's exact current name (required safety check)
    - expected_device_name: The device's exact current name (required safety check)
    - confirm: false = preview only (default), true = delete
    - track_type: "track" (default) or "return". "master" is refused.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_device")
        if missing:
            return missing
        if not expected_name or not expected_device_name:
            return ("Error deleting device: expected_name (the track) and "
                    "expected_device_name (the device) are both required. Read "
                    "them from the current chain and pass them exactly.")
        ableton = get_ableton_connection()
        params = {
            "track_index": track_index,
            "device_index": device_index,
            "expected_name": expected_name,
            "expected_device_name": expected_device_name,
            "track_type": track_type,
        }
        if not confirm:
            preview = ableton.send_command("delete_device", dict(params, confirm=False))
            return (
                "NOT DELETED (preview only). This would delete: "
                + json.dumps(preview, indent=2)
                + "\nTo delete, call delete_device again with the same "
                "arguments and confirm=true."
            )
        result = ableton.send_command("delete_device", dict(params, confirm=True))
        return "Deleted device. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting device: {str(e)}")
        return f"Error deleting device: {str(e)}"


UNDO_REDO_WARNING = (
    "WARNING: Live merges changes made through the API into ONE undo step, so a "
    "single undo/redo can revert SEVERAL MCP changes at once (everything since "
    "the user's last manual action) and also the user's own recent manual edits."
)


def _undo_redo(action: str, confirm: bool = False) -> str:
    """Shared body of undo / redo. Without confirm it only previews."""
    try:
        from .script_handshake import require_capability

        # undo_confirm_guard: an older Remote Script ignores dry_run and would
        # undo at once, defeating the guard, so refuse to talk to it.
        missing = require_capability(action) or require_capability("undo_confirm_guard")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(action, {"dry_run": not confirm})
        if not result.get("performed"):
            if result.get("dry_run") and result.get("message", "").startswith("PREVIEW"):
                return (
                    f"{result['message']} (can undo: {result.get('can_undo')}, "
                    f"can redo: {result.get('can_redo')}.)")
            return result.get("message") or f"Nothing to {action}"
        return (f"{action.capitalize()} done. {UNDO_REDO_WARNING} "
                f"Can undo: {result.get('can_undo')}, "
                f"can redo: {result.get('can_redo')}.")
    except Exception as e:
        logger.error(f"Error performing {action}: {str(e)}")
        return f"Error performing {action}: {str(e)}"


@mcp.tool()
@telemetry_tool("undo")
@trajectory_tool("undo")
def undo(ctx: Context, confirm: bool = False, user_prompt: str = "") -> str:
    """
    Undo in Ableton Live. DANGEROUS: one undo can revert SEVERAL changes.

    WARNING: Live merges changes made through the API into ONE undo step. One
    undo may therefore revert many MCP changes at once (renames, tempo, mutes,
    track creation/deletion, everything since the user's last manual action) and
    also the user's own recent manual edits. It is not "undo the last tool call".
    NOTE: since Remote Script 1.10.15 every MCP tool call is wrapped in its own undo
    step, so with a current script one undo normally reverts only the LAST tool call
    (tools that work in several steps, such as create_locator, set_track_routing and
    set_device_routing, can take more than one undo). It still reverts the user's own
    manual edits when no tool call came after them: read the session first.

    Step 1: call with confirm=false (the default). Nothing is changed; you get a
    preview with this warning plus can_undo / can_redo. Tell the user what an
    undo could revert and get their agreement.
    Step 2: call again with confirm=true to actually undo one step of Live's
    history. Call get_session_info or get_track_info afterwards, because you may
    be in a different state than you expect. Prefer reversing a specific change
    with the matching set_* tool when you can.

    Does nothing, and says so, when there is nothing to undo.

    Parameters:
    - confirm: false = preview only (default), true = really undo
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _undo_redo("undo", confirm)


@mcp.tool()
@telemetry_tool("redo")
@trajectory_tool("redo")
def redo(ctx: Context, confirm: bool = False, user_prompt: str = "") -> str:
    """
    Redo in Ableton Live. DANGEROUS: one redo can re-apply SEVERAL changes.

    WARNING: Live merges changes made through the API into ONE undo step, so one
    redo can re-apply many MCP changes at once (and the user's own manual edits
    that were undone with them).

    Step 1: call with confirm=false (the default). Nothing is changed; you get a
    preview with this warning plus can_undo / can_redo.
    Step 2: call again with confirm=true to actually redo one step.

    Does nothing, and says so, when there is nothing to redo (for example after
    any new edit, which clears Live's redo history).

    Parameters:
    - confirm: false = preview only (default), true = really redo
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    return _undo_redo("redo", confirm)


@mcp.tool()
@telemetry_tool("start_playback")
@trajectory_tool("start_playback")
def start_playback(ctx: Context, user_prompt: str = "") -> str:
    """Start playing the Ableton session.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_playback")
        return "Started playback"
    except Exception as e:
        logger.error(f"Error starting playback: {str(e)}")
        return f"Error starting playback: {str(e)}"

@mcp.tool()
@telemetry_tool("stop_playback")
@trajectory_tool("stop_playback")
def stop_playback(ctx: Context, user_prompt: str = "") -> str:
    """Stop playing the Ableton session.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_playback")
        return "Stopped playback"
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        return f"Error stopping playback: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("get_browser_tree")
@trajectory_tool("get_browser_tree")
def get_browser_tree(ctx: Context, category_type: str = "all", user_prompt: str = "") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.

    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_tree", {
            "category_type": category_type
        })
        
        # Check if we got any categories
        if "available_categories" in result and len(result.get("categories", [])) == 0:
            available_cats = result.get("available_categories", [])
            return (f"No categories found for '{category_type}'. "
                   f"Available browser categories: {', '.join(available_cats)}")
        
        # Format the tree in a more readable way
        total_folders = result.get("total_folders", 0)
        formatted_output = f"Browser tree for '{category_type}' (showing {total_folders} folders):\n\n"
        
        def format_tree(item, indent=0):
            output = ""
            if item:
                prefix = "  " * indent
                name = item.get("name", "Unknown")
                path = item.get("path", "")
                has_more = item.get("has_more", False)
                
                # Add this item
                output += f"{prefix}• {name}"
                if path:
                    output += f" (path: {path})"
                if has_more:
                    output += " [...]"
                output += "\n"
                
                # Add children
                for child in item.get("children", []):
                    output += format_tree(child, indent + 1)
            return output
        
        # Format each category
        for category in result.get("categories", []):
            formatted_output += format_tree(category)
            formatted_output += "\n"
        
        return formatted_output
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        else:
            logger.error(f"Error getting browser tree: {error_msg}")
            return f"Error getting browser tree: {error_msg}"

@mcp.tool()
@rich_telemetry_tool("get_browser_items_at_path")
@trajectory_tool("get_browser_items_at_path")
def get_browser_items_at_path(ctx: Context, path: str, user_prompt: str = "") -> str:
    """
    Get browser items at a specific path in Ableton's browser.

    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_items_at_path", {
            "path": path
        })
        
        # Check if there was an error with available categories
        if "error" in result and "available_categories" in result:
            error = result.get("error", "")
            available_cats = result.get("available_categories", [])
            return (f"Error: {error}\n"
                   f"Available browser categories: {', '.join(available_cats)}")
        
        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        elif "Unknown or unavailable category" in error_msg:
            logger.error(f"Invalid browser category: {error_msg}")
            return f"Error: {error_msg}. Please check the available categories using get_browser_tree."
        elif "Path part" in error_msg and "not found" in error_msg:
            logger.error(f"Path not found: {error_msg}")
            return f"Error: {error_msg}. Please check the path and try again."
        else:
            logger.error(f"Error getting browser items at path: {error_msg}")
            return f"Error getting browser items at path: {error_msg}"

@mcp.tool()
@rich_telemetry_tool("load_drum_kit")
@trajectory_tool("load_drum_kit")
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_path: str, user_prompt: str = "") -> str:
    """
    Load a drum rack and then load a specific drum kit into it.

    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        
        # Step 1: Load the drum rack
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": rack_uri
        })
        
        if not result.get("loaded", False):
            return f"Failed to load drum rack with URI '{rack_uri}'"
        
        # Step 2: Get the drum kit items at the specified path
        kit_result = ableton.send_command("get_browser_items_at_path", {
            "path": kit_path
        })
        
        if "error" in kit_result:
            return f"Loaded drum rack but failed to find drum kit: {kit_result.get('error')}"
        
        # Step 3: Find a loadable drum kit
        kit_items = kit_result.get("items", [])
        loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]
        
        if not loadable_kits:
            return f"Loaded drum rack but no loadable drum kits found at '{kit_path}'"
        
        # Step 4: Load the first loadable kit
        kit_uri = loadable_kits[0].get("uri")
        load_result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": kit_uri
        })
        
        return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"

# ── Arrangement view tools ────────────────────────────────────────────────────

@mcp.tool()
@telemetry_tool("switch_to_arrangement_view")
@trajectory_tool("switch_to_arrangement_view")
def switch_to_arrangement_view(ctx: Context, user_prompt: str = "") -> str:
    """Switch Ableton's main window to the Arrangement view.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        ableton.send_command("switch_to_arrangement_view")
        return "Switched to Arrangement view"
    except Exception as e:
        logger.error(f"Error switching to arrangement view: {str(e)}")
        return f"Error switching to arrangement view: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_arrangement_time")
@trajectory_tool("set_arrangement_time")
def set_arrangement_time(ctx: Context, time: float, user_prompt: str = "") -> str:
    """
    Move the arrangement playhead to a specific position.

    Parameters:
    - time: Position in beats from the start of the arrangement (e.g. 8.0 = bar 3 in 4/4)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_current_song_time", {"time": time})
        message = f"Playhead moved to beat {result.get('current_song_time', time)}"
        if result.get("warning"):
            message += f". WARNING: {result['warning']}"
        return message
    except Exception as e:
        logger.error(f"Error setting arrangement time: {str(e)}")
        return f"Error setting arrangement time: {str(e)}"


@mcp.tool()
@telemetry_tool("get_arrangement_clips")
@trajectory_tool("get_arrangement_clips")
def get_arrangement_clips(ctx: Context, track_index: int, user_prompt: str = "") -> str:
    """
    List all clips placed in the Arrangement timeline for a track.

    Returns each clip's name, start_time, end_time, length, and type.

    Parameters:
    - track_index: The index of the track to inspect
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("duplicate_to_arrangement")
@trajectory_tool("duplicate_to_arrangement")
def duplicate_to_arrangement(
    ctx: Context,
    track_index: int,
    clip_index: int,
    destination_time: float,
    user_prompt: str = ""
) -> str:
    """
    Copy a Session-view clip into the Arrangement timeline.

    Uses Live's track.duplicate_clip_to_arrangement() API (Live 11 / 12).
    The clip is placed at destination_time beats from the start of the
    arrangement on the same track it lives in.

    Typical workflow:
      1. create_clip / add_notes_to_clip to build a Session clip
      2. Call duplicate_to_arrangement once per bar/section you need
      3. Call switch_to_arrangement_view to confirm the result in Live

    Parameters:
    - track_index:       Index of the track that owns the Session clip
    - clip_index:        Index of the clip slot in that track (Session view)
    - destination_time:  Beat position in the arrangement to place the clip
                         (e.g. 0.0 = start, 8.0 = bar 3 in 4/4)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "duplicate_session_clip_to_arrangement",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "destination_time": destination_time
            }
        )
        clip_name = result.get("clip_name", "clip")
        track_name = result.get("track_name", f"track {track_index}")
        return (
            f"Duplicated '{clip_name}' from Session slot {clip_index} "
            f"on '{track_name}' to arrangement at beat {destination_time}"
        )
    except Exception as e:
        logger.error(f"Error duplicating clip to arrangement: {str(e)}")
        return f"Error duplicating clip to arrangement: {str(e)}"


def _arrangement_edit(command: str, params: dict, confirm: bool, verb: str) -> str:
    """Shared preview / apply step of the Arrangement clip edits."""
    from .script_handshake import require_capability

    missing = require_capability(command)
    if missing:
        return missing
    if params.get("expected_name") is None:
        return (f"Error: expected_name is required. Read the track's exact current "
                f"name (get_track_info / get_arrangement_clips) and pass it unchanged.")
    ableton = get_ableton_connection()
    if not confirm:
        preview = ableton.send_command(command, dict(params, confirm=False))
        return (
            "NOT CHANGED (preview only). This would happen: "
            + json.dumps(preview, indent=2)
            + f"\nTo {verb}, call {command} again with the same arguments and confirm=true."
        )
    result = ableton.send_command(command, dict(params, confirm=True))
    return f"Done ({verb}). " + json.dumps(result, indent=2)


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("clear_arrangement_range")
@trajectory_tool("clear_arrangement_range")
def clear_arrangement_range(
    ctx: Context,
    track_index: int,
    expected_name: str,
    start_time: float,
    end_time: float,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Clear a stretch of one Arrangement track, in two steps. DESTRUCTIVE.

    Clips that cross the start or end of [start_time, end_time) are shortened
    (their content stays where it was), a clip that spans the whole range is
    split in two with a gap, clips inside the range are removed. Nothing is moved
    to close the gap. Units are beats from the start of the Arrangement.

    Step 1: confirm=false (default) previews which clips are affected and how.
    Step 2: the same call with confirm=true applies it. expected_name must equal
    the track's current name. Audio tracks need one empty Session slot (a silent
    clip is placed there for a moment).

    Parameters:
    - track_index: Index of the (non-group) track
    - expected_name: The track's exact current name (required safety check)
    - start_time, end_time: Range in beats, start < end
    - confirm: false = preview only (default), true = apply
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _arrangement_edit("clear_arrangement_range", {
            "track_index": track_index, "expected_name": expected_name,
            "start_time": start_time, "end_time": end_time}, confirm, "clear the range")
    except Exception as e:
        logger.error(f"Error clearing arrangement range: {str(e)}")
        return f"Error clearing arrangement range: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("trim_arrangement_clip")
@trajectory_tool("trim_arrangement_clip")
def trim_arrangement_clip(
    ctx: Context,
    track_index: int,
    expected_name: str,
    clip_start_time: float,
    new_start_time: Optional[float] = None,
    new_end_time: Optional[float] = None,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Shorten one Arrangement clip from its start and/or its end, in two steps.

    The clip is found by its start beat (see get_arrangement_clips). The content
    is kept: a later start keeps the content offset, so the same material plays
    at the same time. A clip can only be shortened, never lengthened. Only this
    clip changes. Step 1 (confirm=false, default) previews; step 2 applies.

    Parameters:
    - track_index: Index of the (non-group) track
    - expected_name: The track's exact current name (required safety check)
    - clip_start_time: Start beat of the clip to trim
    - new_start_time: New start beat (>= the current start), optional
    - new_end_time: New end beat (<= the current end), optional
    - confirm: false = preview only (default), true = apply
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "expected_name": expected_name,
                  "clip_start_time": clip_start_time}
        if new_start_time is not None:
            params["new_start_time"] = new_start_time
        if new_end_time is not None:
            params["new_end_time"] = new_end_time
        return _arrangement_edit("trim_arrangement_clip", params, confirm, "trim the clip")
    except Exception as e:
        logger.error(f"Error trimming arrangement clip: {str(e)}")
        return f"Error trimming arrangement clip: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("split_arrangement_clip")
@trajectory_tool("split_arrangement_clip")
def split_arrangement_clip(
    ctx: Context,
    track_index: int,
    expected_name: str,
    clip_start_time: float,
    split_time: float,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Split one Arrangement clip in two at a beat, with no gap, in two steps.

    Both halves keep the content (the right half starts at the matching offset).
    It works through a temporary copy placed after the last clip on the track,
    removed again, so other clips are not touched. Step 1 (confirm=false,
    default) previews; step 2 applies.

    Parameters:
    - track_index: Index of the (non-group) track
    - expected_name: The track's exact current name (required safety check)
    - clip_start_time: Start beat of the clip to split
    - split_time: Beat to cut at, inside the clip
    - confirm: false = preview only (default), true = apply
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _arrangement_edit("split_arrangement_clip", {
            "track_index": track_index, "expected_name": expected_name,
            "clip_start_time": clip_start_time, "split_time": split_time},
            confirm, "split the clip")
    except Exception as e:
        logger.error(f"Error splitting arrangement clip: {str(e)}")
        return f"Error splitting arrangement clip: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("move_arrangement_clip")
@trajectory_tool("move_arrangement_clip")
def move_arrangement_clip(
    ctx: Context,
    track_index: int,
    expected_name: str,
    clip_start_time: float,
    new_start_time: Optional[float] = None,
    copy: bool = False,
    to_track_index: Optional[int] = None,
    to_expected_name: Optional[str] = None,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Move (or copy) one Arrangement clip to another beat, on the same track or on
    another track of the same kind, in two steps. DESTRUCTIVE for whatever is at the
    destination.

    The clip keeps its length, content offset and notes. Clips already at the
    destination are overwritten, like a paste (the preview lists them). With
    to_track_index and to_expected_name the clip goes to another track: MIDI to a
    MIDI track, audio to an audio track (Live refuses a MIDI clip on an audio track);
    new_start_time then defaults to the same beat. Step 1 (confirm=false, default)
    previews; step 2 applies.

    Parameters:
    - track_index: Index of the (non-group) track that holds the clip
    - expected_name: The track's exact current name (required safety check)
    - clip_start_time: Start beat of the clip to move
    - new_start_time: Beat where it should start (optional when to_track_index is given)
    - copy: true = leave the original in place (a copy on the same track cannot overlap it)
    - to_track_index: Index of the destination track, to move or copy to another track
    - to_expected_name: The destination track's exact current name (required with to_track_index)
    - confirm: false = preview only (default), true = apply
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if to_track_index is not None and to_expected_name is None:
            return "Error: to_expected_name is required with to_track_index (the destination track's exact name)."
        if new_start_time is None and to_track_index is None:
            return "Error: give new_start_time, or to_track_index to move the clip to another track."
        params = {"track_index": track_index, "expected_name": expected_name,
                  "clip_start_time": clip_start_time, "copy": copy}
        for key, value in (("new_start_time", new_start_time), ("to_track_index", to_track_index),
                           ("to_expected_name", to_expected_name)):
            if value is not None:
                params[key] = value
        return _arrangement_edit("move_arrangement_clip", params, confirm,
                                 "copy the clip" if copy else "move the clip")
    except Exception as e:
        logger.error(f"Error moving arrangement clip: {str(e)}")
        return f"Error moving arrangement clip: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("create_arrangement_clip")
@trajectory_tool("create_arrangement_clip")
def create_arrangement_clip(
    ctx: Context,
    track_index: int,
    expected_name: str,
    start_time: float,
    length: Optional[float] = None,
    notes: Optional[List[Dict[str, Union[int, float, bool]]]] = None,
    path: Optional[str] = None,
    name: str = "",
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Create a clip directly in the Arrangement at a beat, in two steps.

    MIDI track: give length (beats) and, optionally, notes (pitch, start_time,
    duration, velocity, mute; start_time is relative to the clip and every note
    must start inside it, otherwise this is an error rather than a silent drop).
    Audio track: give path to an audio file; the clip is as long as the file.
    Whatever lies where the clip goes is overwritten (the MIDI preview lists it).
    Step 1 (confirm=false, default) previews; step 2 creates.

    Parameters:
    - track_index: Index of the (non-group) track
    - expected_name: The track's exact current name (required safety check)
    - start_time: Beat where the clip starts
    - length: Length in beats (MIDI tracks)
    - notes: Notes to put in the clip (MIDI tracks)
    - path: Absolute path of an audio file (audio tracks)
    - name: Optional clip name
    - confirm: false = preview only (default), true = create
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "expected_name": expected_name,
                  "start_time": start_time, "name": name}
        for key, value in (("length", length), ("notes", notes), ("path", path)):
            if value is not None:
                params[key] = value
        return _arrangement_edit("create_arrangement_clip", params, confirm,
                                 "create the clip")
    except Exception as e:
        logger.error(f"Error creating arrangement clip: {str(e)}")
        return f"Error creating arrangement clip: {str(e)}"


@mcp.tool()
@telemetry_tool("back_to_arrangement")
@trajectory_tool("back_to_arrangement")
def back_to_arrangement(ctx: Context, user_prompt: str = "") -> str:
    """
    Hand playback back to the Arrangement (Live's "Back to Arrangement" button).

    Launching a Session clip or scene (fire_clip, fire_scene) takes those tracks
    off the Arrangement until this is called. The reply says whether any track
    was off it and what Live read back. Adapted from upstream PR #119 (mateogon).

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("back_to_arrangement")
        if missing:
            return missing
        result = get_ableton_connection().send_command("back_to_arrangement", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error going back to the arrangement: {str(e)}")
        return f"Error going back to the arrangement: {str(e)}"


@mcp.tool()
@telemetry_tool("get_track_routing")
def get_track_routing(
    ctx: Context,
    track_index: int = 0,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Read a track's input and output routing: the current type and channel, and the
    types and channels Live offers (the channels depend on the current type).
    Names are exactly what Live shows, and what set_track_routing takes.

    Parameters:
    - track_index: Index within the chosen track_type (ignored for "master")
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_track_routing")
        if missing:
            return missing
        result = get_ableton_connection().send_command(
            "get_track_routing", {"track_index": track_index, "track_type": track_type})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track routing: {str(e)}")
        return f"Error getting track routing: {str(e)}"


@mcp.tool()
@telemetry_tool("set_track_routing")
@trajectory_tool("set_track_routing")
def set_track_routing(
    ctx: Context,
    track_index: int,
    expected_name: str,
    direction: str,
    routing_type: Optional[str] = None,
    routing_channel: Optional[str] = None,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Set a track's input or output routing (type and/or channel).

    Read the names with get_track_routing first. A type change is applied, Live
    is given a moment to list the channels for it, then the channel is set (about
    a second in all). A wrong OUTPUT can silence a track, so expected_name (the
    track's exact current name) is required; the reply has the previous and the
    new routing, so the change can be undone with another call. Based on upstream
    PR #99 (Zachary May), extended with channels, track_type and the name check.

    Parameters:
    - track_index: Index within the chosen track_type
    - expected_name: The track's exact current name (required safety check)
    - direction: "input" or "output"
    - routing_type: Routing type name, e.g. "Ext. In", "Master", "Sends Only"
    - routing_channel: Routing channel name, e.g. "1/2", "Pre FX"
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_track_routing")
        if missing:
            return missing
        if expected_name is None:
            return ("Error setting track routing: expected_name is required. Read the "
                    "track's exact current name and pass it unchanged.")
        params = {"track_index": track_index, "track_type": track_type,
                  "expected_name": expected_name, "direction": direction}
        if routing_type is not None:
            params["routing_type"] = routing_type
        if routing_channel is not None:
            params["routing_channel"] = routing_channel
        result = get_ableton_connection().send_command("set_track_routing", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting track routing: {str(e)}")
        return f"Error setting track routing: {str(e)}"


def _json_call(command: str, params: dict, error_label: str) -> str:
    from .script_handshake import require_capability

    missing = require_capability(command)
    if missing:
        return missing
    return json.dumps(get_ableton_connection().send_command(command, params), indent=2)


@mcp.tool()
@telemetry_tool("get_device_routing")
def get_device_routing(
    ctx: Context,
    track_index: int,
    device_index: int,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Read a device's sidechain source ("Audio From") on Compressor, Gate, Glue
    Compressor and the other devices that have one: the current type and channel,
    the types and channels Live offers, and whether the device's sidechain is on
    ("S/C On"). Find the device_index with get_track_info.

    Parameters:
    - track_index: Index within the chosen track_type
    - device_index: Index of the device in the track's chain
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("get_device_routing", {"track_index": track_index,
                                                 "device_index": device_index,
                                                 "track_type": track_type}, "getting device routing")
    except Exception as e:
        logger.error(f"Error getting device routing: {str(e)}")
        return f"Error getting device routing: {str(e)}"


@mcp.tool()
@telemetry_tool("set_device_routing")
@trajectory_tool("set_device_routing")
def set_device_routing(
    ctx: Context,
    track_index: int,
    device_index: int,
    expected_name: str,
    expected_device_name: str,
    routing_type: Optional[str] = None,
    routing_channel: Optional[str] = None,
    sidechain_on: Optional[bool] = None,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Set a device's sidechain source: which track feeds it ("Audio From" type, for
    example the kick track), at which tap (channel: "Pre FX", "Post FX", "Post
    Mixer"), and optionally switch its sidechain on or off ("S/C On"). This is the
    ducking setup: a Compressor on the bass with the kick as its source.

    A new type is applied first, Live is given a moment to list its channels, then
    the channel is set (about a second). expected_name (the track) and
    expected_device_name are required safety checks. The reply has the previous
    and the new routing. Two tracks with the same name cannot be picked by name.

    Parameters:
    - track_index: Index of the track that holds the device
    - device_index: Index of the device in its chain
    - expected_name: The track's exact current name
    - expected_device_name: The device's exact current name
    - routing_type: Name of the source (a track name, "Resampling", "Ext. In", ...)
    - routing_channel: The tap ("Pre FX", "Post FX", "Post Mixer", ...)
    - sidechain_on: true/false to switch the device's "S/C On"
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None or expected_device_name is None:
            return ("Error setting device routing: expected_name (the track) and "
                    "expected_device_name are required.")
        params = {"track_index": track_index, "device_index": device_index,
                  "track_type": track_type, "expected_name": expected_name,
                  "expected_device_name": expected_device_name}
        for key, value in (("routing_type", routing_type), ("routing_channel", routing_channel),
                           ("sidechain_on", sidechain_on)):
            if value is not None:
                params[key] = value
        return _json_call("set_device_routing", params, "setting device routing")
    except Exception as e:
        logger.error(f"Error setting device routing: {str(e)}")
        return f"Error setting device routing: {str(e)}"


@mcp.tool()
@telemetry_tool("get_clip_envelope")
def get_clip_envelope(
    ctx: Context,
    track_index: int,
    parameter: str,
    clip_index: int = 0,
    device_index: Optional[int] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    step: float = 0.25,
    user_prompt: str = "",
) -> str:
    """
    Read the automation a clip holds for one parameter, as samples every `step`
    beats (times are from the clip start; values in the parameter's own units, with
    Live's display string). has_envelope is false when the clip has none for it.

    The parameter is a mixer one ("volume", "pan", "send A") or, with
    device_index, a device parameter by name (as get_device_parameters lists it) or
    index. Only Session clips have automation the API can reach (an Arrangement
    clip made from a Session clip keeps the automation it had). At most 512 samples.

    Parameters:
    - track_index: Track that owns the clip
    - parameter: "volume", "pan", "send A"/"send B", or a device parameter name
    - clip_index: Session clip slot
    - device_index: Device holding the parameter; leave out for mixer parameters
    - start, end: Window in beats from the clip start (default the whole clip)
    - step: Beats between samples (default 0.25)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "clip_index": clip_index, "parameter": parameter,
                  "step": step}
        for key, value in (("device_index", device_index), ("start", start), ("end", end)):
            if value is not None:
                params[key] = value
        return _json_call("get_clip_envelope", params, "reading clip envelope")
    except Exception as e:
        logger.error(f"Error reading clip envelope: {str(e)}")
        return f"Error reading clip envelope: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("set_clip_envelope")
@trajectory_tool("set_clip_envelope")
def set_clip_envelope(
    ctx: Context,
    track_index: int,
    expected_name: str,
    parameter: str,
    points: Optional[List[Dict[str, float]]] = None,
    shape: Optional[Dict[str, Any]] = None,
    clip_index: int = 0,
    device_index: Optional[int] = None,
    mode: str = "linear",
    end: Optional[float] = None,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Write a clip's automation of one parameter, in two steps. It REPLACES that
    parameter's automation from the first point to the end of the written span.

    Give either points or shape.

    points: [{"time": beats from the clip start, "value": the parameter's own
    units}] in increasing time (a volume of 0.85 is 0 dB; read get_clip_envelope or
    get_device_parameters for ranges). mode "linear" (default; "ramp" is the same):
    real breakpoints, Live draws straight lines between them, so a fade needs only
    two points; after the last point the value holds until `end` (default the clip's
    end). mode "steps": each value holds until the next point.

    shape: a generated wave, any of sine, triangle, saw_up, saw_down, square,
    random_steps, random_smooth, curve. Fields: type (required); start, end (beats,
    default the whole clip); period (beats) or cycles; min, max (the parameter's
    own units, default its whole range); phase (0-1 of a cycle: a sine starts at the
    middle going up, phase 0.75 starts at the bottom); points_per_cycle (4-128,
    default 16); duty (square, 0.01-0.99); seed (random_*); exponent (curve: min to
    max over start..end, 1 = straight, 2 = slow start); invert (true flips it).
    Example, a pan sweep of 4 beats a cycle over the whole clip:
    {"type": "sine", "period": 4, "min": -0.6, "max": 0.6}. Live only draws straight
    lines (curve coefficients are ignored), so a sine is made of points_per_cycle
    breakpoints per cycle: 16 is within 2% of the amplitude, 32 within 0.5%.

    Step 1: confirm=false (default) previews (parameter, point and event counts,
    whether it replaces automation). Step 2: the same call with confirm=true; the reply
    reads the values back. Clip automation can only target parameters of the clip's
    own track, and only Session clips can be written (copy the clip into the
    Arrangement afterwards with duplicate_to_arrangement: the automation comes
    along). Idea from upstream PR #23 (zzstoatzz).

    Parameters:
    - track_index: Track that owns the clip
    - expected_name: The track's exact current name (required safety check)
    - parameter: "volume", "pan", "send A"/"send B", or a device parameter name
    - points: The breakpoints, as above (or give shape)
    - shape: A generated wave, as above (or give points)
    - clip_index: Session clip slot
    - device_index: Device holding the parameter; leave out for mixer parameters
    - mode: "linear" (default) or "steps"; ignored for shapes (a square holds, the others are linear)
    - end: Where the last point's stretch ends (default the clip end)
    - confirm: false = preview only (default), true = write
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None:
            return "Error: expected_name is required (the track's exact current name)."
        if (points is None) == (shape is None):
            return "Error: give points or shape (exactly one)."
        params = {"track_index": track_index, "clip_index": clip_index, "expected_name": expected_name,
                  "parameter": parameter, "mode": mode, "confirm": confirm}
        for key, value in (("points", points), ("shape", shape), ("device_index", device_index),
                           ("end", end)):
            if value is not None:
                params[key] = value
        out = _json_call("set_clip_envelope", params, "writing clip envelope")
        return (out if confirm else
                "NOT WRITTEN (preview only). This would happen: " + out +
                "\nTo write it, call set_clip_envelope again with the same arguments and confirm=true.")
    except Exception as e:
        logger.error(f"Error writing clip envelope: {str(e)}")
        return f"Error writing clip envelope: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("clear_clip_envelope")
@trajectory_tool("clear_clip_envelope")
def clear_clip_envelope(
    ctx: Context,
    track_index: int,
    expected_name: str,
    parameter: str,
    clip_index: int = 0,
    device_index: Optional[int] = None,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Remove a clip's automation of one parameter, in two steps (Live's undo can bring
    it back). Step 1: confirm=false (default) says whether the clip has any for that
    parameter. Step 2: the same call with confirm=true removes it.

    Parameters:
    - track_index: Track that owns the clip
    - expected_name: The track's exact current name (required safety check)
    - parameter: "volume", "pan", "send A"/"send B", or a device parameter name
    - clip_index: Session clip slot
    - device_index: Device holding the parameter; leave out for mixer parameters
    - confirm: false = preview only (default), true = remove
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None:
            return "Error: expected_name is required (the track's exact current name)."
        params = {"track_index": track_index, "clip_index": clip_index, "expected_name": expected_name,
                  "parameter": parameter, "confirm": confirm}
        for key, value in (("device_index", device_index),):
            if value is not None:
                params[key] = value
        out = _json_call("clear_clip_envelope", params, "clearing clip envelope")
        return (out if confirm else
                "NOT REMOVED (preview only). This would happen: " + out +
                "\nTo remove it, call clear_clip_envelope again with the same arguments and confirm=true.")
    except Exception as e:
        logger.error(f"Error clearing clip envelope: {str(e)}")
        return f"Error clearing clip envelope: {str(e)}"


@mcp.tool()
@telemetry_tool("get_tracks_overview")
def get_tracks_overview(ctx: Context, user_prompt: str = "") -> str:
    """
    Every track, return and the master in ONE compact read: kind (audio, midi,
    group), device names, volume and pan as Live shows them, mute/solo/arm,
    Session and Arrangement clip counts, group, colour, plus tempo, time signature,
    scene and cue-point counts. Use this before get_track_info on each track.
    Adapted from upstream PR #110 (M4x28).

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("get_tracks_overview", {}, "getting tracks overview")
    except Exception as e:
        logger.error(f"Error getting tracks overview: {str(e)}")
        return f"Error getting tracks overview: {str(e)}"


@mcp.tool()
@telemetry_tool("check_arrangement_sync")
def check_arrangement_sync(
    ctx: Context,
    grid_beats: float = 4.0,
    tolerance: float = 0.001,
    user_prompt: str = "",
) -> str:
    """
    Check every track's Arrangement clips against a grid: starts and ends that are
    off the grid, overlaps, and gaps between neighbouring clips. Read-only. The
    counts are complete, each list is cut at 20 entries. A gap is silence between
    two clips of one track, often intended. Handy after trimming, splitting or
    moving clips. Adapted from upstream PR #110 (M4x28).

    Parameters:
    - grid_beats: Grid to check against in beats (4 = bars in 4/4, the default; 1 = beats)
    - tolerance: How far off the grid still counts as on it, in beats
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("check_arrangement_sync",
                          {"grid_beats": grid_beats, "tolerance": tolerance}, "checking arrangement")
    except Exception as e:
        logger.error(f"Error checking arrangement: {str(e)}")
        return f"Error checking arrangement: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("replace_clip_notes")
@trajectory_tool("replace_clip_notes")
def replace_clip_notes(
    ctx: Context,
    track_index: int,
    clip_index: int,
    expected_clip_name: str,
    notes: List[Dict[str, Union[int, float, bool]]],
    confirm: bool = False,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Replace ALL the notes of a Session MIDI clip with new ones, in two steps.

    Everything is validated before anything is removed, and a new note that would
    never play (outside the clip) is an error, since the old notes would be gone.
    If the write fails after the removal the old notes are put back. Notes take the
    same fields as add_notes_to_clip (pitch, start_time, duration, velocity, mute,
    and optionally probability, velocity_deviation, release_velocity). To change a
    few notes in place use apply_note_modifications instead. Adapted from upstream
    PR #119 (mateogon).

    Step 1: confirm=false (default) says how many notes are there and how many would
    replace them. Step 2: the same call with confirm=true.

    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot
    - expected_clip_name: The clip's exact current name ("" for an unnamed clip)
    - notes: The new notes
    - confirm: false = preview only (default), true = replace
    - clip_start_time: Optional. The start beat of an ARRANGEMENT MIDI clip to use instead of a
      Session slot (clip_index is then ignored). Read starts with get_arrangement_clips.
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_clip_name is None:
            return ("Error: expected_clip_name is required (the clip's exact current name; "
                    "\"\" for an unnamed clip).")
        params = _clip_ref(track_index, clip_index, clip_start_time)
        params.update({"expected_clip_name": expected_clip_name, "notes": notes, "confirm": confirm})
        out = _json_call("replace_clip_notes", params, "replacing clip notes")
        return out if confirm else (
            "NOT REPLACED (preview only). This would happen: " + out +
            "\nTo replace the notes, call replace_clip_notes again with the same arguments and confirm=true.")
    except Exception as e:
        logger.error(f"Error replacing clip notes: {str(e)}")
        return f"Error replacing clip notes: {str(e)}"


@mcp.tool()
@telemetry_tool("set_color")
@trajectory_tool("set_color")
def set_color(
    ctx: Context,
    kind: str,
    color_index: int,
    track_index: Optional[int] = None,
    clip_index: Optional[int] = None,
    scene_index: Optional[int] = None,
    track_type: str = "track",
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Set the colour of a track, a Session clip or a scene, from Live's palette
    (index 0-69). Returns the previous and the new index. Adapted from upstream
    PR #99 (Zachary May), merged into one tool.

    Parameters:
    - kind: "track", "clip" or "scene"
    - color_index: Palette index 0-69
    - track_index: For kind "track" and "clip"
    - clip_index: For kind "clip"
    - scene_index: For kind "scene"
    - track_type: "track" (default) or "return" (for kind "track")
    - expected_name: Optional safety check: the target's exact current name
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"kind": kind, "color_index": color_index, "track_type": track_type}
        for key, value in (("track_index", track_index), ("clip_index", clip_index),
                           ("scene_index", scene_index), ("expected_name", expected_name)):
            if value is not None:
                params[key] = value
        return _json_call("set_color", params, "setting colour")
    except Exception as e:
        logger.error(f"Error setting colour: {str(e)}")
        return f"Error setting colour: {str(e)}"


@mcp.tool()
@telemetry_tool("set_track_monitoring")
@trajectory_tool("set_track_monitoring")
def set_track_monitoring(
    ctx: Context,
    track_index: int,
    state: str,
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Set a track's input monitoring: "in" (always hear the input), "auto" (hear it
    while armed) or "off". Useful before recording a guitar or a mic. Audio and
    MIDI tracks only. Returns the previous and the new state.

    Parameters:
    - track_index: Index of the track
    - state: "in", "auto" or "off"
    - expected_name: Optional safety check: the track's exact current name
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "state": state}
        if expected_name is not None:
            params["expected_name"] = expected_name
        return _json_call("set_track_monitoring", params, "setting track monitoring")
    except Exception as e:
        logger.error(f"Error setting track monitoring: {str(e)}")
        return f"Error setting track monitoring: {str(e)}"


@mcp.tool()
@telemetry_tool("duplicate_track")
@trajectory_tool("duplicate_track")
def duplicate_track(
    ctx: Context,
    track_index: int,
    expected_name: str,
    user_prompt: str = "",
) -> str:
    """
    Duplicate a track with its devices, clips and mixer settings; the copy goes right
    after it and the tracks after that move down by one. Live Lite allows 8 tracks
    in all: when the Set is full Live refuses and nothing changes. Undo with
    delete_track on the copy. From upstream PR #94 (Luke Gimza).

    Parameters:
    - track_index: Index of the track to copy
    - expected_name: The track's exact current name (required safety check)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None:
            return "Error: expected_name is required (the track's exact current name)."
        return _json_call("duplicate_track", {"track_index": track_index,
                                              "expected_name": expected_name}, "duplicating track")
    except Exception as e:
        logger.error(f"Error duplicating track: {str(e)}")
        return f"Error duplicating track: {str(e)}"


@mcp.tool()
@telemetry_tool("search_browser_items")
def search_browser_items(
    ctx: Context,
    query: str,
    category: str = "all",
    max_results: int = 20,
    loadable_only: bool = False,
    max_seconds: float = 6.0,
    user_prompt: str = "",
) -> str:
    """
    Find instruments, effects, presets and samples in Live's browser by name,
    instead of opening folders of 150+ items. Every word of the query must appear in
    the item's name or path ("analog pad", "compressor", "808"). Results carry the
    uri that load_instrument_or_effect takes. The search is breadth first (a device
    comes before the presets inside it) and has a time budget: when truncated is
    true, narrow the query or the category. Idea from upstream PR #97 (vanjaoljaca).

    Parameters:
    - query: Words to look for
    - category: "all" (default) or instruments, sounds, drums, audio_effects,
      midi_effects, plugins, user_library, packs
    - max_results: 1-200 (default 20)
    - loadable_only: true to leave out folders and other items that cannot be loaded
    - max_seconds: Time budget, up to 30 (default 6)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("search_browser_items", {
            "query": query, "category": category, "max_results": max_results,
            "loadable_only": loadable_only, "max_seconds": max_seconds}, "searching the browser")
    except Exception as e:
        logger.error(f"Error searching the browser: {str(e)}")
        return f"Error searching the browser: {str(e)}"


@mcp.tool()
@telemetry_tool("get_live_status")
def get_live_status(ctx: Context, user_prompt: str = "") -> str:
    """
    Live's health in one read: version and edition, CPU load (average and peak) and the
    performance impact of each track (heaviest first, to find the plugin that makes it
    crackle), the features this edition lacks (Live Lite), and whether a dialog is open
    (with its text and how many buttons it has).

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("get_live_status", {}, "getting Live status")
    except Exception as e:
        logger.error(f"Error getting Live status: {str(e)}")
        return f"Error getting Live status: {str(e)}"


@mcp.tool()
@telemetry_tool("press_dialog_button")
@trajectory_tool("press_dialog_button")
def press_dialog_button(
    ctx: Context,
    button_index: int,
    expected_message: str,
    user_prompt: str = "",
) -> str:
    """
    Press a button of the modal dialog Live is showing (for example the "Couldn't create track"
    box at Live Lite's limit, which otherwise waits for a click). Read the dialog first with
    get_live_status. Live reports how many buttons there are but not their labels, so only press
    a dialog whose buttons you know (an info box with one OK button is index 0); do not guess on a
    "Save changes?" box. expected_message must be a piece of the dialog's own text: a different
    dialog is never pressed by mistake.

    Parameters:
    - button_index: 0-based index of the button
    - expected_message: A piece of the open dialog's text (case-insensitive)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_message is None:
            return "Error: expected_message is required (a piece of the dialog's text)."
        return _json_call("press_dialog_button", {"button_index": button_index,
                                                  "expected_message": expected_message},
                          "pressing a dialog button")
    except Exception as e:
        logger.error(f"Error pressing a dialog button: {str(e)}")
        return f"Error pressing a dialog button: {str(e)}"


@mcp.tool()
@telemetry_tool("insert_device")
@trajectory_tool("insert_device")
def insert_device(
    ctx: Context,
    track_index: int,
    expected_name: str,
    device_name: str,
    index: int = -1,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Insert a native Live device by name, without opening the browser: "Compressor", "Reverb",
    "Utility", "Limiter", "Drum Rack", "Simpler", "Auto Filter"... The name is the one Live shows.
    index is the chain position (-1 = the end). Live answers "not available" for a device this edition
    lacks (Live Lite has no "EQ Eight" or "Glue Compressor") or "not found" for a wrong name. Needs Live
    12.3 or newer. Returns the device chain before and after. For a preset or a sample use
    search_browser_items and load_instrument_or_effect.

    Parameters:
    - track_index: Index within the chosen track_type
    - expected_name: The track's exact current name (required safety check)
    - device_name: Native device name
    - index: Chain position, -1 = the end
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None:
            return "Error: expected_name is required (the track's exact current name)."
        return _json_call("insert_device", {"track_index": track_index, "expected_name": expected_name,
                                            "device_name": device_name, "index": index,
                                            "track_type": track_type}, "inserting a device")
    except Exception as e:
        logger.error(f"Error in insert_device: {str(e)}")
        return f"Error in insert_device: {str(e)}"


@mcp.tool()
@telemetry_tool("move_device")
@trajectory_tool("move_device")
def move_device(
    ctx: Context,
    track_index: int,
    device_index: int,
    new_index: int,
    expected_name: str,
    expected_device_name: str,
    track_type: str = "track",
    to_track_index: Optional[int] = None,
    to_expected_name: Optional[str] = None,
    to_track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Move a device to another position of its chain (signal order matters: EQ before or after the
    compressor), or to another track. Live refuses combinations that make no sense (an instrument after an
    effect, an audio effect on a MIDI track before an instrument). Returns the chains afterwards.

    Parameters:
    - track_index: Track that holds the device
    - device_index: Index of the device in its chain
    - new_index: Position in the destination chain (0 = first)
    - expected_name: The track's exact current name (required safety check)
    - expected_device_name: The device's exact current name (required safety check)
    - track_type: "track" (default), "return" or "master"
    - to_track_index: Destination track, to move the device to another track
    - to_expected_name: The destination track's exact current name (required with to_track_index)
    - to_track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None or expected_device_name is None:
            return "Error: expected_name and expected_device_name are required."
        if to_track_index is not None and to_expected_name is None:
            return "Error: to_expected_name is required with to_track_index."
        params = {"track_index": track_index, "device_index": device_index, "new_index": new_index,
                  "expected_name": expected_name, "expected_device_name": expected_device_name,
                  "track_type": track_type}
        if to_track_index is not None:
            params.update({"to_track_index": to_track_index, "to_expected_name": to_expected_name,
                           "to_track_type": to_track_type})
        return _json_call("move_device", params, "moving a device")
    except Exception as e:
        logger.error(f"Error in move_device: {str(e)}")
        return f"Error in move_device: {str(e)}"


@mcp.tool()
@telemetry_tool("duplicate_device")
@trajectory_tool("duplicate_device")
def duplicate_device(
    ctx: Context,
    track_index: int,
    device_index: int,
    expected_name: str,
    expected_device_name: str,
    track_type: str = "track",
    user_prompt: str = "",
) -> str:
    """
    Duplicate a device with its settings; the copy goes right after it (parallel compression, a second
    reverb with another setting, a copy of an amp). Returns the chain afterwards.

    Parameters:
    - track_index: Track that holds the device
    - device_index: Index of the device in its chain
    - expected_name: The track's exact current name (required safety check)
    - expected_device_name: The device's exact current name (required safety check)
    - track_type: "track" (default), "return" or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        if expected_name is None or expected_device_name is None:
            return "Error: expected_name and expected_device_name are required."
        return _json_call("duplicate_device", {"track_index": track_index, "device_index": device_index,
                                               "expected_name": expected_name,
                                               "expected_device_name": expected_device_name,
                                               "track_type": track_type}, "duplicating a device")
    except Exception as e:
        logger.error(f"Error in duplicate_device: {str(e)}")
        return f"Error in duplicate_device: {str(e)}"


@mcp.tool()
@telemetry_tool("get_song_scale")
def get_song_scale(
    ctx: Context,
    user_prompt: str = "",
) -> str:
    """
    Read the set's key and scale: root note, scale name, whether scale mode (in-key highlighting) is on,
    and the notes of the scale. Live's default is C Major with scale mode on, which is not necessarily the
    song's key: ask or measure before relying on it.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("get_song_scale", {}, "reading the scale")
    except Exception as e:
        logger.error(f"Error in get_song_scale: {str(e)}")
        return f"Error in get_song_scale: {str(e)}"


@mcp.tool()
@telemetry_tool("set_song_scale")
@trajectory_tool("set_song_scale")
def set_song_scale(
    ctx: Context,
    root_note: Optional[str] = None,
    scale_name: Optional[str] = None,
    scale_mode: Optional[bool] = None,
    user_prompt: str = "",
) -> str:
    """
    Set the set's key and scale, so Live highlights the in-key notes in every MIDI clip and Scale-aware
    devices follow. root_note: a note name ("C", "F#", "Bb") or 0-11 as text. scale_name as Live shows it:
    Major, Minor, Dorian, Mixolydian, Lydian, Phrygian, Locrian, Whole Tone, Minor Pentatonic, Major
    Pentatonic, Harmonic Minor, Melodic Minor, ... (an unknown name is refused). It does not transpose
    anything. Returns the scale before and after.

    Parameters:
    - root_note: Key, as a name or 0-11 (0 = C)
    - scale_name: Scale name
    - scale_mode: true/false: Live's in-key note highlighting
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {}
        if root_note is not None:
            params["root_note"] = int(root_note) if str(root_note).strip().isdigit() else root_note
        for key, value in (("scale_name", scale_name), ("scale_mode", scale_mode)):
            if value is not None:
                params[key] = value
        return _json_call("set_song_scale", params, "setting the scale")
    except Exception as e:
        logger.error(f"Error in set_song_scale: {str(e)}")
        return f"Error in set_song_scale: {str(e)}"


@mcp.tool()
@telemetry_tool("set_scene_tempo")
@trajectory_tool("set_scene_tempo")
def set_scene_tempo(
    ctx: Context,
    scene_index: int,
    tempo: Optional[float] = None,
    numerator: Optional[int] = None,
    denominator: Optional[int] = None,
    clear: bool = False,
    expected_name: Optional[str] = None,
    user_prompt: str = "",
) -> str:
    """
    Give a Session scene its own tempo and/or time signature: launching the scene changes the set's tempo
    (a slow verse, a faster chorus, a 6/8 bridge). clear=true removes both from the scene. Returns what
    the scene holds afterwards. A scene with no tempo of its own leaves the set's tempo alone.

    Parameters:
    - scene_index: Index of the scene (see get_scenes)
    - tempo: BPM, 20 to 999
    - numerator, denominator: Time signature (give both; denominator 1, 2, 4, 8 or 16)
    - clear: true = remove the scene's own tempo and time signature
    - expected_name: Optional safety check: the scene's exact current name ("" if unnamed)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"scene_index": scene_index, "clear": clear}
        for key, value in (("tempo", tempo), ("numerator", numerator), ("denominator", denominator),
                           ("expected_name", expected_name)):
            if value is not None:
                params[key] = value
        return _json_call("set_scene_tempo", params, "setting the scene tempo")
    except Exception as e:
        logger.error(f"Error in set_scene_tempo: {str(e)}")
        return f"Error in set_scene_tempo: {str(e)}"


@mcp.tool()
@telemetry_tool("get_grooves")
def get_grooves(
    ctx: Context,
    user_prompt: str = "",
) -> str:
    """
    Read the groove pool (the grooves loaded in the set, with timing, quantization, random and velocity
    amounts) and the global groove and swing amounts. A groove shifts the timing and velocity of a clip's
    notes the way a drummer would, and is the quickest "humanize". A clip takes one with set_clip_groove.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("get_grooves", {}, "reading the grooves")
    except Exception as e:
        logger.error(f"Error in get_grooves: {str(e)}")
        return f"Error in get_grooves: {str(e)}"


@mcp.tool()
@telemetry_tool("set_groove")
@trajectory_tool("set_groove")
def set_groove(
    ctx: Context,
    groove_index: Optional[int] = None,
    timing_amount: Optional[float] = None,
    quantization_amount: Optional[float] = None,
    random_amount: Optional[float] = None,
    velocity_amount: Optional[float] = None,
    groove_amount: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Change one groove's amounts (how much it shifts timing, how much it quantizes first, how much random
    and velocity it adds) and/or the GLOBAL groove amount (0 to 1.3, 1.0 = 100%, scales every groove).
    Read the ranges with get_grooves. Returns the pool afterwards.

    Parameters:
    - groove_index: Which groove of the pool (needed with the four amounts)
    - timing_amount, quantization_amount, random_amount, velocity_amount: As get_grooves shows them
    - groove_amount: The global amount
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {}
        for key, value in (("groove_index", groove_index), ("timing_amount", timing_amount),
                           ("quantization_amount", quantization_amount), ("random_amount", random_amount),
                           ("velocity_amount", velocity_amount), ("groove_amount", groove_amount)):
            if value is not None:
                params[key] = value
        return _json_call("set_groove", params, "setting the groove")
    except Exception as e:
        logger.error(f"Error in set_groove: {str(e)}")
        return f"Error in set_groove: {str(e)}"


@mcp.tool()
@telemetry_tool("set_clip_groove")
@trajectory_tool("set_clip_groove")
def set_clip_groove(
    ctx: Context,
    track_index: int,
    groove_index: int,
    clip_index: int = 0,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Give a clip a groove from the pool (see get_grooves). Works on Session clips and, with
    clip_start_time, on Arrangement clips. The groove is applied live on playback; the notes are not
    rewritten, and nothing is heard while the global groove amount is 0 (set it with set_groove).
    Live's API cannot take a groove away from a clip; to silence one use set_groove (amounts to 0).

    Parameters:
    - track_index: Track that owns the clip
    - groove_index: Index in get_grooves
    - clip_index: Session clip slot (ignored with clip_start_time)
    - clip_start_time: Start beat of an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "clip_index": clip_index, "groove_index": groove_index}
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        return _json_call("set_clip_groove", params, "setting the clip groove")
    except Exception as e:
        logger.error(f"Error in set_clip_groove: {str(e)}")
        return f"Error in set_clip_groove: {str(e)}"


@mcp.tool()
@telemetry_tool("edit_warp_marker")
@trajectory_tool("edit_warp_marker")
def edit_warp_marker(
    ctx: Context,
    track_index: int,
    action: str,
    beat_time: float,
    clip_index: int = 0,
    seconds: Optional[float] = None,
    distance: Optional[float] = None,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Edit the warp markers of a WARPED audio clip: line a recording up with the grid. Live stretches the
    audio between markers. Read the current markers with get_audio_clip_info.
    action "add": the audio at `seconds` into the FILE will play at `beat_time` (beats from the clip start).
    action "move": the marker at `beat_time` moves by `distance` beats. action "remove": the marker at
    `beat_time` goes. Typical use: find where a note really falls (scripts/ears onsets), add a marker at its
    time in the file, and move it to the beat. Undoable. Returns the markers before and after.

    Parameters:
    - track_index: Track that owns the clip
    - action: "add", "move" or "remove"
    - beat_time: Beat of the marker (clip beats)
    - clip_index: Session clip slot (ignored with clip_start_time)
    - seconds: For "add": position in the audio file, in seconds
    - distance: For "move": beats to move by (negative = earlier)
    - clip_start_time: Start beat of an Arrangement clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "clip_index": clip_index, "action": action, "beat_time": beat_time}
        for key, value in (("seconds", seconds), ("distance", distance), ("clip_start_time", clip_start_time)):
            if value is not None:
                params[key] = value
        return _json_call("edit_warp_marker", params, "editing a warp marker")
    except Exception as e:
        logger.error(f"Error in edit_warp_marker: {str(e)}")
        return f"Error in edit_warp_marker: {str(e)}"


@mcp.tool()
@telemetry_tool("duplicate_clip_loop")
@trajectory_tool("duplicate_clip_loop")
def duplicate_clip_loop(
    ctx: Context,
    track_index: int,
    clip_index: int = 0,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Make a MIDI clip's loop twice as long, copying its notes (and envelopes) into the new half: a 4-beat
    pattern becomes 8 beats you can then vary. Undoable. Returns the loop length and note count before and
    after. (An Arrangement clip's loop is its content loop; its extent on the timeline does not change.)

    Parameters:
    - track_index: Track that owns the clip
    - clip_index: Session clip slot (ignored with clip_start_time)
    - clip_start_time: Start beat of an Arrangement MIDI clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "clip_index": clip_index}
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        return _json_call("duplicate_clip_loop", params, "duplicating the clip loop")
    except Exception as e:
        logger.error(f"Error in duplicate_clip_loop: {str(e)}")
        return f"Error in duplicate_clip_loop: {str(e)}"


@mcp.tool()
@telemetry_tool("copy_note_region")
@trajectory_tool("copy_note_region")
def copy_note_region(
    ctx: Context,
    track_index: int,
    region_start: float,
    region_length: float,
    destination_time: float,
    clip_index: int = 0,
    pitch: int = -1,
    transposition: int = 0,
    clip_start_time: Optional[float] = None,
    user_prompt: str = "",
) -> str:
    """
    Copy the notes inside a stretch of a MIDI clip to another time in the same clip, all pitches or one
    pitch, transposed by semitones: repeat a motif a fifth higher (transposition=7), echo a bar, build a
    sequence. Beats are from the clip start. The destination must start inside the clip (a copy at or after
    the end would never play). Undoable. Returns the note counts.

    Parameters:
    - track_index: Track that owns the clip
    - region_start: Start of the stretch to copy, in beats
    - region_length: Its length in beats
    - destination_time: Where the copy starts, in beats
    - clip_index: Session clip slot (ignored with clip_start_time)
    - pitch: Copy only this MIDI pitch (-1 = all)
    - transposition: Semitones to transpose the copy by
    - clip_start_time: Start beat of an Arrangement MIDI clip
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        params = {"track_index": track_index, "clip_index": clip_index, "region_start": region_start,
                  "region_length": region_length, "destination_time": destination_time,
                  "pitch": pitch, "transposition": transposition}
        if clip_start_time is not None:
            params["clip_start_time"] = clip_start_time
        return _json_call("copy_note_region", params, "copying a note region")
    except Exception as e:
        logger.error(f"Error in copy_note_region: {str(e)}")
        return f"Error in copy_note_region: {str(e)}"


@mcp.tool()
@telemetry_tool("copy_clip_to_slot")
@trajectory_tool("copy_clip_to_slot")
def copy_clip_to_slot(
    ctx: Context,
    track_index: int,
    clip_index: int,
    to_track_index: int,
    to_clip_index: int,
    overwrite: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Copy a Session clip into another slot: another scene of the same track, or a track of the same kind
    (MIDI to MIDI, audio to audio). The destination slot must be empty unless overwrite is true (then the
    clip there is deleted first). Undoable.

    Parameters:
    - track_index, clip_index: The clip to copy
    - to_track_index, to_clip_index: The destination slot
    - overwrite: true = replace what is in the destination slot
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        return _json_call("copy_clip_to_slot", {"track_index": track_index, "clip_index": clip_index,
                                                 "to_track_index": to_track_index,
                                                 "to_clip_index": to_clip_index,
                                                 "overwrite": overwrite}, "copying a clip")
    except Exception as e:
        logger.error(f"Error in copy_clip_to_slot: {str(e)}")
        return f"Error in copy_clip_to_slot: {str(e)}"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
@telemetry_tool("delete_locator")
@trajectory_tool("delete_locator")
def delete_locator(
    ctx: Context,
    time: float,
    expected_name: str,
    confirm: bool = False,
    user_prompt: str = "",
) -> str:
    """
    Delete the locator (cue point) at a beat position, in two steps.

    Step 1: call with confirm=false (the default). Nothing is deleted; you get
    the locator's name and time and the locators that would remain.
    Step 2: call again with the same time and expected_name and confirm=true.

    Deletion only happens when confirm=true AND expected_name equals the name of
    the locator at that time (read both with get_cue_points). The transport must
    be stopped: the playhead is moved onto the locator, Live is given a moment,
    and the playhead is put back (about a second). Deletions go into Live's
    undo history.

    Parameters:
    - time: Beat position of the locator to delete (as get_cue_points shows it)
    - expected_name: The locator's exact current name (required safety check)
    - confirm: false = preview only (default), true = delete
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("delete_locator")
        if missing:
            return missing
        if expected_name is None:
            return ("Error deleting locator: expected_name is required. Read the "
                    "locator's name with get_cue_points and pass it exactly.")
        ableton = get_ableton_connection()
        params = {"time": time, "expected_name": expected_name}
        if not confirm:
            preview = ableton.send_command("delete_locator", dict(params, dry_run=True))
            return (
                "NOT DELETED (preview only). This would delete: "
                + json.dumps(preview, indent=2)
                + "\nTo delete, call delete_locator again with the same time "
                "and expected_name and confirm=true."
            )
        result = ableton.send_command("delete_locator", dict(params, dry_run=False))
        return "Deleted locator. " + json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error deleting locator: {str(e)}")
        return f"Error deleting locator: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("create_locator")
def create_locator(
    ctx: Context,
    name: str,
    time: float,
    user_prompt: str = ""
) -> str:
    """
    Create a named locator (cue point) in the Arrangement at a beat position.

    If a locator already exists at that beat (within ~1e-3 tolerance) it is
    renamed instead of toggled off. Time is in beats from the start of the
    arrangement (e.g. 0.0 = start, 16.0 = bar 5 in 4/4).

    The transport must be stopped: the playhead is moved to the locator time,
    Live is given a moment to apply it, and it is put back afterwards (this
    takes about a second). Live puts locators on whole beats, so a fractional
    time lands on a beat and the reply says so.

    Parameters:
    - name: The locator label (e.g. "Chorus", "Verse 1", "Drop")
    - time: Beat position where the locator should sit
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("create_locator")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command(
            "create_locator",
            {"name": name, "time": time}
        )
        message = (
            f"Locator '{result.get('name', name)}' set at beat "
            f"{result.get('time', time)}"
        )
        if result.get("note"):
            message += f". {result['note']}"
        return message
    except Exception as e:
        logger.error(f"Error creating locator: {str(e)}")
        return f"Error creating locator: {str(e)}"


# ── Dataset / preference tools (Supabase trajectory recording) ─────────────────

@mcp.tool()
@telemetry_tool("submit_intent")
@trajectory_tool("submit_intent", modifying=False)
def submit_intent(
    ctx: Context,
    text: str,
    level: int = 5,
    user_prompt: str = "",
) -> str:
    """
    Record the human's creative intent for subsequent actions in this session.

    Call this before a sequence of edits so trajectory steps are conditioned on intent.
    Levels: 1=atomic, 2=musical op, 3=section, 4=song, 5=creative goal.

    Requires telemetry consent. Data is stored in Supabase (same project as telemetry).

    Parameters:
    - text: Natural-language intent (e.g. "make the chorus feel bigger")
    - level: Hierarchical intent level 1–5 (default 5)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.set_intent(text=text, level=level)
        return (
            f"Recorded intent {event.intent_id} (level {level}): {text!r}. "
            f"Session: {recorder.session_id}"
        )
    except Exception as e:
        logger.error(f"Error submitting intent: {str(e)}")
        return f"Error submitting intent: {str(e)}"


@mcp.tool()
@telemetry_tool("rate_last_action")
@trajectory_tool("rate_last_action", modifying=False)
def rate_last_action(
    ctx: Context,
    rating: str,
    tags: str = "",
    note: str = "",
    user_prompt: str = "",
) -> str:
    """
    Rate the most recent recorded action (or the track after an edit).

    Ratings: better | same | worse | keep | reject | thumbs_up | thumbs_down
    Optional tags (comma-separated): groove, harmony, melody, sound, arrangement,
    energy, mix, emotion

    Requires telemetry consent.

    Parameters:
    - rating: Preference label
    - tags: Comma-separated aspect tags
    - note: Optional free-text reason
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        event = recorder.record_preference(
            rating=rating.strip().lower(),
            tags=tag_list,
            note=note or None,
        )
        target = event.target_action_id or "none"
        return f"Recorded preference {rating!r} for action {target}"
    except Exception as e:
        logger.error(f"Error rating action: {str(e)}")
        return f"Error rating action: {str(e)}"


@mcp.tool()
@telemetry_tool("prefer_candidate")
@trajectory_tool("prefer_candidate", modifying=False)
def prefer_candidate(
    ctx: Context,
    candidate_a: str,
    candidate_b: str,
    winner: str,
    reason: str = "",
    user_prompt: str = "",
) -> str:
    """
    Record a pairwise preference between two candidate actions or auditions.

    winner should be 'a', 'b', or an explicit candidate id matching A or B.

    Requires telemetry consent.

    Parameters:
    - candidate_a: Id / URI / label for option A
    - candidate_b: Id / URI / label for option B
    - winner: 'a', 'b', or the winning id
    - reason: Optional reason ("C has the right attack")
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        w = winner.strip().lower()
        if w == "a":
            w = candidate_a
        elif w == "b":
            w = candidate_b
        event = recorder.record_preference(
            rating="pairwise",
            winner=w,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            note=reason or None,
        )
        return f"Recorded pairwise preference: winner={w!r} (event {event.event_id})"
    except Exception as e:
        logger.error(f"Error recording pairwise preference: {str(e)}")
        return f"Error recording pairwise preference: {str(e)}"


@mcp.tool()
@telemetry_tool("reject_last_action")
@trajectory_tool("reject_last_action", modifying=False)
def reject_last_action(
    ctx: Context,
    reason: str = "",
    user_prompt: str = "",
) -> str:
    """
    Mark the last action as rejected (exploration / preference boundary).

    Use when the human undoes or discards an agent edit. Requires telemetry consent.

    Parameters:
    - reason: Optional why it was rejected
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.record_preference(
            rating="reject",
            note=reason or None,
        )
        return f"Recorded rejection for action {event.target_action_id or 'none'}"
    except Exception as e:
        logger.error(f"Error rejecting action: {str(e)}")
        return f"Error rejecting action: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("record_audition")
@trajectory_tool("record_audition", modifying=False)
def record_audition(
    ctx: Context,
    uri: str,
    kept: bool = False,
    search_query: str = "",
    dwell_ms: float = 0.0,
    user_prompt: str = "",
) -> str:
    """
    Log a browser/preset/sample audition (keep or reject) for preference learning.

    Call once per candidate auditioned. Does not load the device — use
    load_instrument_or_effect when kept=True and you want to commit.

    Requires telemetry consent.

    Parameters:
    - uri: Browser item URI (or stable preset/sample id)
    - kept: Whether this candidate was kept
    - search_query: Optional search text that led here (e.g. "analog bass")
    - dwell_ms: Optional time spent auditioning
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    recorder = get_recorder()
    if recorder is None:
        return (
            "Dataset recording is off (telemetry disabled or user has not consented)."
        )
    try:
        event = recorder.record_audition(
            uri=uri,
            kept=kept,
            search_query=search_query or None,
            dwell_ms=dwell_ms if dwell_ms > 0 else None,
        )
        status = "kept" if kept else "rejected"
        return f"Recorded audition ({status}) uri={uri!r} event={event.event_id}"
    except Exception as e:
        logger.error(f"Error recording audition: {str(e)}")
        return f"Error recording audition: {str(e)}"


# ── Mixer tools ───────────────────────────────────────────────────────────────

@mcp.tool()
@telemetry_tool("get_mixer")
@trajectory_tool("get_mixer")
def get_mixer(ctx: Context, track_index: int = 0, track_type: str = "track",
              user_prompt: str = "") -> str:
    """
    Get the mixer state (volume, panning and sends) for a track.

    Each value is reported three ways: the raw 0..1 parameter value, the dB it
    corresponds to, and the string Live itself displays.

    Parameters:
    - track_index: The index of the track (ignored when track_type is "master")
    - track_type: "track" (default), "return", or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_mixer")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("get_mixer", {
            "track_index": track_index,
            "track_type": track_type
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting mixer: {str(e)}")
        return f"Error getting mixer: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_track_volume")
@trajectory_tool("set_track_volume")
def set_track_volume(
    ctx: Context,
    track_index: int,
    db: Optional[float] = None,
    value: Optional[float] = None,
    track_type: str = "track",
    user_prompt: str = ""
) -> str:
    """
    Set a track's volume fader.

    Prefer `db` — Live's fader taper is non-linear, so the raw 0..1 value is not
    proportional to level (0.85 is 0 dB, 1.0 is +6 dB). Passing `db` resolves the
    exact fader position for that level using Live's own readout.

    Parameters:
    - track_index: The index of the track (ignored when track_type is "master")
    - db: Target level in decibels, e.g. -4.0. Clamped to the fader range.
    - value: Raw fader position 0.0-1.0, as an alternative to db
    - track_type: "track" (default), "return", or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_track_volume")
        if missing:
            return missing
        if db is None and value is None:
            return "Error: provide either db or value"
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_volume", {
            "track_index": track_index,
            "db": db,
            "value": value,
            "track_type": track_type
        })
        return f"Set volume of '{result.get('name')}' to {result.get('display')}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_track_panning")
@trajectory_tool("set_track_panning")
def set_track_panning(
    ctx: Context,
    track_index: int,
    value: float,
    track_type: str = "track",
    user_prompt: str = ""
) -> str:
    """
    Set a track's pan position.

    Parameters:
    - track_index: The index of the track (ignored when track_type is "master")
    - value: -1.0 is hard left, 0.0 is centre, 1.0 is hard right
    - track_type: "track" (default), "return", or "master"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_track_panning")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_panning", {
            "track_index": track_index,
            "value": value,
            "track_type": track_type
        })
        return f"Set panning of '{result.get('name')}' to {result.get('display')}"
    except Exception as e:
        logger.error(f"Error setting track panning: {str(e)}")
        return f"Error setting track panning: {str(e)}"

@mcp.tool()
@rich_telemetry_tool("set_send")
@trajectory_tool("set_send")
def set_send(
    ctx: Context,
    track_index: int,
    send_index: int,
    db: Optional[float] = None,
    value: Optional[float] = None,
    track_type: str = "track",
    user_prompt: str = ""
) -> str:
    """
    Set one of a track's send levels.

    As with volume, prefer `db` over the raw value. The master track has no sends.

    Parameters:
    - track_index: The index of the track
    - send_index: Which send to set (0 is the first return track, A)
    - db: Target send level in decibels, e.g. -12.0
    - value: Raw send position 0.0-1.0, as an alternative to db
    - track_type: "track" (default) or "return"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_send")
        if missing:
            return missing
        if db is None and value is None:
            return "Error: provide either db or value"
        ableton = get_ableton_connection()
        result = ableton.send_command("set_send", {
            "track_index": track_index,
            "send_index": send_index,
            "db": db,
            "value": value,
            "track_type": track_type
        })
        return f"Set send {result.get('send')} on '{result.get('name')}' to {result.get('display')}"
    except Exception as e:
        logger.error(f"Error setting send: {str(e)}")
        return f"Error setting send: {str(e)}"

@mcp.tool()
@telemetry_tool("create_return_track")
@trajectory_tool("create_return_track")
def create_return_track(ctx: Context, name: str = "", user_prompt: str = "") -> str:
    """
    Add a return track to the Live Set and return the new list of return tracks.

    Side effects: the Set gains a return track, and so a new send on every
    track. Undoable with Live's undo. Live Lite allows only 2 return tracks:
    when the Set is full nothing is created and an explanatory error is returned.

    Parameters:
    - name: Optional name for the new return track (empty keeps Live's default)
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("create_return_track")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("create_return_track", {"name": name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error creating return track: {str(e)}")
        return f"Error creating return track: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("load_device_on_return")
@trajectory_tool("load_device_on_return")
def load_device_on_return(ctx: Context, return_track_index: int, uri: str,
                          user_prompt: str = "") -> str:
    """
    Load an effect from the browser onto a return track, by browser URI.

    Side effects: Live loads browser items onto the selected track, so the
    return track is selected for the load and the previously selected track is
    restored afterwards (the reply says whether that worked). The return track
    gains a device. After a short settle the reply lists the return's devices
    as read back from Live; "loaded" is true only if that list grew. Find URIs
    with get_browser_tree / get_browser_items_at_path. Return tracks take audio
    effects; instruments are not expected to load there.

    Parameters:
    - return_track_index: Index of the return track (0 = A)
    - uri: Browser URI of the device to load
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("load_device_on_return")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("load_device_on_return", {
            "return_track_index": return_track_index,
            "uri": uri,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error loading device on return track: {str(e)}")
        return f"Error loading device on return track: {str(e)}"


@mcp.tool()
@rich_telemetry_tool("set_time_signature")
@trajectory_tool("set_time_signature")
def set_time_signature(ctx: Context, numerator: int, denominator: int, user_prompt: str = "") -> str:
    """
    Set the Live Set's global time signature (undoable with Live's undo).

    Parameters:
    - numerator: Beats per bar, an integer from 1 to 99
    - denominator: Note value of one beat: 1, 2, 4, 8 or 16
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_time_signature")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("set_time_signature", {"numerator": numerator, "denominator": denominator})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in set_time_signature: {str(e)}")
        return f"Error in set_time_signature: {str(e)}"


@mcp.tool()
@telemetry_tool("set_metronome")
@trajectory_tool("set_metronome")
def set_metronome(ctx: Context, enabled: bool, user_prompt: str = "") -> str:
    """
    Turn Live's metronome on or off. This is a Set-wide setting and is audible
    immediately. The reply gives the requested state and what Live read back
    (Live may apply the change just after replying).

    Parameters:
    - enabled: true = metronome on, false = off
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_metronome")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("set_metronome", {"enabled": enabled})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in set_metronome: {str(e)}")
        return f"Error in set_metronome: {str(e)}"


@mcp.tool()
@telemetry_tool("get_arrangement_loop")
@trajectory_tool("get_arrangement_loop")
def get_arrangement_loop(ctx: Context, user_prompt: str = "") -> str:
    """
    Read the arrangement loop brace: whether looping is on, loop_start,
    loop_length and loop_end, all in beats.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_arrangement_loop")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_loop", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in get_arrangement_loop: {str(e)}")
        return f"Error in get_arrangement_loop: {str(e)}"


@mcp.tool()
@telemetry_tool("set_arrangement_loop")
@trajectory_tool("set_arrangement_loop")
def set_arrangement_loop(ctx: Context, loop_start: Optional[float] = None, loop_length: Optional[float] = None, enabled: Optional[bool] = None, user_prompt: str = "") -> str:
    """
    Set the arrangement loop brace and/or switch looping on or off. Give at
    least one of the three; omitted ones are left alone. Changes the Set's loop
    region, which also changes what repeats if the transport is playing.

    Parameters:
    - loop_start: Loop start in beats, 0 or more (e.g. 16.0 = bar 5 in 4/4)
    - loop_length: Loop length in beats, greater than 0
    - enabled: true = loop on, false = loop off
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("set_arrangement_loop")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_loop", {"loop_start": loop_start, "loop_length": loop_length, "enabled": enabled})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in set_arrangement_loop: {str(e)}")
        return f"Error in set_arrangement_loop: {str(e)}"


@mcp.tool()
@telemetry_tool("get_cue_points")
@trajectory_tool("get_cue_points")
def get_cue_points(ctx: Context, user_prompt: str = "") -> str:
    """
    List the arrangement's cue points (locators) as name and time in beats,
    sorted by time. Read-only; this does not create or delete locators.

    Parameters:
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("get_cue_points")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("get_cue_points", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in get_cue_points: {str(e)}")
        return f"Error in get_cue_points: {str(e)}"


@mcp.tool()
@telemetry_tool("jump_to_cue")
@trajectory_tool("jump_to_cue")
def jump_to_cue(ctx: Context, direction: str = "next", user_prompt: str = "") -> str:
    """
    Move the playhead to the next or previous cue point (locator). The playhead
    moves, and playback continues from there if the transport is playing. If
    there is no cue point in that direction nothing moves and an error is
    returned. Live performs the jump just after replying, so the reply gives
    the position expected from the cue list rather than a read-back.

    Parameters:
    - direction: "next" (default) or "previous"
    - user_prompt: The original user prompt that led to this tool call (for telemetry)
    """
    try:
        from .script_handshake import require_capability

        missing = require_capability("jump_to_cue")
        if missing:
            return missing
        ableton = get_ableton_connection()
        result = ableton.send_command("jump_to_cue", {"direction": direction})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error in jump_to_cue: {str(e)}")
        return f"Error in jump_to_cue: {str(e)}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()