// Phrases for the caller: short melodies on an eighth-note grid, in the player's zone. Seeded, so a round
// can be replayed and tested.

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const MAJOR_PENTATONIC = [0, 2, 4, 7, 9];

// The scale's notes inside a zone, counting from the zone's lowest note as the root.
export function scaleNotes(zone, scale = MAJOR_PENTATONIC) {
  const notes = [];
  for (let p = zone.low; p <= zone.high; p++) {
    if (scale.includes((((p - zone.low) % 12) + 12) % 12)) notes.push(p);
  }
  return notes;
}

// [{ beat, pitch, dur }] sorted by beat: `notes` onsets on a `grid`-beat grid inside `beats`, the first on the
// downbeat, pitches stepping through the scale like a melody (mostly steps, sometimes a skip).
export function makePhrase({ random, zone, notes, beats = 4, grid = 0.5, scale = MAJOR_PENTATONIC }) {
  const pitches = scaleNotes(zone, scale);
  if (!pitches.length) throw new Error('no scale notes in the zone');
  const slots = Math.round(beats / grid);
  const count = Math.max(1, Math.min(notes, slots));

  const free = [];
  for (let s = 1; s < slots; s++) free.push(s);
  const onsets = [0];
  while (onsets.length < count) {
    const k = Math.floor(random() * free.length);
    onsets.push(free.splice(k, 1)[0]);
  }
  onsets.sort((a, b) => a - b);

  const steps = [-2, -1, -1, 1, 1, 2];
  let at = Math.floor(random() * Math.ceil(pitches.length / 2));
  const phrase = [];
  for (let i = 0; i < onsets.length; i++) {
    if (i > 0) {
      let next = at + steps[Math.floor(random() * steps.length)];
      if (next < 0 || next >= pitches.length) next = at - Math.sign(next - at); // bounce off the zone's edge
      at = Math.max(0, Math.min(pitches.length - 1, next));
    }
    const beat = onsets[i] * grid;
    const nextBeat = i + 1 < onsets.length ? onsets[i + 1] * grid : beats;
    phrase.push({ beat, pitch: pitches[at], dur: Math.min(nextBeat - beat, 1) * 0.9 });
  }
  return phrase;
}
