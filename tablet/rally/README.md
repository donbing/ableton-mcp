# Rally: a ball across the whole keyboard on FP10 Lights

A simpler rhythm game than Duel. A ball of light crosses the strip in one bar and lands on the beat as it reaches
the far end's octave (its inner edge, nearest the middle). Play any key in that octave as the ball touches it to
send it back; missed, it runs on into the octave: left hand at the bass end, right
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

## Notes or octave

**Notes** (the default) is the musical one. The ball lands on one key, glowing amber: play that key on the beat as
it lands. The left hand plays a bass line, A F C G, one note per crossing, and the right a tune over it, E F E D C
A G B; each return sounds the chord in the browser (Am, F, C, G, two crossings each). A key near the target that
isn't it flashes red as a wrong note, and the right one still counts if it's in time. A return counts from 150 ms
before landing to 0.6 of a beat after (at least 300 ms); a miss starts the tune again. The tunes are in
`src/songs.js`.

**Octave** is the first version: any key in the end's octave, while the ball is in it. Pick it under Targets in
the settings.

## The rules (Octave)

| | Default | Setting |
|---|---|---|
| Start tempo | 80 BPM | yes |
| Faster per return | 4 BPM, up to 160 | yes |
| A return counts | from 150 ms before the ball reaches the octave until it reaches the end of the strip (plus 60 ms for late Wi-Fi notes): while the light is in the octave | tight 100, easy 220 ms early |
| The end zones | the strip's lowest and highest 12 keys (F0–E1 and E5–D#6 at the default calibration) | |
| A crossing | 4 beats, from one octave's inner edge to the other's; serves count in for 4 | |

Late is more forgiving than early: whenever the light is in your octave, a key there sends it back, from where it
is. Reacting to the light lands 200-300 ms after the beat, and that should count while you find the beat. A key in
the last beat before the window flashes red ("Too early"); one before that is ignored. The next crossing still lands
on the beat a bar after the last landing, whenever the key went down, so the pulse never drifts.

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
