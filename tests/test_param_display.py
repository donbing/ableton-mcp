"""Tests for get_device_parameters: display strings, filters and the rack guard.

Runs the real Remote Script code against a mocked Live Object Model (no
Ableton, no socket). The parameter fake mirrors DeviceParameter: str_for_value
returns Live's display text; quantized parameters show their item name.
"""

import asyncio
import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path

import pytest

import MCP_Server.server as server
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
        "ableton_mcp_script_param_display", BUNDLED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeParam(object):
    def __init__(self, name, value=0.5, minimum=0.0, maximum=1.0, fmt=None,
                 items=None):
        self.name = name
        self.value = value
        self.min = minimum
        self.max = maximum
        self.is_quantized = items is not None
        self.is_enabled = True
        self._fmt = fmt or (lambda v: "%.2f" % v)
        self._items = items

    def str_for_value(self, value):
        if self._items is not None:
            return self._items[int(value)]
        return self._fmt(value)


class FakeDevice(object):
    can_have_chains = False
    can_have_drum_pads = False
    class_display_name = "Operator"

    def __init__(self, name, parameters, class_name="Operator"):
        self.name = name
        self.class_name = class_name
        self.parameters = parameters


class FakeChain(object):
    def __init__(self, name, devices):
        self.name = name
        self.devices = devices


class FakeRack(FakeDevice):
    can_have_chains = True
    class_display_name = "Instrument Rack"

    def __init__(self, name, parameters, chains, return_chains=(), drum=False):
        FakeDevice.__init__(self, name, parameters, class_name="InstrumentGroupDevice")
        self.chains = list(chains)
        self.return_chains = list(return_chains)
        self.can_have_drum_pads = drum


class FakeTrack(object):
    def __init__(self, devices):
        self.devices = devices


class FakeSong(object):
    def __init__(self, devices):
        self.tracks = [FakeTrack(devices)]


def synth():
    return FakeDevice("Operator", [
        FakeParam("Device On", 1.0, fmt=lambda v: "On" if v else "Off"),
        FakeParam("Filter Freq", 0.5, fmt=lambda v: "%.1f kHz" % (v * 4)),
        FakeParam("Filter Res", 0.25, fmt=lambda v: "%d %%" % (v * 100)),
        FakeParam("Osc A Wave", 1, 0, 2, items=["Sine", "Saw", "Square"]),
        FakeParam("Volume", 0.85, fmt=lambda v: "%.1f dB" % ((v - 0.85) * 40)),
        FakeParam("Filter Env Attack", 0.1, fmt=lambda v: "%d ms" % (v * 1000)),
    ])


def make_rack(chains=2, devices_per_chain=2, params_per_device=50, drum=False,
              return_chains=0):
    def chain(i):
        return FakeChain("Chain %d" % i, [
            FakeDevice("Dev %d.%d" % (i, d),
                       [FakeParam("P%d" % p) for p in range(params_per_device)])
            for d in range(devices_per_chain)])
    macros = [FakeParam("Macro %d" % (i + 1), 0.0, 0, 127,
                        fmt=lambda v: "%d" % v) for i in range(8)]
    return FakeRack("Big Rack", macros, [chain(i) for i in range(chains)],
                    return_chains=[chain(100 + i) for i in range(return_chains)],
                    drum=drum)


def make_inst(script_module, devices):
    obj = script_module.AbletonMCP.__new__(script_module.AbletonMCP)
    obj._song = FakeSong(devices)
    obj.log_message = lambda *a, **k: None
    obj.show_message = lambda *a, **k: None
    obj.scheduled = []
    obj.schedule_message = lambda delay, cb: obj.scheduled.append((delay, cb))
    return obj


def read(inst, **params):
    params.setdefault("track_index", 0)
    params.setdefault("device_index", 0)
    reply = inst._process_command({"type": "get_device_parameters", "params": params})
    return reply


def device_of(reply):
    assert reply["status"] == "success", reply
    return reply["result"]["device"]


