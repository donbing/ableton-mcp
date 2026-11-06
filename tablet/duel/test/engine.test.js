import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Clock } from '../src/clock.js';
import { Evaluator } from '../src/evaluator.js';
import { makeLayout, keyPos, noteName, whiteIndex } from '../src/layout.js';
import { makePhrase, rng, scaleNotes } from '../src/phrase.js';

test('layout matches the firmware: C1 and C6 on their calibrated LEDs, strip covers F0-D#5 at the default calibration', () => {
  const l = makeLayout();
  assert.equal(l.keyLed(36), 14);
  assert.equal(l.keyLed(96), 135);
  assert.equal(l.lowest, 29);
  assert.equal(l.highest, 99); // E5's middle rounds to LED 144, off the strip, as in the firmware
  // neighbouring keys never share an LED
  for (let n = l.lowest; n < l.highest; n++) assert.ok(l.keyLed(n + 1) > l.keyLed(n), `key ${n}`);
  // a fractional pitch sits between its neighbours
  const mid = l.ledAtPitch(60.5);
  assert.ok(mid > l.ledAt(60) && mid < l.ledAt(61));
  assert.ok(Math.abs(l.posOfLed(l.ledAt(60)) - keyPos(60)) < 1e-9);
  assert.equal(noteName(60), 'C3');
  assert.equal(whiteIndex(61), whiteIndex(60));
});

test('clock: beats and ms convert both ways, and a tempo change keeps earlier beats where they were', () => {
  const c = new Clock(120, 1000);
  assert.equal(c.msAt(4), 3000);
  assert.equal(c.beatAt(3000), 4);
  c.setTempo(8, 60);
  assert.equal(c.msAt(8), 5000);
  assert.equal(c.msAt(4), 3000);
  assert.equal(c.msAt(9), 6000);
  assert.equal(c.beatAt(6000), 9);
  assert.equal(c.bpmAt(7.9), 120);
  assert.equal(c.bpmAt(8), 60);
});

test('phrases: seeded, on the grid, first note on the downbeat, inside the zone and scale', () => {
  const zone = { low: 60, high: 71 };
  const a = makePhrase({ random: rng(7), zone, notes: 5 });
  const b = makePhrase({ random: rng(7), zone, notes: 5 });
  assert.deepEqual(a, b);
  assert.equal(a.length, 5);
  assert.equal(a[0].beat, 0);
  const allowed = scaleNotes(zone);
  assert.deepEqual(allowed, [60, 62, 64, 67, 69]);
  for (let i = 0; i < a.length; i++) {
    assert.ok(allowed.includes(a[i].pitch));
    assert.equal((a[i].beat * 2) % 1, 0);
    assert.ok(a[i].beat < 4);
    if (i) assert.ok(a[i].beat > a[i - 1].beat);
  }
});

const targets = () => [
  { pitch: 60, timeMs: 1000 },
  { pitch: 62, timeMs: 1500 },
  { pitch: 64, timeMs: 2000 },
];

test('evaluator: right key within +/-80 ms hits and promotes the next target', () => {
  const e = new Evaluator(targets());
  assert.equal(e.noteOn(60, 1080).kind, 'hit');
  assert.equal(e.active, 1);
  const j = e.noteOn(62, 1421);
  assert.equal(j.kind, 'hit');
  assert.equal(j.deltaMs, -79);
  assert.equal(e.active, 2);
});

test('evaluator: a closed window is a miss, and the next target becomes active', () => {
  const e = new Evaluator(targets());
  assert.deepEqual(e.expire(1080), []);
  const missed = e.expire(1081);
  assert.equal(missed.length, 1);
  assert.equal(missed[0].kind, 'miss');
  assert.equal(e.active, 1);
});

test('evaluator: wrong key, early key, and noodling before the window opens', () => {
  const e = new Evaluator(targets(), { opensAtMs: 500 });
  assert.equal(e.noteOn(60, 400).kind, 'ignored');
  assert.equal(e.noteOn(60, 900).kind, 'early');
  assert.equal(e.noteOn(65, 1000).kind, 'wrong');
  assert.equal(e.active, 0);
  assert.equal(e.noteOn(60, 1010).kind, 'hit');
  const s = e.summary();
  assert.equal(s.early, 1);
  assert.equal(s.wrong, 1);
});

test('evaluator: hitting the next note in its window counts the skipped one as missed', () => {
  const e = new Evaluator(targets());
  const j = e.noteOn(62, 1490);
  assert.equal(j.kind, 'hit');
  assert.equal(j.missed.length, 1);
  assert.equal(j.missed[0].pitch, 60);
  assert.equal(e.active, 2);
});

test('evaluator: finish misses the rest; score charges error presses like misses', () => {
  const e = new Evaluator(targets());
  e.noteOn(60, 1000);
  e.noteOn(61, 1500);
  e.noteOn(62, 1500);
  e.finish();
  const s = e.summary();
  assert.equal(s.hits, 2);
  assert.equal(s.misses, 1);
  assert.equal(s.wrong, 1);
  assert.equal(s.score, 2 / 4);
  assert.equal(s.meanAbsDeltaMs, 0);
});
