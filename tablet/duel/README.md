# Duel: call and response on FP10 Lights

A spike of a 1D rhythm game for the LED strip over the FP-10. The strip's only axis is pitch, so time and order
are carried by how the lights behave: brightness tiers, halos that close in on the beat, comets timed to the
bar. A caller plays a phrase an octave up; you answer it in your octave, in time; each rally you win adds
5 BPM and a note.

## Run it

- **On the Surface, with the piano and the strip:** plug both into the Surface (as for NeoKeys), double-click
  `tablet\Duel.cmd`, press Start and allow MIDI. It serves `http://localhost:8765/duel/` (Chrome only allows
  Web MIDI on secure pages, and `localhost` counts as one). The status line under the keys says what it found.
- **On the Surface through PianoDeck, cables on the Push:** open **☄️ Duel** in PianoDeck (`http://moo:8484`).
  That page isn't a secure context, so instead of Web MIDI Duel uses the Push's MIDI hub through PianoDeck's
  `/hub` (`src/hub.js`, the same protocol as `tablet/fp10-bridge.js`): the FP-10 in, FP10 Lights out, the Push's
  own pads ignored. Wi-Fi delays each note, so it's stamped earlier by half the measured ping round trip (at most
  150 ms); the status line shows the lag allowed for. The call sounds in the browser (the hub doesn't play the
  piano). `?hub=ws://host:port` picks another hub, `?hub=off` never uses one.
- While a game runs Duel sets the board's layers (CC114) to 25: your playing, hints and flashes, without sparks
  or the violet left hand, which would recolour its halos and comets. It re-sends that every minute and puts all
  effects back (31) when the game stops or the page goes.
- **Anywhere else:** serve this folder over HTTP (`python3 -m http.server` in `tablet/duel`) and open it. Without
  MIDI, play on the on-screen keys or the computer keys `A W S E D F T G Y H U J` (C3 to B3).
- On load it runs a silent demo with the computer answering. **Autoplay** keeps the computer answering in a
  real game, so you can watch the strip without playing.

## A round

At 90 BPM in 4/4, with the defaults (`DEFAULTS` in `src/game.js`):

| Phase | Beats | What happens |
|---|---|---|
| `COUNT_IN` | 4 (first round only) | End pulses count you in; a comet runs from the bass end to the caller's first note |
| `CALL_PLAYBACK` | 4 | The phrase sounds in the caller's zone (C4-B4) and lights there in magenta, echoed in cyan on your keys (C3-B3) as it plays |
| `COMET_TRANSITION` | 2 | A comet runs from the caller's last note to your first and lands on beat 1 of the response; the whole phrase fades in as breadcrumbs |
| `PLAYER_RESPONSE` | 4 | Play it back. Active note cyan, next amber, the rest dim blue; each note's halo closes in from ±3 keys over the beat before it |
| `ROUND_ESCALATION` | 2 | Your zone washes green or red; a comet carries the turn back. A pass adds 5 BPM and a note from the next call; a fail repeats the phrase |

The ends of the strip pulse on every beat, brighter on each phase's first beat. A hit is the right key within
±80 ms of its beat. The score is hits ÷ (notes + wrong or early presses), and 75% passes.

## How it's built

Everything that decides or draws is plain ES modules with no DOM, tested with `node --test` (run it in this
folder; Node 18+, nothing to install):

| File | Does |
|---|---|
| `src/clock.js` | One musical clock, beats ↔ `performance.now()` ms; tempo changes apply from a beat, so handoffs never jump |
| `src/phrase.js` | Seeded pentatonic phrases on an eighth-note grid, first note on the downbeat |
| `src/evaluator.js` | Scores NoteOns (pitch and timestamp) against the phrase: hit, miss, wrong, early |
| `src/game.js` | The state machine above; emits events and a plain `view(now)` for renderers |
| `src/layout.js` | Key → LED, copied from the firmware's `keyPos()` / `buildKeyMap()` |
| `src/render.js` | View → one linear-light RGB value per LED, for any frame time (the "ideal" strip) |
| `src/fp10.js` | View → the MIDI notes today's firmware understands, sending only changes; and a simulator of the firmware |
| `src/audio.js`, `src/app.js` | Browser only: a plucked-string call and click, Web MIDI, keys, the canvas |

Input timestamps are the events' own (`MIDIMessageEvent.timeStamp`, pointer and key events), and the call is
scheduled against `AudioContext.getOutputTimestamp()`, so sound and light land together despite output latency.
"The piano (MIDI)" sends the call to the FP-10 instead, with Web MIDI timestamps.

## The two strips

The page draws two strips over the same keys. The top one is the pixel renderer, the design as briefed. The
bottom one is what FP10 Lights shows today: `fp10.js` turns the same view into notes, and the simulator draws
what the firmware does with them. The board gets exactly those notes when "Light FP10 Lights" is on.

| Briefed | On today's firmware |
|---|---|
| Active / next / queue in cyan / amber / dim blue | Amber at velocity 127 / 45 / 10 (ch 2) |
| Caller magenta, echo cyan | Caller amber (ch 2), echo blue (ch 1) |
| Halos gliding in from ±3 keys | Blue (ch 1), stepping ±3 → ±2 → ±1 keys, a third of a beat each |
| Comets with a tail | Blue (ch 1), a key at a time; the firmware's 450 ms fade-out is the tail |
| End pulses | Blue (ch 1) on the strip's lowest and highest keys |
| Hit / wrong / missed, result wash | Green (ch 3) / red (ch 4) flashes |

## What the spike found

- **The game works on today's firmware without a reflash.** The breadcrumbs, the call and its echo, and the
  flashes all come across. Colour is the loss: amber and blue stand in for cyan, amber and magenta.
- **Halos and comets smear on today's firmware.** Every channel 1 note fades for 450 ms after its note-off, so a
  halo stepping every third of a beat trails 2-3 steps behind at 120 BPM and turns into a closing smudge by
  ~150 BPM. If sparks are on (`board.sh sparks`), every step throws sparks. Turn them off for Duel.
- **The strip is coarse at key level.** There are 144 LEDs for about 71 keys (MIDI 29-99 at the default
  calibration), so a ±3-key halo has about 6 LEDs per side to travel. The pixel renderer splits light between
  neighbouring LEDs so the halo glides instead of hopping. The strip could do that too, but only if it took
  pixels.
- **Two halos at once is busy.** With eighth notes the next note's halo starts before the active one lands. It's
  drawn at half brightness, but at 5-6 notes the zone gets crowded. Worth trying: halos only for the active note.
- **Late-delivered input.** A frame that stalls can close a note's window before a NoteOn with an earlier
  timestamp is judged, which shows up as a false miss. Windows now close 100 ms late (`inputGraceMs`). This
  turned up in testing.
- **Next step for the hardware: a frame mode in the firmware.** For example, SysEx
  `F0 7D 46 4C <first LED> <count> <r g b, 7 bits each…> F7` (7D is the non-commercial ID). 144 LEDs is 432 data
  bytes a frame, about 27 KB/s at 60 fps, well within USB MIDI. The board would keep its gamma and power cap,
  and go back to note mode if frames stop for ~250 ms. Chrome asks separately for SysEx permission
  (`requestMIDIAccess({ sysex: true })`). `renderPixels()` already produces the frames.

## Not tried yet

The real Surface, piano and strip. `serve.ps1`'s `/duel/` route and `Duel.cmd` haven't been run, because no
PowerShell was available where they were written. Everything else has been run in headless Chromium: the demo,
autoplay rounds, phone width, and light and dark themes.
