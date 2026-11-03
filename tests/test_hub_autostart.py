"""The Remote Script keeps the MIDI hub running: how it tells the hub is up, and how a second hub steps aside."""

import importlib.util
import socket
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script" / "AbletonMCP_init.py"

# /proc/net/tcp as on the Push: 0x223E = 8766, 0x2695 = 9877; st 0A = LISTEN, 01 = ESTABLISHED
HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
LIVE_ONLY = "   0: 0100007F:2695 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 1\n"
HUB = "   1: 00000000:223E 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 2 1\n"
HUB_CLIENT = "   2: E000000A:223E 9A02000A:C350 01 00000000:00000000 00:00000000 00000000  1000        0 3 1\n"


def _script():
    framework = types.ModuleType("_Framework")
    control_surface = types.ModuleType("_Framework.ControlSurface")
    control_surface.ControlSurface = type("ControlSurface", (object,), {})
    framework.ControlSurface = control_surface
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface)
    spec = importlib.util.spec_from_file_location("ableton_mcp_script_hub", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hub_counts_as_up_only_while_listening(tmp_path):
    script = _script()
    table = tmp_path / "tcp"
    table.write_text(HEADER + LIVE_ONLY + HUB)
    assert script._hub_listening(str(table))
    table.write_text(HEADER + LIVE_ONLY + HUB_CLIENT)  # a connection left over after the hub stopped
    assert not script._hub_listening(str(table))
    assert not script._hub_listening(str(tmp_path / "missing"))


def test_second_hub_sees_the_port_taken():
    from MCP_Server.midi_hub import port_taken
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    try:
        assert port_taken("127.0.0.1", held.getsockname()[1])
    finally:
        held.close()
