// Where each key lights on the FP10 Lights strip. This mirrors the firmware (keyPos() and buildKeyMap() in
// firmware/fp10_lights/fp10_lights.ino), so the virtual strip lines up with the real one: 144 LEDs along the
// back of the keys, fixed by the LED under the middle of C1 (MIDI 36) and C6 (MIDI 96).

export const NUM_LEDS = 144;
export const DEFAULT_CAL = { lowNote: 36, lowLed: 14.1, highNote: 96, highLed: 135.3 };

// Key centres in white-key widths along the back of the keys: C-E split into 5 equal slots, F-B into 7.
const POS = [0.3, 0.9, 1.5, 2.1, 2.7, 3 + 2 / 7, 3 + 6 / 7, 3 + 10 / 7, 3 + 14 / 7, 3 + 18 / 7, 3 + 22 / 7, 3 + 26 / 7];
const WHITE_INDEX = [0, -1, 1, -1, 2, 3, -1, 4, -1, 5, -1, 6];
const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

const pc = (n) => ((n % 12) + 12) % 12;
export const isBlack = (n) => ((0x54a >> pc(n)) & 1) === 1;
export const keyPos = (n) => Math.floor(n / 12) * 7 + POS[pc(n)];
// Front of a white key, in white-key widths (it spans [w, w + 1]); black keys get the white key below them.
export const whiteIndex = (n) => {
  const p = pc(n);
  return Math.floor(n / 12) * 7 + (WHITE_INDEX[p] >= 0 ? WHITE_INDEX[p] : WHITE_INDEX[p - 1]);
};
// Live's note names: MIDI 60 = C3.
export const noteName = (n) => NAMES[pc(n)] + (Math.floor(n / 12) - 2);

export function makeLayout({ numLeds = NUM_LEDS, cal = DEFAULT_CAL } = {}) {
  const ledsPerWhite = (cal.highLed - cal.lowLed) / (keyPos(cal.highNote) - keyPos(cal.lowNote));
  const origin = keyPos(cal.lowNote);
  // Fractional LED under the middle of a key (the firmware lights the nearest one).
  const ledAt = (n) => cal.lowLed + (keyPos(n) - origin) * ledsPerWhite;
  const keyLed = (n) => Math.round(ledAt(n));
  // Fractional pitch -> fractional LED, gliding between neighbouring key centres (for halos and comets).
  const ledAtPitch = (p) => {
    const a = Math.floor(p);
    const f = p - a;
    return f === 0 ? ledAt(a) : ledAt(a) + (ledAt(a + 1) - ledAt(a)) * f;
  };
  // An LED's position in white-key widths, for drawing it over a keyboard.
  const posOfLed = (i) => origin + (i - cal.lowLed) / ledsPerWhite;

  let lowest = 127;
  let highest = 0;
  for (let n = 0; n < 128; n++) {
    const i = keyLed(n);
    if (i >= 0 && i < numLeds) {
      lowest = Math.min(lowest, n);
      highest = Math.max(highest, n);
    }
  }
  return { numLeds, cal, ledsPerWhite, ledAt, keyLed, ledAtPitch, posOfLed, lowest, highest };
}
