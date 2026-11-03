# NeoKeys on the Surface, with FP10 Lights

[NeoKeys](https://github.com/ArtinSHF/NeoKeys) (falling notes, practice mode, MIDI files) runs on the Surface
that sits on the FP-10. With the piano and the FP10 Lights board both plugged into the Surface (move the USB
cables over from the Push), the strip follows the lesson:

| Strip | When |
|---|---|
| Amber hint, dim to full (ch 2) | Your next notes, ~1.2 s ahead; full while practice mode waits for them, and while the demo plays them in Normal mode |
| Green flash (ch 3) | Practice mode credits a note |
| Red flash (ch 4) | A wrong note while practice mode waits |
| Blue (ch 1) | Whatever you play, echoed from the piano, so split and sparks work as on the Push |

The hand buttons choose whose notes are hinted (Left / Right / Both). The song itself still goes to the piano on
channel 1, so Normal mode plays it through the FP-10's speakers; switch on NeoKeys' "Mute Web Audio Synth" to
hear only the piano.

## Run it

On the Surface, once:

```sh
git clone --recursive https://github.com/donbing/ableton-mcp.git
```

(or, in an existing clone, `git submodule update --init`). Then double-click `tablet\NeoKeys.cmd`: it serves
NeoKeys on `http://localhost:8765` and opens the browser. Use Chrome or Edge, press Start and allow MIDI. The
badge at the bottom left says whether the strip was found. Close the window to stop it.

NeoKeys loads Tone.js, its MIDI libraries and the piano samples from the web, so the Surface needs internet.

## With the cables on the Push

Leave the piano and the board on the Push and start its MIDI hub (by hand for now; it runs until you stop it):

```sh
ssh push3 /data/uv/tools/ableton-mcp/bin/python -m MCP_Server.midi_hub
```

When Start is pressed, the bridge connects to `ws://push.local:8766` over Wi-Fi. The piano's notes and pedal reach
NeoKeys as if it were plugged in, and the strip's hints and flashes go back the same way, while Live keeps playing
the piano too. The badge says "FP10 Lights on the Push". Add `?hub=ws://host:port` to the page's address for
another hub, or `?hub=off` to use only Web MIDI. Starting the hub makes Live rescan its MIDI ports once, so don't
hold a note just then. The hub's protocol is in `MCP_Server/midi_hub.py`.

## How it fits together

- `neokeys/` is a git submodule of upstream NeoKeys, never edited. Update it with
  `git submodule update --remote tablet/neokeys`, then commit the new pointer.
- `fp10-bridge.js` adds the strip. It wraps a few of NeoKeys' global functions (`initMIDI`, `awardHit`,
  `awardMiss`, the `sendHardware*` helpers) and reads its `state` each frame for the hints. If an update renames
  any of them, the badge turns red and names what's missing, and NeoKeys runs as before without the strip.
- `serve.ps1` (Windows PowerShell, nothing to install) serves `neokeys/index.html` with the bridge added and
  NeoKeys' Cloudflare analytics beacon left out. Chrome only allows Web MIDI on secure pages, and `localhost`
  counts as one.

The strip's MIDI protocol is in `firmware/fp10_lights/README.md`.

## Licence

NeoKeys is © ArtinSHF, under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): free for
non-commercial use with credit. It isn't copied into this repo, only referenced as a submodule; the files next to
this README are part of ableton-mcp.
