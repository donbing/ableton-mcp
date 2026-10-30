"""Cross-feature checks for the combined local build.

Each feature branch has its own tests; these guard the seams that only exist
once they are merged: every advertised capability reaches a handler, every new
tool is registered with the MCP server, and the Remote Script and the server
agree on the version.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

import MCP_Server.server as server
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")

NEW_TOOLS = {
    "get_mixer", "set_track_volume", "set_track_panning", "set_send",
    "set_track_mute", "set_track_solo", "set_track_arm",
    "delete_track", "get_meters", "undo", "redo", "get_device_parameters",
}

NEW_CAPABILITIES = {
    "get_mixer", "set_track_volume", "set_track_panning", "set_send",
    "set_track_mute", "set_track_solo", "set_track_arm", "delete_track",
    "get_meters", "undo", "redo", "get_device_parameters_v2",
}


# Capabilities that advertise a feature of an existing command, not a command.
FEATURE_FLAGS = {"get_device_parameters_v2", "undo_confirm_guard", "undo_steps", "start_playback_at_beat"}


def _load_script_module():
    framework = types.ModuleType("_Framework")
    control_surface_mod = types.ModuleType("_Framework.ControlSurface")

    class _StubControlSurface(object):
        def __init__(self, *args, **kwargs):
            pass

        def log_message(self, *args, **kwargs):
            pass

        def show_message(self, *args, **kwargs):
            pass

    control_surface_mod.ControlSurface = _StubControlSurface
    framework.ControlSurface = control_surface_mod
    sys.modules.setdefault("_Framework", framework)
    sys.modules.setdefault("_Framework.ControlSurface", control_surface_mod)
    spec = importlib.util.spec_from_file_location(
        "ableton_mcp_script_combined", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


def test_script_and_server_agree_on_the_version(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    assert script_module.SCRIPT_VERSION not in ("1.7.1", "1.8.0", "1.8.1", "1.9.0")


def test_capabilities_have_no_duplicates(script_module):
    caps = script_module.SCRIPT_CAPABILITIES
    assert len(caps) == len(set(caps))


def test_every_new_script_command_is_advertised(script_module):
    assert NEW_CAPABILITIES <= set(script_module.SCRIPT_CAPABILITIES)


def test_every_advertised_capability_reaches_a_handler(script_module):
    """A capability that dispatches to 'Unknown command' would make the
    handshake promise something the script cannot do. Parameters are junk on
    purpose: handlers may fail, but must not be missing. Feature flags (see
    FEATURE_FLAGS) are checked against their command instead."""
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    inst._song = mock.MagicMock()
    inst.log_message = lambda *a, **k: None
    inst.show_message = lambda *a, **k: None
    inst.running = True
    inst.application = lambda: None
    inst.schedule_message = lambda delay, callback: callback()
    for name in script_module.SCRIPT_CAPABILITIES:
        if name in FEATURE_FLAGS:
            continue
        reply = inst._process_command(
            {"type": name, "params": {"seconds": 0.1, "hz": 5}})
        assert not reply.get("message", "").startswith("Unknown command"), name


def test_every_new_tool_is_registered():
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert NEW_TOOLS <= tools


def test_feature_flags_belong_to_a_dispatched_command(script_module):
    assert "get_device_parameters" in script_module.SCRIPT_CAPABILITIES
    assert FEATURE_FLAGS <= set(script_module.SCRIPT_CAPABILITIES)


def test_undo_and_redo_preview_by_default_through_the_real_dispatcher(script_module):
    """Seam: with no params the combined script must never call song.undo()."""
    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    inst._song = mock.MagicMock()
    inst.log_message = lambda *a, **k: None
    inst.schedule_message = lambda delay, callback: callback()
    for command in ("undo", "redo"):
        reply = inst._process_command({"type": command, "params": {}})
        assert reply["status"] == "success"
        assert reply["result"]["performed"] is False
        assert reply["result"]["dry_run"] is True
    inst._song.undo.assert_not_called()
    inst._song.redo.assert_not_called()
