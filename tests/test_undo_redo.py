"""Tests for undo / redo, guarded by Song.can_undo / Song.can_redo.

Remote Script side runs against a mocked Song with a real undo/redo stack
(no Ableton, no socket); server side runs the real tool functions with the
connection faked.
"""

import asyncio
import importlib.util
import inspect
import sys
import types
from pathlib import Path

import pytest

import MCP_Server.server as server
from MCP_Server.dataset.trajectory_decorator import MODIFYING_TOOLS
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SCRIPT = (REPO_ROOT / "MCP_Server" / "bundled_ableton_remote_script"
                  / "AbletonMCP_init.py")


# ----------------------------------------------------------------- fixtures

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
        "ableton_mcp_script_undo_redo", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeSong(object):
    """A song whose tempo edits land on an undo stack, like Live's."""

    def __init__(self):
        self.tempo = 120.0
        self._undo = []
        self._redo = []
        self.undo_calls = 0
        self.redo_calls = 0

    def set_tempo(self, value):
        self._undo.append(self.tempo)
        self._redo = []
        self.tempo = value

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        self.undo_calls += 1
        if not self._undo:
            raise RuntimeError("Nothing to undo")  # what Live does unguarded
        self._redo.append(self.tempo)
        self.tempo = self._undo.pop()

    def redo(self):
        self.redo_calls += 1
        if not self._redo:
            raise RuntimeError("Nothing to redo")
        self._undo.append(self.tempo)
        self.tempo = self._redo.pop()


@pytest.fixture
def song():
    return FakeSong()


@pytest.fixture
def inst(script_module, song):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = song
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []

    def schedule_message(delay, callback):
        obj.scheduled.append((delay, callback.__name__))
        callback()

    obj.schedule_message = schedule_message
    return obj


def run(inst, command, **params):
    """Send a command with the given params (no params = the safe preview)."""
    return inst._process_command({"type": command, "params": params})


def act(inst, command):
    """undo / redo for real (what confirm=true sends)."""
    return run(inst, command, dry_run=False)


# ------------------------------------------------------------- remote script

def test_undo_reverts_one_step_and_reports_the_new_state(inst, song):
    song.set_tempo(100.0)
    song.set_tempo(90.0)
    reply = act(inst, "undo")
    assert reply["status"] == "success"
    assert reply["result"]["performed"] is True
    assert reply["result"]["action"] == "undo"
    assert song.tempo == 100.0          # exactly one step
    assert reply["result"]["can_undo"] is True
    assert reply["result"]["can_redo"] is True


def test_undo_with_nothing_to_undo_is_a_clear_message_not_an_error(inst, song):
    reply = act(inst, "undo")
    assert reply["status"] == "success"
    assert reply["result"]["performed"] is False
    assert "Nothing to undo" in reply["result"]["message"]
    assert reply["result"]["can_undo"] is False
    assert song.undo_calls == 0  # Live's undo() is not even called


def test_redo_replays_the_undone_step(inst, song):
    song.set_tempo(100.0)
    act(inst, "undo")
    reply = act(inst, "redo")
    assert reply["result"]["performed"] is True
    assert song.tempo == 100.0
    assert reply["result"]["can_redo"] is False
    assert reply["result"]["can_undo"] is True


def test_redo_with_nothing_to_redo_is_a_clear_message(inst, song):
    reply = act(inst, "redo")
    assert reply["status"] == "success"
    assert reply["result"]["performed"] is False
    assert "Nothing to redo" in reply["result"]["message"]
    assert song.redo_calls == 0


def test_a_new_edit_clears_redo(inst, song):
    song.set_tempo(100.0)
    act(inst, "undo")
    song.set_tempo(80.0)
    reply = act(inst, "redo")
    assert reply["result"]["performed"] is False
    assert song.tempo == 80.0


def test_undo_all_the_way_stops_cleanly(inst, song):
    song.set_tempo(100.0)
    song.set_tempo(90.0)
    results = [act(inst, "undo")["result"]["performed"] for _ in range(3)]
    assert results == [True, True, False]
    assert song.tempo == 120.0


