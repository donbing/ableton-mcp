# ableton-mcp (Push 3 fork)

A personal fork of ableton-mcp aimed at the user's Ableton Push 3 in standalone mode (Live 12.4.6 Intro on
AbletonOS). The MCP server and the Remote Script both run on the Push.

## Reaching the Push

- SSH: `ssh push3` (user `ableton`, key `~/.ssh/push3_rsa`, set up in `~/.ssh/config`). Works from Git Bash and
  PowerShell. Add `-T -o BatchMode=yes -o ConnectTimeout=10` for scripted use. Don't try other keys or users; if
  `ssh push3` fails, the Push is off, asleep or off the network: tell the user.
- Copy files with `scp <file> push3:<path>`.
- MCP: the `ableton-push` server runs `ssh ... ableton@push.local /data/uv/ableton-mcp.sh` (entry in
  `~/.claude.json`). Prefer the MCP tools for anything inside Live.

## Paths on the Push

- Remote Script: `/data/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`
- APICapture (LiveAPI's capture surface): `.../Remote Scripts/APICapture/`, output under `/data/apicapture/probe/`
- Sets: `/data/Music/Ableton/Sets/` (the Push autosaves `[Autosave]` copies there)
- MCP server: uv tool at `/data/uv/tools/ableton-mcp`; Live's command socket is `127.0.0.1:9877` on the Push

## Branches

- `main` on this fork is what the Push runs. Start every branch from the current `main`, deploy it to the Push,
  then fast-forward `main` to it. Never build on an older `main` or on `upstream`.
- CI fails a branch that isn't based on the current `main`, lowers `SCRIPT_VERSION`, or lets the bundled Remote
  Script drift from `AbletonMCP_Remote_Script/__init__.py`.
- Deploying the server: build the wheel locally (`pip wheel --no-deps -w dist .`), keep the old one in
  `/data/uv/backups/` as `ableton_mcp-1.4.5-before-<feature>.whl`, copy the new one over
  `/data/uv/backups/ableton_mcp-1.4.5-py3-none-any.whl`, then on the Push run `/data/uv/uv tool install --force
  --reinstall --offline --python /usr/bin/python3.10 <wheel>` with `UV_TOOL_DIR=/data/uv/tools
  UV_TOOL_BIN_DIR=/data/uv/bin UV_CACHE_DIR=/data/uv/cache`.

## Rules

- Live's API can't save or open a set: ask the user to do it on the Push, and never claim work is saved.
- Leave telemetry off and dataset consent "denied" (`/data/.ableton-mcp/consent.json`); don't change Push settings.
- Restarting Live, changing the open set or loading devices interrupts the user: ask first.
- Don't push or open PRs until the user says so.

## Skills

- `push3-live-api` (`.claude/skills/`): Live's Python API as captured on the Push; for Remote Script work.
- `ableton-music` (personal): making music through the MCP tools; its `doctor.md` covers connection trouble.
