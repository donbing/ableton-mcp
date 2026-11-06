import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Game, PHASE } from '../src/game.js';
import { makeLayout } from '../src/layout.js';
import { renderPixels } from '../src/render.js';
import { Fp10Adapter, FirmwareSim } from '../src/fp10.js';

// 120 BPM, beat 0 at 150 ms: count-in 150-2150, call 2150-4150, comet 4150-5150, response 5150-7150,
// escalation 7150-8150, next call from 8150.
const newGame = (opts = {}) => {
  const g = new Game({ bpm: 120, seed: 3, ...opts });
  g.start(0);
  return g;
};

test('phases follow each other on the beat', () => {
  const g = newGame();
  const at = (ms) => (g.update(ms), g.phase);
  assert.equal(at(2149), PHASE.COUNT_IN);
  assert.equal(at(2150), PHASE.CALL_PLAYBACK);
  assert.equal(at(4149), PHASE.CALL_PLAYBACK);
  assert.equal(at(4150), PHASE.COMET_TRANSITION);
  assert.equal(at(5150), PHASE.PLAYER_RESPONSE);
  assert.equal(at(7150), PHASE.ROUND_ESCALATION);
  assert.equal(at(8150), PHASE.CALL_PLAYBACK);
  assert.equal(g.round.no, 2);
});

test('the call sounds in the caller zone and is echoed in the player zone; the comet lands on the first target', () => {
  const g = newGame();
  const r = g.round;
  for (const c of r.callNotes) {
    assert.equal(c.pitch, c.echo + 12);
    assert.ok(c.pitch >= 72 && c.pitch <= 83);
  }
  assert.equal(r.callNotes[0].startMs, 2150);
  g.update(4500);
  const v = g.view(4500);
  const handoff = v.comets.find((c) => c.kind === 'handoff');
  assert.equal(handoff.startMs, 4150);
  assert.equal(handoff.endMs, 5150);
  assert.equal(handoff.endMs, v.targets[0].timeMs); // first note is on beat 1 of the response
  assert.equal(handoff.from, r.callNotes[r.callNotes.length - 1].pitch);
  assert.equal(handoff.to, v.targets[0].pitch);
});

const playAll = (g, offsetMs = 0) => {
  for (const t of g.round.evaluator.results) g.noteOn(t.pitch, t.timeMs + offsetMs);
};

test('a clean response passes: +5 BPM from the next call, one more note, the clock unbroken', () => {
  const g = newGame();
  g.update(4150);
  playAll(g, 40);
  const events = g.update(7150);
  const result = events.find((e) => e.type === 'result');
  assert.equal(result.pass, true);
  assert.equal(result.hits, result.targets);
  assert.equal(result.meanAbsDeltaMs, 40);
  assert.equal(result.nextBpm, 125);
  assert.equal(g.next.callMs, 8150);
  assert.equal(g.next.beatMs, 480);
  assert.equal(g.next.phrase.length, g.round.phrase.length + 1);
  g.update(8150);
  assert.equal(g.view(8150).bpm, 125);
  assert.equal(g.streak, 1);
});

test('a missed response fails: the same phrase again at the same tempo, every note judged a miss', () => {
  const g = newGame();
  const phrase = g.round.phrase;
  g.update(4150);
  const events = g.update(7150);
  const misses = events.filter((e) => e.type === 'judgement' && e.kind === 'miss');
  assert.equal(misses.length, phrase.length);
  const result = events.find((e) => e.type === 'result');
  assert.equal(result.pass, false);
  assert.equal(result.nextBpm, 120);
  assert.deepEqual(g.next.phrase, phrase);
  assert.equal(g.streak, 0);
});

test('timing outside the window fails the round', () => {
  const g = newGame();
  g.update(4150);
  playAll(g, 90);
  const result = g.update(7150).find((e) => e.type === 'result');
  assert.equal(result.hits, 0);
  assert.equal(result.pass, false);
});

test('a long gap plays out every phase in order', () => {
  const g = newGame();
  const phases = g.update(60000).filter((e) => e.type === 'phase').map((e) => e.phase);
  const cycle = [PHASE.CALL_PLAYBACK, PHASE.COMET_TRANSITION, PHASE.PLAYER_RESPONSE, PHASE.ROUND_ESCALATION];
  phases.forEach((p, i) => assert.equal(p, cycle[i % 4]));
  assert.ok(phases.length > 20);
});