def test_a_live_failure_is_reported_as_an_error(inst, song):
    song.set_tempo(100.0)

    def boom():
        raise RuntimeError("Live said no")

    song.undo = boom
    reply = act(inst, "undo")
    assert reply["status"] == "error"
    assert "Live said no" in reply["message"]


# ------------------------------------------------------- preview / confirm guard

@pytest.mark.parametrize("command", ["undo", "redo"])
def test_default_is_a_preview_that_never_calls_live(inst, song, command):
    song.set_tempo(100.0)
    song.set_tempo(90.0)
    act(inst, "undo")  # one step to undo and one to redo
    song.undo_calls = song.redo_calls = 0
    tempo = song.tempo
    reply = run(inst, command)  # no params at all: must be the preview
    result = reply["result"]
    assert reply["status"] == "success"
    assert result["performed"] is False and result["dry_run"] is True
    assert song.undo_calls == 0 and song.redo_calls == 0
    assert song.tempo == tempo
    assert "PREVIEW ONLY" in result["message"] and "nothing was changed" in result["message"]
    assert "confirm=true" in result["message"]
    assert result["can_undo"] is True and result["can_redo"] is True


@pytest.mark.parametrize("command", ["undo", "redo"])
def test_explicit_dry_run_true_is_a_preview(inst, song, command):
    song.set_tempo(100.0)
    song.set_tempo(90.0)
    act(inst, "undo")
    song.undo_calls = song.redo_calls = 0
    run(inst, command, dry_run=True)
    assert song.undo_calls == 0 and song.redo_calls == 0


def test_preview_warns_that_one_undo_reverts_several_changes(inst, song):
    song.set_tempo(100.0)
    result = run(inst, "undo")["result"]
    for text in ("ONE undo step", "SEVERAL MCP changes",
                 "user's own recent manual edits"):
        assert text in result["message"]
        assert text in result["warning"]
    assert result["can_undo"] is True and result["can_redo"] is False


def test_confirmed_undo_acts_and_still_carries_the_warning(inst, song):
    song.set_tempo(100.0)
    result = act(inst, "undo")["result"]
    assert song.undo_calls == 1 and song.tempo == 120.0
    assert result["performed"] is True and result["dry_run"] is False
    assert "SEVERAL MCP changes" in result["message"]
    assert "SEVERAL MCP changes" in result["warning"]


def test_confirmed_redo_acts(inst, song):
    song.set_tempo(100.0)
    act(inst, "undo")
    result = act(inst, "redo")["result"]
    assert song.redo_calls == 1 and song.tempo == 100.0
    assert result["performed"] is True


def test_preview_with_nothing_to_undo_says_so(inst, song):
    result = run(inst, "undo")["result"]
    assert result["performed"] is False
    assert "Nothing to undo" in result["message"]
    assert song.undo_calls == 0


def test_direct_call_defaults_to_preview(inst, song):
    song.set_tempo(100.0)
    assert inst._undo_redo("undo")["performed"] is False
    assert song.undo_calls == 0
    assert inst._undo_redo("undo", dry_run=False)["performed"] is True


def test_missing_can_flags_are_treated_as_nothing_to_do(script_module):
    """An older Live without can_undo/can_redo must not crash or call undo()."""
    class Bare(object):
        def undo(self):
            raise AssertionError("must not be called")

    inst = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    inst._song = Bare()
    inst.log_message = lambda *a, **k: None
    result = inst._undo_redo("undo")
    assert result["performed"] is False


def test_unknown_action_is_rejected(inst):
    with pytest.raises(ValueError):
        inst._undo_redo("rewind")


# ------------------------------------------------- scheduling / handshake / docs

@pytest.mark.parametrize("command", ["undo", "redo"])
def test_commands_are_scheduled_on_the_main_thread(inst, song, command):
    song.set_tempo(100.0)
    act(inst, command)
    assert inst.scheduled == [(0, "main_thread_task")]


