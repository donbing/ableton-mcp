# FP10 Lights

An LED strip over the Roland FP-10's keys, driven by MIDI from Live on the Push 3. A Waveshare ESP32-S3-Zero
shows up as a USB MIDI device called **FP10 Lights** on the Push's USB hub; Live sends it notes and it lights the
keys. The firmware only draws what it's told: lessons, timing and right/wrong decisions belong to the MCP/skill.

## MIDI protocol

| Channel | Meaning | Look |
|---|---|---|
| 1 | Play: what's being played | Blue, brightness from velocity, fades ~330 ms after note-off, held by sustain (CC64) |
| 2 | Hint: play this next | Steady amber until note-off |
| 3 | Correct | Green flash, fades ~400 ms (note-off not needed) |
| 4 | Wrong | Red flash, fades ~400 ms (note-off not needed) |
| any | CC120 or CC123 | Clears everything |
| 16 | CC119 ≥ 64 / < 64 | Wireless update mode on / off |

Colours add where channels overlap on the same key. Channels 5-15 are ignored.

In Live: a MIDI track with input = FP-10, monitor = In, output = FP10 Lights, channel 1 forwards your playing.
Lesson hints go out on channel 2 from another track (or the MCP).

## Hardware

- Board: Waveshare ESP32-S3-Zero, on one port of a powered USB hub (500 mA per port).
- Strip: SK9822, 1 m, 144 LEDs, powered from a second hub port. Shared GND with the board.
- DATA = GPIO2, CLOCK = GPIO1, each through a ~240 Ω resistor; 100-220 µF across 5V/GND.
  (Keep the cap small: big caps on a USB port trip its inrush protection.)
- Onboard RGB LED (GPIO21) is the status light: dim green idle, blue blink on MIDI, see update mode below.

Settings at the top of `fp10_lights.ino`: pins, `COLOR_ORDER`, `MAX_MA` (power cap, 300 mA leaves room for the
SK9822s' idle draw), and the key mapping `FIRST_NOTE` / `LEDS_PER_NOTE` / `REVERSED`.

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

Start update mode by holding BOOT for 2 s, sending CC119 ≥ 64 on channel 16, or typing `update`. The onboard LED
blinks amber while connecting, turns purple when ready, white while updating, red on failure. Update mode turns
itself off after 10 minutes.
