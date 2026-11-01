# FP10 Lights

An LED strip over the Roland FP-10's keys, driven by MIDI from Live on the Push 3. A Waveshare ESP32-S3-Zero
shows up as a USB MIDI device called **FP10 Lights** on the Push's USB hub; Live sends it notes and it lights the
keys. The firmware only draws what it's told: lessons, timing and right/wrong decisions belong to the MCP/skill.

## MIDI protocol

| Channel | Meaning | Look |
|---|---|---|
| 1 | Play: what's being played | Blue, brightness from velocity, fades ~450 ms after note-off; ~4 s with sustain (CC64) down |
| 2 | Hint: play this next | Steady amber until note-off |
| 3 | Correct | Green flash, fades ~400 ms (note-off not needed) |
| 4 | Wrong | Red flash, fades ~400 ms (note-off not needed) |
| any | CC120 or CC123 | Clears everything |
| 16 | CC119 ≥ 64 / < 64 | Wireless update mode on / off |
| 16 | CC118 ≥ 64 / < 64 | Calibration mode on / cancel |

Colours add where channels overlap on the same key. Channels 5-15 are ignored.

In Live (on the Push the ports are **Roland Digital Piano MIDI 1** and **FP10 Lights MIDI 1**): a MIDI track
with no devices, input = the FP-10, monitor = In, output = FP10 Lights, channel 1, forwards your playing. Lesson
hints go out on channel 2 from another track. Each set needs its own lights track. The MCP side is in
`.claude/skills/ableton-music/recipes/fp10-lights.md`.

## Hardware

- Board: Waveshare ESP32-S3-Zero, on one port of a powered USB hub (500 mA per port).
- Strip: SK9822, 1 m, 144 LEDs, powered from the board's hub port (5V/GND shared with the board).
- DATA = GPIO2, CLOCK = GPIO1, each through a ~240 Ω resistor; 100-220 µF across 5V/GND.
  (Keep the cap small: big caps on a USB port trip its inrush protection.)
- Onboard RGB LED (GPIO21) is the status light: dim green idle, blue blink on MIDI, see update mode below.

Settings at the top of `fp10_lights.ino`: pins, `COLOR_ORDER`, `MAX_MA`, `BRIGHTNESS`, the key mapping, and the fade
times `RELEASE_MS` / `SUSTAIN_MS`.
`MAX_MA` (250) caps the strip, idle draw included: the firmware counts 1 mA per LED idle, so ~106 mA is left
for lit keys at `LED_MA` (20 mA) per colour at full, and dims the whole strip when more is asked for. That makes
the worst case ~250 mA for the strip, ~300-330 mA with the board on the same 500 mA port. (FastLED's own cap isn't
used: it would count the gamma-encoded values sent in HD mode, below, and dim chords far too soon.)

The strip runs as FastLED's `SK9822HD`: FastLED applies a 2.8 gamma and uses the chips' 5-bit global brightness,
which gives fine steps near dark. Plain `SK9822` has only ~128 steps at 50% brightness, and dithering between them
flickered at the end of fades. The sketch works in linear light and undoes the gamma (`toHd()`), so colours and
fades look as they did; dithering is off.

`BRIGHTNESS` (128 = 50%) dims everything on the strip (not the status LED) and halves the current; the cap only
bites when many keys are lit.

The mapping follows the keyboard layout at the back of the keys, where the strip sits: C-E split into 5 equal
slots and F-B into 7, black keys included (so B's back is right of its front's middle, and C's left). It is fixed
by which LED sits under the middle of C1 and C6. Each key lights the one LED nearest its middle; `WHITE_SPAN` /
`BLACK_SPAN` (share of the key's width, e.g. 0.8 / 0.5) light more. `REVERSED` flips the strip.

## Calibrating from the piano

With the lights track routing the FP-10 to the board (channel 1), run `./board.sh calibrate` (or send CC118 ≥ 64
on channel 16, or type `calibrate` on serial). The onboard LED turns cyan and one white LED shows where C1 lights.
On an 88-key piano C1 (MIDI 36, Live's names) is the 2nd C from the bottom and C6 (MIDI 96) the 2nd C from the top.

1. Play any key below C1 to move the light one LED left, any key above to move it right.
2. When it sits in the middle of C1, play C1.
3. The light jumps to C6: the same again, then play C6.

Both points are saved on the board and survive updates; `show` on serial prints them, `forget` clears them along
with the Wi-Fi details. `CAL_LOW_LED` / `CAL_HIGH_LED` are only the defaults for a board never calibrated.
`./board.sh calibrate off` cancels, and so does 5 minutes without a key.

## Building

Uses [arduino-cli](https://arduino.github.io/arduino-cli/) with the pinned profile in `sketch.yaml`
(ESP32 core 3.3.12, FastLED 3.9.20). Don't move FastLED to 3.10.x: 3.10.8 crashes the S3 when driving SK9822.

```sh
./build.sh          # build + flash over USB (PORT=/dev/ttyACM0 by default)
./build.sh ota      # build + flash over Wi-Fi to fp10-lights.local
```

If the board crash-loops and won't take an upload, hold BOOT while plugging it in, then flash.

`../sk9822_test/` is a standalone wiring check (red/green/blue on the first 10 LEDs, then a dot along the strip).
Build it with FastLED 3.9.20 and `--fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc` (hardware CDC, no TinyUSB).

## Wi-Fi and wireless updates

Wi-Fi is off unless update mode is on. The Wi-Fi details are stored on the board, not in this repo. Set them once
over USB serial (`arduino-cli monitor -p /dev/ttyACM0`):

```
set ssid <name>
set pass <password>
set otapass <password>   # optional: also put it in ~/.config/fp10-lights/ota_pass for build.sh
show                     # prints the SSID and whether passwords are set
forget                   # clears everything
update                   # starts update mode
```

Start update mode by holding BOOT for 2 s, sending CC119 ≥ 64 on channel 16, or typing `update`. With the board
on the Push, `./board.sh update` (run from a PC with `ssh push3`) sends the CC for you; then `./build.sh ota` on
moo. `./board.sh update off` ends it. The onboard LED blinks amber while connecting, turns purple when ready,
white while updating, red on failure. Update mode turns itself off after 10 minutes.

After an update the board restarts, and about one restart in three the Push refuses it (`dmesg`: `can't set config
#1, error -32`, no FP10 Lights port in Live; the board's LED stays green). Unplug and replug it; if it stays dark,
use another hub port (that fixed it twice when the same port didn't, and the first port worked again later). Tried
without success (2026-11-01): a clean USB disconnect before restarting, restarting through deep sleep, and the
board reconnecting itself when unconfigured (from the board's side the connection looked fine, MIDI included).
