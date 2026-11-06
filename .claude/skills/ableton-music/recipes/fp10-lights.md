# FP10 Lights: light the piano keys

An SK9822 strip over the middle of the user's Roland FP-10, driven by an ESP32-S3 that shows up on the Push's USB hub
as the MIDI device **FP10 Lights**. It only draws what it is sent; deciding what to light (lessons, right/wrong)
is our job. Firmware and its README: `firmware/fp10_lights/` in the ableton-mcp repo.
Set up and working on the Push 2026-11-01: in Live the piano is **Roland Digital Piano MIDI 1** and the board is
**FP10 Lights MIDI 1**.

## What the strip understands

| Output channel | Meaning | Look |
|---|---|---|
| 1 | Play: what the user is playing | Blue, brightness from velocity, fades ~450 ms after release; ~4 s with sustain (CC64) down |
| 2 | Hint: play this next | Steady amber while the note is held, brightness from velocity (127 = full) |
| 3 | Correct | Green flash, ~400 ms (no note-off needed) |
| 4 | Wrong | Red flash, ~400 ms (no note-off needed) |
| any | CC120 / CC123 (All Sound / All Notes Off) | Clears everything |

Colours add where channels overlap on one key. Channels 5-15 are ignored; channel 16 CC119 switches the board's
Wi-Fi update mode, CC118 calibration mode, CC117 restarts it, CC116 sets the split and CC115 sparks, so never send
those on channel 16 from Live. From the PC, `firmware/fp10_lights/board.sh update|calibrate [off]` and
`board.sh restart` send them over SSH from a hidden port; after `update`, run `build.sh ota` on moo.

Options the user can switch, saved on the board (`board.sh`, from the PC):

- `board.sh split [NOTE|off]`: play notes below NOTE (Live's names, C3 = 60 by default) light violet, a
  left-hand colour; by pitch, not by hand. Hints and flashes keep their colours.
- `board.sh sparks [off]`: each played note throws sparks out along the strip (white-hot, cooling to the note's
  colour, ~0.5 s). Worth suggesting for free play; for a lesson where hints matter, they may distract.

The 1 m strip covers about MIDI notes 29-100 (F0-E5 in Live's names, where 60 = C3); notes outside stay dark. The
firmware runs the strip at 50% brightness and caps it at 250 mA, so lighting many keys only dims them, notes left ringing
by the pedal first and hints last: nothing to manage from here.

## Light the keys as the user plays

Use a separate, empty MIDI track for the lights. A MIDI track with an instrument outputs audio, not MIDI, so the
user's piano sound (the FP-10's own speakers, or a Live instrument track) stays as it is.

1. `get_tracks_overview`: is there already a track named `FP10 Lights`? Then check its routing and stop.
2. `create_midi_track`, then `set_track_name` to `FP10 Lights`. Add no devices.
3. `get_track_routing` on it: find the FP-10 among the input types and FP10 Lights among the output types. Use
   the names exactly as Live lists them.
4. `set_track_routing(direction="input", routing_type=<FP-10's name>, routing_channel=<"All Channels" or "Ch. 1">)`.
5. `set_track_routing(direction="output", routing_type=<FP10 Lights' name>, routing_channel="Ch. 1")`.
6. `set_track_monitoring(state="in")`. No arming needed, and no feedback risk: this track makes no sound.
7. Ask the user to play a few keys and say whether they light, and whether the right keys light.

If FP10 Lights is missing from the output types, find out which of these it is:

- **Not in the input types either:** the Push has no MIDI port for the board. Check over SSH:
  `ssh push3 'cat /proc/asound/cards; dmesg | grep -E "FP10|set config" | tail'`. A `Lights` card should be listed.
  If dmesg says `can't set config #1, error -32`, the Push refused the board as it connected (about one restart
  in three). Since 2026-11-01 the firmware restarts itself 3 s later and is normally back within ~5 s: wait and
  check again. Only if it stays off (LED green, still no card) ask the user to unplug and replug it, or use
  another hub port. `board.sh restart-test N` checks the recovery (README "When the Push refuses the board").
- **The FP-10 missing too:** `lsusb` has no Roland, so the piano is off or unplugged: ask the user.
- **In the input types but not the outputs:** track output is off for that port in the Push's MIDI settings
  (Setup > MIDI). That is a Push setting: tell the user to turn it on, don't change it.

The board's onboard LED is dim green when idle and blinks blue on MIDI.

If the wrong keys light, the mapping is off: it's set on the board, not in Live. Each key lights one LED. Run
`board.sh calibrate`: the user moves a white LED with keys below / above C1, plays C1 to accept, then the same for
C6; the board saves both (README "Calibrating from the piano"). The keys reach the board only through a lights
track, so check the OPEN set has one first: each set needs its own, and the user may switch sets mid-task
(2026-11-01: calibration "did nothing" because they had opened a song set without one).

## Lessons on the Surface (NeoKeys)

For practising set pieces the user can move the piano's and the board's USB cables from the Push to the Surface
and run NeoKeys there (`tablet/` in the ableton-mcp repo, `tablet\NeoKeys.cmd`). Then NeoKeys drives the strip:
hints, green/red flashes in practice mode, and the user's playing echoed in blue. `tablet\Duel.cmd` starts Duel
instead, a call-and-response game on the strip (`tablet/duel/README.md`). While the cables are on the
Surface, Live doesn't hear the piano and can't reach the strip, so none of the steps here work: ask where the
cables are before debugging a lights track.

## Hints, lessons and right/wrong from Live (more later)

A track with monitoring "in" ignores its own clips, so anything played from clips goes on a second empty MIDI
track, `FP10 Hints`, with no input, monitoring "off" and output FP10 Lights on the channel you want:

- Hints: output channel "Ch. 2", and a clip whose notes are the keys to press, each lasting as long as it should
  stay lit, at velocity 127 for a full-strength hint (softer = dimmer, e.g. for a note coming up after the next).
  Light it a beat early to give the user time to move.
- Correct / wrong flashes need to know what the user played compared with the hint; that logic doesn't exist yet,
  so don't promise it. A track can only send on one output channel, so channels 3 and 4 each need their own track.

The tools can't send a single MIDI message, so there is no direct "clear the strip": stopping the hint clip ends
its notes. If keys stay lit, ask the user to send All Notes Off, or unplug and replug the board.