test('beatsBetween marks each phase start as an accent', () => {
  const g = newGame();
  const beats = g.beatsBetween(0, 5200);
  assert.deepEqual(beats.map((b) => b.beat), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(beats.filter((b) => b.accent).map((b) => b.beat), [0, 4, 8, 10]);
  assert.equal(beats[4].ms, 2150);
});

// ---- renderers ----

const layout = makeLayout();
const baseView = (over = {}) => ({
  now: 0,
  phase: PHASE.PLAYER_RESPONSE,
  zones: { caller: { low: 72, high: 83 }, player: { low: 60, high: 71 } },
  beat: -1, // no pulse
  bpm: 120,
  beatMs: 500,
  accentBeats: [],
  callNotes: [],
  targets: [],
  activeIndex: 0,
  haloMs: 500,
  comets: [],
  flashes: [],
  presses: [],
  result: null,
  cometMs: 0,
  responseMs: 0,
  phaseStartMs: 0,
  phaseEndMs: 1,
  ...over,
});
const rgbAt = (buf, i) => [buf[i * 3], buf[i * 3 + 1], buf[i * 3 + 2]];
// Light-weighted centre of the LEDs from a to b (exclusive of `skip`).
const centroid = (buf, a, b, skip) => {
  let sum = 0;
  let w = 0;
  for (let i = Math.floor(a); i <= Math.ceil(b); i++) {
    if (i === skip) continue;
    const l = buf[i * 3] + buf[i * 3 + 1] + buf[i * 3 + 2];
    sum += i * l;
    w += l;
  }
  return w ? sum / w : NaN;
};

test('breadcrumbs: active cyan, next amber, the rest dim blue; a hit promotes the next one', () => {
  const targets = [
    { pitch: 60, timeMs: 5000, state: 'pending' },
    { pitch: 64, timeMs: 5500, state: 'pending' },
    { pitch: 67, timeMs: 6000, state: 'pending' },
  ];
  let buf = renderPixels(baseView({ targets }), layout);
  const [a, n, q] = [60, 64, 67].map((p) => rgbAt(buf, layout.keyLed(p)));
  assert.ok(a[2] > 0.9 && a[1] > 0.8 && a[0] < 0.1, `active ${a}`);
  assert.ok(n[0] > n[1] && n[1] > n[2] && n[0] < a[2], `next ${n}`);
  assert.ok(q[2] > q[0] && q[2] < 0.1, `queue ${q}`);

  targets[0].state = 'hit';
  buf = renderPixels(baseView({ targets, activeIndex: 1 }), layout);
  assert.deepEqual(rgbAt(buf, layout.keyLed(60)), [0, 0, 0]);
  assert.ok(rgbAt(buf, layout.keyLed(64))[2] > 0.9);
});

test('halos start 3 keys out a beat before the note and close in at the tempo', () => {
  const target = { pitch: 66, timeMs: 1000, state: 'pending' }; // F#3: nothing else within 3 keys
  const centre = layout.keyLed(66);
  const at = (now) => renderPixels(baseView({ now, targets: [target] }), layout);
  const left = (now) => centroid(at(now), layout.ledAt(62), layout.ledAt(66) - 0.5, centre);
  assert.ok(Math.abs(left(500) - layout.ledAtPitch(63)) < 0.6, `q=0 ${left(500)}`);
  assert.ok(Math.abs(left(750) - layout.ledAtPitch(64.5)) < 0.6, `q=0.5 ${left(750)}`);
  assert.ok(left(900) > left(750));
  const before = rgbAt(at(499), layout.keyLed(63));
  assert.ok(before[0] + before[1] + before[2] === 0, 'no halo before its beat');
});

test('comets run from zone to zone and land at their end time', () => {
  const comet = { kind: 'handoff', from: 81, to: 60, startMs: 0, endMs: 1000 };
  const view = (now) => baseView({ now, phase: PHASE.COMET_TRANSITION, comets: [comet], cometMs: 0, responseMs: 1000 });
  const head = (buf) => {
    let best = -1;
    let bestL = 0;
    for (let i = 0; i < layout.numLeds; i++) {
      const [r, g, b] = rgbAt(buf, i);
      if (r > 0.3 && g > 0.3 && b > 0.3 && r + g + b > bestL) [best, bestL] = [i, r + g + b];
    }
    return best;
  };
  const mid = (layout.ledAt(81) + layout.ledAt(60)) / 2;
  assert.ok(Math.abs(head(renderPixels(view(500), layout)) - mid) <= 1);
  assert.ok(Math.abs(head(renderPixels(view(999), layout)) - layout.ledAt(60)) <= 1);
});

test('FP10 adapter: breadcrumbs on ch 2 by tier, only changes sent, a hit re-tiers', () => {
  const sent = [];
  const fp = new Fp10Adapter((b) => sent.push(b), layout);
  const targets = [
    { pitch: 60, timeMs: 9000, state: 'pending' },
    { pitch: 64, timeMs: 9500, state: 'pending' },
    { pitch: 67, timeMs: 9900, state: 'pending' },
  ];
  fp.frame(baseView({ targets }));
  assert.deepEqual(sent, [
    [0x91, 60, 127],
    [0x91, 64, 45],
    [0x91, 67, 10],
  ]);
  sent.length = 0;
  fp.frame(baseView({ now: 5, targets }));
  assert.deepEqual(sent, []);
  targets[0].state = 'hit';
  fp.frame(baseView({ now: 10, targets, activeIndex: 1, flashes: [{ id: 1, kind: 'hit', pitch: 60, atMs: 10 }] }));
  assert.deepEqual(sent, [
    [0x81, 60, 0],
    [0x91, 64, 127],
    [0x91, 67, 45],
    [0x92, 60, 127],
  ]);
  sent.length = 0;
  fp.frame(baseView({ now: 20, targets, activeIndex: 1, flashes: [{ id: 1, kind: 'hit', pitch: 60, atMs: 10 }] }));
  assert.deepEqual(sent, [], 'a flash is sent once');
});

test('FP10 adapter: halos step in a key at a time on ch 1', () => {
  const sent = [];
  const fp = new Fp10Adapter((b) => sent.push(b), layout);
  const targets = [{ pitch: 66, timeMs: 1000, state: 'pending' }];
  const ch1 = () => sent.filter((b) => (b[0] & 0x0f) === 0);
  fp.frame(baseView({ now: 510, targets }));
  assert.deepEqual(ch1(), [
    [0x90, 63, 40],
    [0x90, 69, 40],
  ]);
  sent.length = 0;
  fp.frame(baseView({ now: 900, targets }));
  assert.deepEqual(ch1(), [
    [0x80, 63, 0],
    [0x80, 69, 0],
    [0x90, 65, 100],
    [0x90, 67, 100],
  ]);
});

test('firmware sim: blue fades evenly to dark in 450 ms, flashes in 400 ms, CC123 clears', () => {
  const sim = new FirmwareSim(layout);
  const i = layout.keyLed(60);
  sim.receive([0x90, 60, 127], 0);
  sim.receive([0x80, 60, 0], 100);
  assert.ok(Math.abs(sim.render(325)[i * 3 + 2] - Math.pow(0.5, 2.8)) < 1e-6);
  assert.equal(sim.render(551)[i * 3 + 2], 0);
  sim.receive([0x92, 62, 127], 1000);
  assert.ok(Math.abs(sim.render(1200)[layout.keyLed(62) * 3 + 1] - 0.5) < 1e-6);
  sim.receive([0x91, 64, 127], 1000);
  sim.receive([0xb0, 123, 0], 1100);
  assert.ok(sim.render(1100).every((x) => x === 0));
});

test('a NoteOn delivered a frame late still counts by its own timestamp', () => {
  const g = newGame();
  g.update(4150);
  const first = g.round.evaluator.results[0];
  g.update(first.timeMs + 140); // the main thread got here before the MIDI event was handed over
  const events = g.noteOn(first.pitch, first.timeMs + 30);
  assert.equal(events.find((e) => e.type === 'judgement').kind, 'hit');
  // but once the grace has passed, the window is closed
  g.update(g.round.evaluator.results[1].timeMs + 181);
  assert.equal(g.round.evaluator.results[1].state, 'missed');
});
