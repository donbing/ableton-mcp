# Rally: a ball across the whole keyboard on FP10 Lights

A simpler rhythm game than Duel. A ball of light crosses the whole strip in one bar and lands on the beat. When it
reaches an end, play any key in that end's octave as it lands to send it back: left hand at the bass end, right
hand at the treble end. Each return adds 4 BPM; a miss flashes that end red and serves again from there at the
start tempo. There's nothing to remember, only the beat to keep.

## Run it

- **In PianoDeck on the Surface (cables on the Push):** open **🏓 Rally** (`http://moo:8484`). Like Duel, it uses the
  Push's MIDI hub through PianoDeck's `/hub`: the FP-10 in, FP10 Lights out, the Push's pads ignored, and notes
  stamped earlier by half the Wi-Fi round trip.
- **On the Surface with both cables plugged in:** double-click `tablet\Rally.cmd` (Web MIDI on
  `http://localhost:8765/rally/`).
- **Anywhere else:** serve `tablet/` over HTTP (Rally imports Duel's hub, layout and sound from `../duel/src/`)
  and open `rally/`. Tap the end boxes, or press Z (bass end), M (treble end) or Space (whichever end the ball is
  heading for).

Any piano key starts a game, serving away from the end nearer that key. The click needs one tap on the page
first, because browsers start sound only after a tap.

## The rules

| | Default | Setting |
|---|---|---|
| Start tempo | 80 BPM | yes |
| Faster per return | 4 BPM, up to 160 | yes |
| A return counts within | ±150 ms of landing (plus 60 ms for late Wi-Fi notes) | ±100 / 150 / 220 ms |
| The end zones | the strip's lowest and highest 12 keys (F0–E1 and E5–D#6 at the default calibration) | |
| A crossing | 4 beats; serves count in for 4 | |

A return starts the next crossing on the landing beat, not when the key went down, so the pulse never drifts.

## On the strip

| | FP10 Lights |
|---|---|
| The ball | ch 1 blue, a key at a time; the firmware's 450 ms fade draws its tail |
| The end it's heading for | ch 2 amber, dim, brightening over the last beat |
| A return | ch 3 green flash on the key you hit |
| A miss | ch 4 red flash over that end's octave |

While a game runs the board's layers are set to 25 (CC114: no sparks, no violet left hand), re-sent every minute,
and put back to 31 when it stops or the page goes.

## Files

`src/rally.js` is the game (no DOM), `src/strip.js` turns it into notes for the board, `src/app.js` is the page.
`node --test` in this folder runs the tests.