@pytest.fixture
def inst(script_module):
    return make_inst(script_module, [synth()])


# ------------------------------------------------------------ display strings

def test_every_parameter_carries_the_display_string(inst):
    params = device_of(read(inst))["parameters"]
    by_name = {p["name"]: p for p in params}
    assert by_name["Filter Freq"]["display"] == "2.0 kHz"
    assert by_name["Volume"]["display"] == "0.0 dB"
    assert by_name["Filter Env Attack"]["display"] == "100 ms"
    assert by_name["Device On"]["display"] == "On"
    assert all("display" in p for p in params)


def test_quantized_parameters_show_the_item_name(inst):
    wave = next(p for p in device_of(read(inst))["parameters"] if p["name"] == "Osc A Wave")
    assert wave["display"] == "Saw"
    assert wave["is_quantized"] is True


def test_existing_fields_are_unchanged(inst):
    param = device_of(read(inst))["parameters"][1]
    assert set(param) == {"index", "name", "value", "min", "max", "is_enabled",
                          "is_quantized", "display"}
    assert param["index"] == 1 and param["value"] == 0.5


def test_display_falls_back_to_str_when_str_for_value_fails(script_module):
    class Odd(FakeParam):
        def str_for_value(self, value):
            raise RuntimeError("no display")

        def __str__(self):
            return "3.5 Hz"

    dev = FakeDevice("D", [Odd("Rate")])
    param = device_of(read(make_inst(script_module, [dev])))["parameters"][0]
    assert param["display"] == "3.5 Hz"


def test_display_is_omitted_rather_than_a_default_object_repr(script_module):
    class NoDisplay(FakeParam):
        def str_for_value(self, value):
            return None

    dev = FakeDevice("D", [NoDisplay("Rate")])  # default repr starts with "<"
    param = device_of(read(make_inst(script_module, [dev])))["parameters"][0]
    assert "display" not in param
    assert param["name"] == "Rate"


def test_session_snapshot_path_is_unchanged(script_module):
    """_serialize_device without the new arguments (used by get_session_snapshot
    and the dataset recorder) must not grow a display field or metadata."""
    inst = make_inst(script_module, [synth()])
    info = inst._serialize_device(inst._song.tracks[0].devices[0], 0)
    assert all("display" not in p for p in info["parameters"])
    assert "parameters_total" not in info


# -------------------------------------------------------------------- filters

def test_name_contains_is_case_insensitive_and_keeps_real_indices(inst):
    info = device_of(read(inst, name_contains="FILTER"))
    assert [(p["index"], p["name"]) for p in info["parameters"]] == [
        (1, "Filter Freq"), (2, "Filter Res"), (5, "Filter Env Attack")]
    assert info["parameters_total"] == 6
    assert info["parameters_matched"] == 3
    assert info["parameters_truncated"] is False


def test_name_contains_with_no_match_is_empty_not_an_error(inst):
    info = device_of(read(inst, name_contains="nonexistent"))
    assert info["parameters"] == []
    assert info["parameters_matched"] == 0


def test_limit_truncates_and_says_so(inst):
    info = device_of(read(inst, limit=2))
    assert [p["name"] for p in info["parameters"]] == ["Device On", "Filter Freq"]
    assert info["parameters_total"] == 6
    assert info["parameters_matched"] == 6
    assert info["parameters_truncated"] is True


def test_limit_applies_after_the_name_filter(inst):
    info = device_of(read(inst, name_contains="filter", limit=2))
    assert [p["index"] for p in info["parameters"]] == [1, 2]
    assert info["parameters_matched"] == 3
    assert info["parameters_truncated"] is True


def test_limit_larger_than_the_list_is_not_truncated(inst):
    info = device_of(read(inst, limit=100))
    assert len(info["parameters"]) == 6
    assert info["parameters_truncated"] is False


def test_limit_zero_returns_only_the_counts(inst):
    info = device_of(read(inst, limit=0))
    assert info["parameters"] == []
    assert info["parameters_matched"] == 6 and info["parameters_truncated"] is True