def test_version_and_capabilities(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    assert {"undo", "redo", "undo_confirm_guard"} <= set(
        script_module.SCRIPT_CAPABILITIES)


def test_tools_are_in_the_dataset_modifying_set():
    assert {"undo", "redo"} <= MODIFYING_TOOLS


class _FakeSock(object):
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        pass

    def recv(self, _size):
        return b'{"status": "success", "result": {}}'


@pytest.mark.parametrize("command", ["undo", "redo"])
def test_server_treats_the_commands_as_modifying(command):
    conn = server.AbletonConnection(host="x", port=1, sock=_FakeSock())
    conn.send_command(command, {})
    assert conn.sock.timeouts[0] == 15.0


# ------------------------------------------------------------- server tools

class FakeConnection(object):
    def __init__(self):
        self.response = {}
        self.raise_exc = None
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, dict(params or {})))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    fake = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: fake)
    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    return fake


def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


def test_undo_tool_sends_the_command_and_reports_success(conn):
    conn.response = {"performed": True, "can_undo": False, "can_redo": True}
    out = call(server.undo, None, confirm=True)
    assert conn.sent == [("undo", {"dry_run": False})]
    assert out.startswith("Undo done")
    assert "SEVERAL MCP changes" in out
    assert "can redo: True" in out


def test_redo_tool_sends_the_command_and_reports_success(conn):
    conn.response = {"performed": True, "can_undo": True, "can_redo": False}
    out = call(server.redo, None, confirm=True)
    assert conn.sent == [("redo", {"dry_run": False})]
    assert out.startswith("Redo done")


@pytest.mark.parametrize("name", ["undo", "redo"])
def test_tools_preview_by_default_and_never_confirm_implicitly(conn, name):
    conn.response = {
        "performed": False, "dry_run": True,
        "message": "PREVIEW ONLY, nothing was changed. WARNING: ONE undo step ...",
        "can_undo": True, "can_redo": False}
    out = call(getattr(server, name), None)
    assert conn.sent == [(name, {"dry_run": True})]
    assert out.startswith("PREVIEW ONLY")
    assert "can undo: True" in out and "can redo: False" in out
    assert not out.startswith(name.capitalize() + " done")
    conn.sent.clear()
    call(getattr(server, name), None, confirm=False)
    assert conn.sent == [(name, {"dry_run": True})]


@pytest.mark.parametrize("name", ["undo", "redo"])
def test_tool_docstrings_carry_the_warning(name):
    doc = getattr(server, name).__doc__
    assert "ONE undo step" in doc and "SEVERAL" in doc
    assert "confirm=false" in doc and "confirm=true" in doc
    assert "manual edits" in doc


def test_tools_relay_the_nothing_to_do_message(conn):
    conn.response = {"performed": False,
                     "message": "Nothing to undo: Live's undo history is empty"}
    assert call(server.undo, None, confirm=True) == (
        "Nothing to undo: Live's undo history is empty")
    conn.response = {"performed": False}
    assert call(server.redo, None, confirm=True) == "Nothing to redo"


def test_tools_report_connection_errors(conn):
    conn.raise_exc = Exception("Connection to Ableton lost")
    assert call(server.undo, None).startswith("Error performing undo:")
    assert call(server.redo, None).startswith("Error performing redo:")


@pytest.mark.parametrize("name", ["undo", "redo"])
def test_tools_return_the_capability_message_for_an_old_script(conn, monkeypatch, name):
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(sh, "require_capability", lambda cap: "missing " + cap)
    assert call(getattr(server, name), None) == "missing " + name
    assert call(getattr(server, name), None, confirm=True) == "missing " + name
    assert conn.sent == []


@pytest.mark.parametrize("name", ["undo", "redo"])
def test_tools_refuse_a_script_without_the_confirm_guard(conn, monkeypatch, name):
    """An older script ignores dry_run and would undo at once."""
    import MCP_Server.script_handshake as sh
    monkeypatch.setattr(
        sh, "require_capability",
        lambda cap: "missing " + cap if cap == "undo_confirm_guard" else None)
    assert call(getattr(server, name), None, confirm=True) == "missing undo_confirm_guard"
    assert conn.sent == []


def test_tools_take_no_required_arguments_and_confirm_defaults_false():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("undo", "redo"):
        schema = tools[name].inputSchema
        assert not schema.get("required")
        assert schema["properties"]["confirm"]["default"] is False
