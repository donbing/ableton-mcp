# Doctor: when Live does not respond, and the socket fallback

## Facts about this setup

- Push 3 standalone, Live 12.4.15, host `push.local`, user `ableton`, key `~/.ssh/push3_rsa` (the `push3` entry in `~/.ssh/config`).
- MCP entry in `~/.claude.json`: stdio `ssh -T -i <key> -o BatchMode=yes ableton@push.local /data/uv/ableton-mcp.sh`.
- Server: uv tool at `/data/uv/tools/ableton-mcp`; Remote Script in `/data/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`; Live's command socket is `127.0.0.1:9877` on the Push.
- Telemetry is off (`ABLETON_MCP_DISABLE_TELEMETRY=1` in the launcher); dataset consent is "denied" in `/data/.ableton-mcp/consent.json`. Do not change either.
- Sets are in `/data/Music/Ableton/Sets/`; the Push autosaves `[Autosave]` copies there.

## Checks, in order

1. `ssh -T -o BatchMode=yes -o ConnectTimeout=10 push3 echo ok` - fails: Push off, asleep or not on the network.
2. `get_remote_script_info` - "Connection closed" once is normal after a restart (it reconnects); the next call should answer. It should report `up_to_date: true`; otherwise `script_version` (on the Push) and `expected_version` (the server) differ and the Remote Script needs reinstalling.
3. Tool list stale (no `record_into_slot`): the session loaded an old list. A new session fixes it; until then use the socket fallback.
4. Live restarted: it opens a new empty set. The user must open their set on the Push (no open API).

## Restarting Live remotely

Ask the user first, every time: a restart stops playback, closes the open set and drops anything unsaved. Only
restart after they said yes.

`kill -TERM <Live pid>` (pid from `pgrep -f "^/opt/push3/Live"`) asks Live to quit; the launcher restarts it unless `/data/settings/.reboot` exists. Live then shows dialogs that block the quit; read them with `get_live_status` (`dialog_message`) and answer with `press_dialog_button`:
- "Save changes to "<set>" before closing?" - buttons 0 = Save, 1 = Don't save, 2 = Cancel (measured 2026-10-26). Press 1 only when the user said the set can be discarded.
- "Would you like to delete the temporary files in ... Temp Project?" - appears after discarding an unsaved set with recordings. Button 1 = No (keeps the files; measured 2026-10-26, Live then restarts in ~4 s). Never press the delete option yourself; back the folder up first if unsure.

## Socket fallback (any command, without the MCP tool list)

Run on the Push over SSH; commands and params are the Remote Script's (same names as the tools, minus `user_prompt`):

```bash
ssh -T -o BatchMode=yes push3 'python3 - <<EOF
import socket, json
s = socket.create_connection(("127.0.0.1", 9877), 30)
def q(t, p={}):
    s.sendall(json.dumps({"type": t, "params": p}).encode()); buf = b""
    while True:
        buf += s.recv(65536)
        try: return json.loads(buf)
        except ValueError: pass
print(q("get_tracks_overview"))
EOF'
```

A reply has `status` ("success" or "error"), `result`, and `message` on errors - print the whole reply, not only `result`. For anything longer than a few commands, write a script to the scratchpad, `scp` it to `/data/uv/backups/`, and run it; put cleanup (stop, disarm, monitoring back) in a `finally`. Never `import` such a script to reuse a function: importing runs it.
