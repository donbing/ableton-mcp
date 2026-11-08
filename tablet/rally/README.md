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
| A return counts | from 150 ms before landing to 300 ms after (plus 60 ms for late Wi-Fi notes) | tight 100/150, easy 220/400 |
| The end zones | the strip's lowest and highest 12 keys (F0–E1 and E5–D#6 at the default calibration) | |
| A crossing | 4 beats; serves count in for 4 | |

Late is more forgiving than early: reacting to the light lands about 200-300 ms after it, and that should count
while you find the beat. A key in the last beat before the window flashes red ("Too early"); one before that is
ignored. A return starts the next crossing on the landing beat, not when the key went down, so the pulse never
drifts.

## On the strip

| | FP10 Lights |
|---|---|
| The ball | ch 1 blue, a key at a time; the firmware's 450 ms fade draws its tail |
| The end it's heading for | ch 2 amber, dim, brightening in 4 steps over the last beat |
| A return | ch 3 green flash on the key you hit |
| A miss | ch 4 red flash over that end's octave |
| Too early | ch 4 red flash on the key |

Through the hub the strip is drawn ahead by half the Wi-Fi round trip (~45 ms measured), so the ball lands on
the real strip on the beat. The amber steps rather than ramps: a ramp re-sent 12 notes every frame, over 600
messages a second, which the Wi-Fi to the Push can't carry smoothly.

While a game runs the board's layers are set to 25 (CC114: no sparks, no violet left hand), re-sent every minute,
and put back to 31 when it stops or the page goes.

## Files

`src/rally.js` is the game (no DOM), `src/strip.js` turns it into notes for the board, `src/app.js` is the page.
`node --test` in this folder runs the tests.