def test_no_filter_means_no_extra_metadata(inst):
    info = device_of(read(inst))
    assert len(info["parameters"]) == 6
    assert not any(k.startswith("parameters_") for k in info)


@pytest.mark.parametrize("bad", [-1, "3", 1.5, True])
def test_invalid_limit_is_an_error(inst, bad):
    reply = read(inst, limit=bad)
    assert reply["status"] == "error"
    assert "limit" in reply["message"]


def test_invalid_name_contains_is_an_error(inst):
    reply = read(inst, name_contains=5)
    assert reply["status"] == "error"
    assert "name_contains" in reply["message"]


def test_filtered_index_works_with_set_device_parameter(script_module, inst):
    """The point of keeping real indices: the result feeds the setter."""
    param = device_of(read(inst, name_contains="res"))["parameters"][0]
    assert param["index"] == 2
    dev = inst._song.tracks[0].devices[0]
    assert dev.parameters[param["index"]].name == "Filter Res"


@pytest.mark.parametrize("track,device", [(5, 0), (-1, 0), (0, 9), (0, -1)])
def test_bounds_are_still_checked(inst, track, device):
    reply = read(inst, track_index=track, device_index=device)
    assert reply["status"] == "error"
    assert "out of range" in reply["message"]


# ------------------------------------------------------------------ rack guard

def test_rack_is_summarised_by_default(script_module):
    inst = make_inst(script_module, [make_rack(chains=3, devices_per_chain=2)])
    info = device_of(read(inst))
    assert "chains" not in info
    assert len(info["parameters"]) == 8  # the rack's own macros, with display
    assert info["parameters"][0]["display"] == "0"
    summary = info["rack_summary"]
    assert summary["chain_count"] == 3
    assert summary["return_chain_count"] == 0
    assert summary["nested_device_count"] == 6
    assert summary["chains"][0] == {
        "index": 0, "kind": "chains", "chain_name": "Chain 0",
        "device_names": ["Dev 0.0", "Dev 0.1"]}
    assert "include_racks=true" in summary["hint"]
    assert summary["chains_truncated"] is False


def test_rack_summary_is_a_small_fraction_of_the_full_payload(script_module):
    inst = make_inst(script_module, [make_rack(chains=24, devices_per_chain=3,
                                               params_per_device=100)])
    small = len(json.dumps(read(inst)["result"]))
    big = len(json.dumps(read(inst, include_racks=True)["result"]))
    assert big > 200000          # the problem being guarded against
    assert small < 8000
    assert small * 25 < big


def test_include_racks_returns_the_full_chain_contents_with_display(script_module):
    inst = make_inst(script_module, [make_rack(chains=2, devices_per_chain=2,
                                               params_per_device=3)])
    info = device_of(read(inst, include_racks=True))
    assert "rack_summary" not in info
    assert len(info["chains"]) == 2
    nested = info["chains"][1]["devices"][0]
    assert nested["name"] == "Dev 1.0"
    assert [p["name"] for p in nested["parameters"]] == ["P0", "P1", "P2"]
    assert all("display" in p for p in nested["parameters"])


def test_filters_reach_devices_inside_a_rack_when_included(script_module):
    inst = make_inst(script_module, [make_rack(chains=1, devices_per_chain=1,
                                               params_per_device=20)])
    info = device_of(read(inst, include_racks=True, name_contains="P1", limit=3))
    nested = info["chains"][0]["devices"][0]
    assert [p["name"] for p in nested["parameters"]] == ["P1", "P10", "P11"]
    assert nested["parameters_matched"] == 11
    assert nested["parameters_truncated"] is True


def test_macro_filter_applies_to_the_rack_summary(script_module):
    inst = make_inst(script_module, [make_rack()])
    info = device_of(read(inst, name_contains="macro 3"))
    assert [p["name"] for p in info["parameters"]] == ["Macro 3"]
    assert "rack_summary" in info


