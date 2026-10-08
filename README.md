<div align="center">

# Ableton MCP

**Connect Ableton Live to Claude AI**

Prompt-assisted music production, end-to-end track creation, and Live session and arrangement manipulation — driven by AI.

[![PyPI Version](https://img.shields.io/pypi/v/ableton-mcp?color=blue)](https://pypi.org/project/ableton-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/JK4hNKGprW)

[**Setup Video**](https://youtu.be/iJWJqyVuPS8) · [**Discord**](https://discord.gg/JK4hNKGprW) · [**Issues**](https://github.com/ahujasid/ableton-mcp/issues)

</div>

---

## Quickstart

Three steps: install `uv`, point your MCP client at the server, install the Ableton Remote Script.

**1. Install uv**

```bash
# macOS
brew install uv
```

Otherwise, install from [uv's official website](https://docs.astral.sh/uv/getting-started/installation/).

> **Warning:** Do not proceed before installing uv.

**2. Add the MCP server to your client**

<details open>
<summary><b>Claude Desktop</b> — Settings → Developer → Edit Config</summary>

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```
</details>

<details>
<summary><b>Cursor</b> — Settings → MCP</summary>

Paste this as a command:

```
uvx ableton-mcp
```
</details>

> **Warning:** Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both.

**3. Install the Ableton Remote Script**

```bash
uvx --from ableton-mcp ableton-mcp-install-script
uvx --from ableton-mcp ableton-mcp-install-script --list-targets   # preview target folders first
```

**4. Connect**

1. Launch Ableton Live
2. Go to **Settings/Preferences → Link, Tempo & MIDI**
3. In the **Control Surface** dropdown, select **AbletonMCP**
4. Set **Input** and **Output** to **None**

That's it — ask Claude to build something.

---

## Table of Contents

- [Quickstart](#quickstart)
- [Features](#features)
- [Components](#components)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Claude for Desktop Integration](#claude-for-desktop-integration)
  - [Cursor Integration](#cursor-integration)
  - [Installing the Ableton Remote Script](#installing-the-ableton-remote-script)
- [Usage](#usage)
  - [Starting the Connection](#starting-the-connection)
  - [Using with Claude](#using-with-claude)
  - [Capabilities](#capabilities)
  - [Example Commands](#example-commands)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)
- [Limitations & Security Considerations](#limitations--security-considerations)
- [Telemetry](#telemetry)
- [Join the Community](#join-the-community)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)

---

## Features

| | |
|---|---|
| **Two-way communication** | Connect Claude AI to Ableton Live through a socket-based server |
| **Track manipulation** | Create, modify, and manipulate MIDI and audio tracks |
| **Instrument and effect selection** | Claude can access and load the right instruments, effects and sounds from Ableton's library |
| **Clip creation** | Create and edit MIDI clips with notes |
| **Arrangement view composition** | Build full songs autonomously in Arrangement View, including sections like intro, buildup, drop, breakdown, and outro |
| **Session control** | Start and stop playback, fire clips, and control transport across Session View and Arrangement View |
| **Anonymous telemetry** | Usage tracking to help improve the tool (can be disabled) |

## Components

The system consists of two main components:

1. **Ableton Remote Script** (`Ableton_Remote_Script/__init__.py`) — a MIDI Remote Script for Ableton Live that creates a socket server to receive and execute commands
2. **MCP Server** (`server.py`) — a Python server that implements the Model Context Protocol and connects to the Ableton Remote Script

---

## Installation

### Prerequisites

- **Ableton Live** 10 or newer
- **Python** 3.8 or newer
- **uv** package manager

If you're on Mac, please install uv as:

```
brew install uv
```

Otherwise, install from [uv's official website](https://docs.astral.sh/uv/getting-started/installation/)

> **Warning:** Do not proceed before installing uv.

### Claude for Desktop Integration

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

Go to **Claude → Settings → Developer → Edit Config → `claude_desktop_config.json`** to include the following:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```

### Cursor Integration

Run ableton-mcp without installing it permanently through uvx. Go to **Cursor Settings → MCP** and paste this as a command:

```
uvx ableton-mcp
```

> **Warning:** Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both.

### Claude Code Integration

In the terminal, run:

```
claude mcp add AbletonMCP uvx ableton-mcp
```

### Installing the Ableton Remote Script

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

Install the Remote Script with:

```bash
uvx --from ableton-mcp ableton-mcp-install-script
uvx --from ableton-mcp ableton-mcp-install-script --list-targets   # preview target folders first
```

> If you installed the package with `pip` or `pipx`, the command is on your PATH directly — just run `ableton-mcp-install-script`.

This copies the matching Remote Script into your Ableton **User Library**'s `Remote Scripts` folder — the location Live (10.1.13+) scans for third-party control surface scripts. The installer reads the User Library location from Live's `Library.cfg`, falling back to the default (`~/Music/Ableton/User Library` on macOS, `Documents\Ableton\User Library` on Windows). If a different version of the script is already there, the existing file is backed up to `__init__.py.bak` before being replaced.

If your User Library lives somewhere non-standard and isn't detected, point the installer at it directly:

```bash
uvx --from ableton-mcp ableton-mcp-install-script --target "/path/to/User Library/Remote Scripts"
```

> The legacy `Preferences/User Remote Scripts` folder (used for instant-mapping configs, not Python control surfaces) is no longer targeted by default; pass `--legacy` if you need it for an old Live version.

Then **restart Ableton** (or re-select the AbletonMCP control surface) so Live loads it. Re-run the command after upgrading the package — the server logs a warning when the loaded script version doesn't match what it expects.

> **Note:** The server does **not** install the script on startup. Writing into Ableton's preferences directory is an explicit action, not a side effect of launching a server.

**First-time Ableton setup:**

1. Run `uvx --from ableton-mcp ableton-mcp-install-script`
2. Launch Ableton Live
3. Go to **Settings/Preferences → Link, Tempo & MIDI**
4. In the **Control Surface** dropdown, select **AbletonMCP**
5. Set **Input** and **Output** to **None**

<details>
<summary><b>Manual fallback locations (User Library → Remote Scripts)</b></summary>

- **macOS:** `~/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`
- **Windows:** `C:\Users\[Username]\Documents\Ableton\User Library\Remote Scripts\AbletonMCP\`

If you've moved your User Library, use its actual location (shown in Live under **Preferences → Library → Location of User Library**), and create the `Remote Scripts` folder inside it if it doesn't exist yet.
</details>

The MCP server and Remote Script share a version handshake (`get_remote_script_info`). If they diverge, newer tools degrade gracefully until Live is restarted.

---

## Usage

### Starting the Connection

1. Ensure the Ableton Remote Script is loaded in Ableton Live
2. Make sure the MCP server is configured in Claude Desktop or Cursor
3. The connection should be established automatically when you interact with Claude

### Using with Claude

Once the config file has been set on Claude, and the remote script is running in Ableton, you will see a hammer icon with tools for the Ableton MCP.

### Capabilities

- Get session and track information
- Create and modify MIDI and audio tracks
- Create full song arrangements from start to finish in Arrangement View
- Create, edit, and trigger clips
- Control playback
- Load instruments and effects from Ableton's browser
- Add notes to MIDI clips
- Change tempo and other session parameters
- Read and set mixer levels — volume, panning and sends
- Mute, solo and arm tracks
- Delete a track, with a preview and name check first
- Measure per-track output levels (peak and mean) over a short window
- Read device parameters with Live's own display strings ("-6.0 dB", "1/8")
- Undo and redo

### Mixer control

`get_mixer`, `set_track_volume`, `set_track_panning` and `set_send` work on
regular tracks, return tracks and the master (`track_type` is `"track"`,
`"return"` or `"master"`).

Levels are set in decibels:

```
set_track_volume(track_index=0, db=-4)
set_send(track_index=0, send_index=0, db=-12)
```

Prefer `db` over the raw `value`. Live's fader position is not proportional to
level — 0.85 is 0 dB and 1.0 is +6 dB — and the taper has no published closed
form, so approximating it drifts away from unity gain. Passing `db` resolves the
exact fader position by bisecting against `DeviceParameter.str_for_value()`,
i.e. asking Live what a position actually reads as. Accuracy is bounded by
Live's own 0.01 dB display resolution. Targets beyond the fader range clamp to
its ends.

`get_mixer` reports each parameter three ways — the raw value, the dB, and the
string Live displays:

```json
{
  "name": "1-Drums",
  "volume": { "value": 0.85, "db": 0.0, "display": "0.0 dB" },
  "panning": { "value": 0.0, "db": null, "display": "C", "pan_percent": 0 },
  "sends": [ { "index": 0, "name": "A Reverb", "db": -12.0, "display": "-12.0 dB" } ]
}
```

Panning has no dB: `db` is always `null` and `pan_percent` is the position parsed
from Live's display (`"50L"` is `-50`, `"25R"` is `25`, `"C"` is `0`). A volume or
send at silence also reports `db: null`; its `display` reads `"-inf dB"`.

### Tool reference (mixer state)

| Tool | What it does |
|---|---|
| `set_track_mute(track_index, mute, track_type="track", expected_name=None)` | Mute or unmute a regular, group or return track. Returns the previous and new value. The master track cannot be muted. |
| `set_track_solo(track_index, solo, track_type="track", expected_name=None)` | Solo or unsolo a regular, group or return track. Returns the previous and new value. The master track cannot be soloed. |
| `set_track_arm(track_index, arm, track_type="track", expected_name=None)` | Arm or disarm a MIDI or audio track. Group, return and master tracks have no arm state and are refused. |

`track_type` is `"track"` (default) or `"return"`. `expected_name` is an optional
guard: the call fails unless the track at `track_index` currently has exactly that
name, which catches a stale index after tracks were added or removed.

### Tool reference (destructive edits)

| Tool | What it does |
|---|---|
| `delete_track(track_index, expected_name, confirm=false)` | Deletes a regular track in two steps. Without `confirm=true` it only returns a preview (name, type, devices, clip counts, group members, and the track list as it would remain). It deletes only when `confirm=true` **and** `expected_name` matches the track's current name. Return and master tracks and the last remaining track are refused. Returns the new track list, because every later track's index shifts down by one. Deletions go into Live's undo history (Cmd/Ctrl+Z). |

### Tool reference (metering)

| Tool | What it does |
|---|---|
| `get_meters(seconds=2.0, hz=20)` | Samples the output meters of every track, return track and the master for `seconds` (max 10) at `hz` samples per second, and returns each one's `peak` and `mean` level. Raw values are Live's own 0..1 meter readings, which are approximately **linear in dB, not linear amplitude** (about 0.01325 per dB, ~0.85 = 0 dBFS). Each entry also has `peak_db_approx` / `mean_db_approx` = `(raw-0.85)/0.01325` (`null` = silence, raw <= 0.03), accurate to about +-1.5 dB inside roughly -37..-7 dB and extrapolated outside it; the response carries a `scale` object saying so. Never use `20*log10(raw)`. Start playback first; meters read 0 when nothing plays. Sampling happens on the Remote Script's client thread, so Live is not blocked. |

Abridged `get_meters` response (a synth track whose fader sits at -30 dB reads about 0.43 raw, which is about -31.7 dB; `20*log10(0.43)` would wrongly say -7.3):

```json
{
  "seconds_requested": 4.4,
  "is_playing": true,
  "tracks": [
    {"index": 0, "name": "1-Synth", "meter_available": true,
     "peak": 0.4301, "peak_db_approx": -31.69,
     "mean": 0.4056, "mean_db_approx": -33.54,
     "peak_left": 0.4301, "peak_right": 0.4288}
  ],
  "scale": {
    "raw": "Live's 0..1 meter reading, approximately linear in dB, NOT linear amplitude",
    "db_approx": "(raw-0.85)/0.01325",
    "calibrated_range_db": [-37, -7],
    "accuracy_db": "about +-1.5 inside the calibrated range; extrapolated outside it (unverified)"
  }
}
```

### Tool reference (device parameters)

| Tool | What it does |
|---|---|
| `get_device_parameters(track_index, device_index, name_contains=None, limit=None, include_racks=false)` | Reads a device's parameters. Every entry now has a `display` string, exactly what Live shows for the value (`"-6.0 dB"`, `"1/8"`, `"Sine"`). `name_contains` (case-insensitive) and `limit` narrow the list; each `index` stays the real index for `set_device_parameter`. Racks are returned as a compact summary (macros plus chain and device names) unless `include_racks=true`, because a full rack read can be hundreds of KB. Other devices are returned as before. |

### Tool reference (undo)

| Tool | What it does |
|---|---|
| `undo()` | Undoes one step of Live's undo history. If there is nothing to undo it does nothing and says so. Live has one history, so this also undoes edits you made by hand. |
| `redo()` | Redoes one undone step. If there is nothing to redo it does nothing and says so. |

### Example Commands

Here are some examples of what you can ask Claude to do:

| Prompt | Demo |
|---|---|
| *"Create an 80s synthwave track"* | [Watch](https://youtu.be/VH9g66e42XA) |
| *"Create a Metro Boomin style hip-hop beat"* | |
| *"Create a full arrangement with an intro, buildup, drop, breakdown, and outro"* | |
| *"Create a new MIDI track with a synth bass instrument"* | |
| *"Add reverb to my drums"* | |
| *"Create a 4-bar MIDI clip with a simple melody"* | |
| *"Get information about the current Ableton session"* | |
| *"Load a 808 drum rack into the selected track"* | |
| *"Add a jazz chord progression to the clip in track 1"* | |
| *"Set the tempo to 120 BPM"* | |
| *"Play the clip in track 2"* | |
| *"Set every track to -4 dB"* | |
| *"Pan the hats 30% left and send them to the reverb at -12 dB"* | |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Connection issues** | Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude |
| **Timeout errors** | Try simplifying your requests or breaking them into smaller steps |
| **Have you tried turning it off and on again?** | If you're still having connection errors, try restarting both Claude and Ableton Live |

## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- **Commands** are sent as JSON objects with a `type` and optional `params`
- **Responses** are JSON objects with a `status` and `result` or `message`

## Limitations & Security Considerations

- Creating complex musical arrangements might need to be broken down into smaller steps
- The tool is designed to work with Ableton's default devices and browser items
- Always save your work before extensive experimentation

---

## Telemetry

There are two tiers, and they have different defaults.

**Anonymous telemetry — on by default.** A random install ID, a per-run session ID, which tools ran, whether they succeeded, and how long they took. This is what counts active users and catches broken tools. It contains none of your content: no prompts, no MIDI, no track or clip names, no device settings.

**Dataset recording — off by default, opt-in.** Everything with your work in it: prompts, MIDI notes, track and clip names, and device settings, which may be published as part of an open dataset used to train music-production models. Nothing here is collected unless you explicitly turn it on.

To see exactly what data each tier collects, see the [Terms & Data Use](TERMS.md).

### Opting in to dataset recording

Either set the environment variable before starting the server:

```bash
export ABLETON_MCP_ENABLE_DATASET=true
```

…or answer the question when your client asks it. On your first tool call you're asked once — as a dialog if your client supports MCP elicitation, otherwise as a message in the chat — and answering yes turns it on from that point. Your answer is stored in `~/.ableton-mcp/consent.json`. Declining, or never answering, records nothing. If you dismiss the dialog without choosing, that isn't treated as an answer and you may be asked again in a later session.

### Opting out of anonymous telemetry

Set one of these before starting the MCP server:

```bash
export ABLETON_MCP_DISABLE_TELEMETRY=true
```

Or use any of these alternatives:

- `DISABLE_TELEMETRY=true`
- `MCP_DISABLE_TELEMETRY=true`

This also disables dataset recording. `ABLETON_MCP_DISABLE_DATASET=true` turns off dataset recording only, and overrides any stored grant.

For Claude Desktop, add the environment variable to your config:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": ["ableton-mcp"],
            "env": {
                "ABLETON_MCP_DISABLE_TELEMETRY": "true"
            }
        }
    }
}
```

---

## Join the Community

Give feedback, get inspired, and build on top of the MCP: [**Discord**](https://discord.gg/JK4hNKGprW)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Ableton. Made by [Siddharth](https://x.com/sidahuj).

---

<div align="center">

**If Ableton MCP is useful to you, consider starring the repo**

</div>
