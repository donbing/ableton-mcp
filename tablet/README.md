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

Leave the piano and the board on the Push. Its MIDI hub (`MCP_Server/midi_hub.py`) starts with Live: the AbletonMCP
Remote Script (1.10.27 on) starts it and starts it again within ~10 s if it stops. Each start makes Live rescan its
MIDI ports once, so a note held right then may hang. To turn it off, create `/data/.ableton-mcp/midi_hub.off` on
the Push; to run it by hand instead, `ssh push3 /data/uv/tools/ableton-mcp/bin/python -m MCP_Server.midi_hub`. Its
log is `/data/.ableton-mcp/midi_hub.log`.

When Start is pressed, the bridge connects to `ws://push.local:8766` over Wi-Fi. The piano's notes and pedal reach
NeoKeys as if it were plugged in, and the strip's hints and flashes go back the same way, while Live keeps playing
the piano too. The badge says "FP10 Lights on the Push". Add `?hub=ws://host:port` to the page's address for
another hub, or `?hub=off` to use only Web MIDI. The hub's protocol is in `MCP_Server/midi_hub.py`.

## Only NeoKeys' lights

The strip's own effects (your playing in blue, violet below the split, sparks) sit on top of NeoKeys' hints and
can be confusing. So while NeoKeys is in view the strip shows just its hints and flashes, plus whichever extras you
switch on in settings under **Display → Lights**: show my playing, sparks, left-hand colour (all off to start
with). Leave NeoKeys and the strip is back to normal. This uses the board's layers (CC114, not saved on the
board, see `firmware/fp10_lights/README.md`), whichever way the strip is connected, so it also covers Live's
lights track echoing the piano. The strip's saved effects themselves are set in PianoDeck's 💡 Lights app.

## Claude me lessons

The **🎓** button in the top bar (next to ⚙) opens the Lessons drawer on the right, which turns the loaded song
into short practice lessons. Load a song (Built-in, Recent or a .mid file), then press **✨ Claude me** there, or
**🎓 Claude me** on the end-of-song screen. Claude plans 3-12 lessons,
for example: the tune of the first phrase in the right hand at 60%, its chords as held left-hand blocks, both
together, then the whole song. Click a lesson to load it in practice mode with its hand and tempo set; the strip
hints and flashes as usual. At the end the screen says whether it passed (accuracy and wrong notes against the
lesson's limits) and offers the next lesson, the same one 10% slower, or one hand at a time. **Quick plan** makes a
plan without Claude.

Each lesson is built in the browser from the song's own notes: the bars it names, as written, the right hand's
top line, or one held triad per chord change. Its tempo is written into the lesson file, so the Tempo slider goes
back to 1x. Plans and every run (accuracy, wrong notes, notes per bar) stay in the browser; 📋 downloads them
as JSON, and the next Claude me for that song sends the recent runs so the new plan can go back over weak bars.

Claude needs an API key where `serve.ps1` runs (the Surface), once:

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

then start NeoKeys again. The page never sees the key: it sends `serve.ps1` a summary of the song (key, chords per
half bar, sections, hand ranges, notes per bar; no notes), and `serve.ps1` asks the Claude API
(`claude-opus-5-5`, set `CLAUDE_ME_MODEL` for another) and passes back the plan. Only NeoKeys as served by
`serve.ps1` can ask. A plan takes a few seconds to a minute, and the server answers nothing else meanwhile.

Limits: the analysis guesses the key from the notes when the file's key signature disagrees, names chords from
the key's own chords (plus secondary dominants), and finds repeated phrases only when they repeat exactly (on a
fine grid), so performed classical MIDI files often show every phrase as new. A tempo change inside the song is
ignored (lessons use the first tempo). Practice mode checks which notes you play, not how long you hold them.

## How it fits together

- `neokeys/` is a git submodule of upstream NeoKeys, never edited. Update it with
  `git submodule update --remote tablet/neokeys`, then commit the new pointer.
- `fp10-bridge.js` adds the strip. It wraps a few of NeoKeys' global functions (`initMIDI`, `awardHit`,
  `awardMiss`, the `sendHardware*` helpers) and reads its `state` each frame for the hints. If an update renames
  any of them, the badge turns red and names what's missing, and NeoKeys runs as before without the strip.
- `claude-me.js` adds the Lessons drawer the same way: it wraps `loadMidiObject`, `awardHit`/`awardMiss`,
  `restartCurrentSong` and `showVictoryOverlay`, and uses NeoKeys' `Midi` and `MidiWriter` plus tonal.js (loaded
  by `serve.ps1`). If any is missing it logs a warning and the 🎓 button doesn't appear.
  `claude-me-plan.schema.json` is the plan format Claude must answer in.
- `lights-layers.js` adds the Lights switches and sends the board's layers through `window.fp10Lights.send`,
  which `fp10-bridge.js` provides (Web MIDI or the hub, whichever has the strip).
- `panel-folds.js` folds the settings panel into Play (open), Sound, Display and Advanced. It only moves the
  panel's existing headings and controls into folding sections, so their ids and handlers are untouched; a
  heading it doesn't know goes into Advanced. Each section remembers whether it was left open.
- `serve.ps1` (Windows PowerShell, nothing to install) serves `neokeys/index.html` with the bridge and the
  lessons and folds added and NeoKeys' Cloudflare analytics beacon left out, plus the `/api/claude-me/` endpoints. Chrome
  only allows Web MIDI on secure pages, and `localhost` counts as one.

The strip's MIDI protocol is in `firmware/fp10_lights/README.md`.

## Duel

`duel/` is a call-and-response game made for the strip: the caller plays a phrase an octave up, you answer
it on the beat, and each rally won speeds it up. Same cables; double-click `tablet\Duel.cmd` (it opens
`http://localhost:8765/duel/`). See `duel/README.md`. With the cables on the Push it's also in PianoDeck (☄️ Duel), through
the hub.

## Rally

`rally/` is a simpler rhythm game: a ball of light crosses the whole keyboard in a bar, and you send it back
with any key in the end octave it lands in, on the beat. Each return is a little faster. Double-click
`tablet\Rally.cmd` (`http://localhost:8765/rally/`), or open 🏓 Rally in PianoDeck. It uses Duel's hub, layout
and sound modules from `duel/src/`. See `rally/README.md`.

## Licence

NeoKeys is © ArtinSHF, under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): free for
non-commercial use with credit. It isn't copied into this repo, only referenced as a submodule; the files next to
this README are part of ableton-mcp.