def test_drum_rack_is_a_rack_too(script_module):
    inst = make_inst(script_module, [make_rack(chains=4, drum=True)])
    info = device_of(read(inst))
    assert "chains" not in info and info["rack_summary"]["chain_count"] == 4


def test_return_chains_are_counted_in_the_summary(script_module):
    inst = make_inst(script_module, [make_rack(chains=2, return_chains=1)])
    summary = device_of(read(inst))["rack_summary"]
    assert summary["return_chain_count"] == 1
    assert summary["chains"][-1]["kind"] == "return_chains"


def test_huge_racks_cap_the_summary_chain_list(script_module):
    inst = make_inst(script_module, [make_rack(chains=100, devices_per_chain=1,
                                               params_per_device=1)])
    summary = device_of(read(inst))["rack_summary"]
    assert summary["chain_count"] == 100
    assert len(summary["chains"]) == 32
    assert summary["chains_truncated"] is True


def test_non_rack_devices_ignore_include_racks(script_module):
    inst = make_inst(script_module, [synth()])
    assert read(inst, include_racks=True)["result"] == read(inst)["result"]
    assert "rack_summary" not in device_of(read(inst))


# ----------------------------------------------- dispatch / handshake / bundle

def test_read_is_served_inline_not_scheduled(inst):
    read(inst, name_contains="x")
    assert inst.scheduled == []


def test_version_and_capability(script_module):
    assert script_module.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION
    assert "get_device_parameters_v2" in script_module.SCRIPT_CAPABILITIES
    assert "get_device_parameters" in script_module.SCRIPT_CAPABILITIES


# --------------------------------------------------------------- server tool

class FakeConnection(object):
    def __init__(self):
        self.response = {"track_index": 0, "device": {"parameters": []}}
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


def test_tool_default_call_is_the_same_wire_request_as_before(conn):
    call(server.get_device_parameters, None, 2, 1)
    assert conn.sent == [("get_device_parameters", {"track_index": 2, "device_index": 1})]


def test_tool_forwards_the_new_arguments(conn):
    call(server.get_device_parameters, None, 0, 0, name_contains="cutoff",
         limit=5, include_racks=True)
    assert conn.sent[0][1] == {"track_index": 0, "device_index": 0,
                               "name_contains": "cutoff", "limit": 5,
                               "include_racks": True}


def test_tool_returns_the_payload_as_json(conn):
    conn.response = {"device": {"parameters": [{"name": "Volume", "display": "0.0 dB"}]}}
    out = json.loads(call(server.get_device_parameters, None, 0, 0))
    assert out["device"]["parameters"][0]["display"] == "0.0 dB"


def test_tool_rejects_a_negative_limit_without_talking_to_live(conn):
    out = call(server.get_device_parameters, None, 0, 0, limit=-1)
    assert out.startswith("Error getting device parameters:")
    assert conn.sent == []


def test_tool_requires_the_new_capability_only_for_new_arguments(conn, monkeypatch):
    import MCP_Server.script_handshake as sh
    asked = []
    monkeypatch.setattr(sh, "require_capability",
                        lambda name: asked.append(name) or "missing " + name)
    # default call keeps working against an old Remote Script
    call(server.get_device_parameters, None, 0, 0)
    assert asked == [] and len(conn.sent) == 1
    # a filter needs the new script
    assert call(server.get_device_parameters, None, 0, 0,
                name_contains="x") == "missing get_device_parameters_v2"
    assert len(conn.sent) == 1


def test_tool_reports_errors_as_text(conn):
    conn.raise_exc = Exception("Device index out of range")
    out = call(server.get_device_parameters, None, 0, 9)
    assert out.startswith("Error getting device parameters:")


def test_tool_schema_exposes_the_new_optional_arguments():
    tools = asyncio.run(server.mcp.list_tools())
    schema = next(t for t in tools if t.name == "get_device_parameters").inputSchema
    assert set(schema["required"]) == {"track_index", "device_index"}
    for name in ("name_contains", "limit", "include_racks"):
        assert name in schema["properties"]
    assert schema["properties"]["include_racks"]["default"] is False
