import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Rally, PHASE, DEFAULTS } from '../src/rally.js';
import { StripNotes } from '../src/strip.js';

const LOW = 29, HIGH = 99;
const beat = (bpm) => 60000 / bpm;

function served(from = 'low') {
  const r = new Rally({ lowest: LOW, highest: HIGH });
  r.start(0, from);
  const flyAt = DEFAULTS.serveBeats * beat(DEFAULTS.bpm);
  assert.deepEqual(r.update(flyAt), [{ type: 'serve', from }]);
  return { r, flyAt };
}

test('rally: the serve counts in, then the ball crosses the whole strip in a bar and lands on the beat', () => {
  const { r, flyAt } = served('low');
  const landMs = flyAt + DEFAULTS.crossBeats * beat(80);
  assert.equal(r.view(flyAt).ball, LOW);
  assert.equal(r.view((flyAt + landMs) / 2).ball, (LOW + HIGH) / 2);
  assert.equal(r.view(landMs).ball, HIGH);
  assert.equal(r.view(landMs).target, 'high');
  assert.equal(r.view(landMs - beat(80)).heat, 0);
  assert.equal(r.view(landMs).heat, 1);
});

test('rally: a key in the far octave near landing sends it back on the landing beat, faster', () => {
  const { r, flyAt } = served('low');
  const landMs = flyAt + 4 * beat(80);
  assert.deepEqual(r.noteOn(60, landMs), [], 'a key outside the zone does nothing');
  assert.deepEqual(r.noteOn(LOW + 3, landMs), [], 'nor one in the zone it came from');
  assert.equal(r.noteOn(HIGH - 2, landMs - 400)[0].type, 'early');
  assert.equal(r.flashes.at(-1).kind, 'early', 'an early key flashes red, so you know');
  assert.deepEqual(r.noteOn(HIGH - 2, landMs - beat(80) - 10), [], 'a key before the last beat is just playing');
  // someone reacting to the light lands ~250 ms after it: that still counts
  const [hit] = r.noteOn(HIGH - 2, landMs + 240);
  assert.equal(hit.type, 'hit');
  assert.equal(hit.offsetMs, 240);
  assert.equal(r.rally, 1);
  assert.equal(r.bpm, 80 + DEFAULTS.stepBpm);
  // the return starts on the landing beat, not when the key went down, so the pulse doesn't drift
  assert.equal(r.flight.startMs, landMs);
  assert.equal(r.flight.landMs, landMs + 4 * beat(84));
  assert.equal(r.view(landMs + 2 * beat(84)).ball, (LOW + HIGH) / 2);
  assert.equal(r.view(landMs + 1).target, 'low');
});

test('rally: a miss flashes the zone, then serves again from there at the start tempo', () => {
  const { r, flyAt } = served('low');
  const land1 = flyAt + 4 * beat(80);
  r.noteOn(HIGH, land1);
  const land2 = land1 + 4 * beat(84);
  assert.deepEqual(r.update(land2 + DEFAULTS.lateMs), []);
  const ev = r.update(land2 + DEFAULTS.lateMs + DEFAULTS.graceMs + 1);
  assert.deepEqual(ev, [{ type: 'miss', side: 'low', rally: 1 }]);
  assert.equal(r.phase, PHASE.MISSED);
  assert.equal(r.flashes.at(-1).kind, 'miss');
  r.update(land2 + DEFAULTS.missedBeats * beat(84));
  assert.equal(r.phase, PHASE.SERVE);
  assert.equal(r.bpm, 80);
  assert.equal(r.rally, 0);
  assert.equal(r.best, 1);
  assert.equal(r.view(land2 + 3000).ball, LOW, 'the low end serves');
});

test('rally: the click track has no doubled beat where one flight hands over to the next', () => {
  const { r, flyAt } = served('low');
  const land = flyAt + 4 * beat(80);
  const before = r.beatTimes(flyAt, land + 1).map((b) => b.atMs);
  assert.equal(before.length, 5);
  r.noteOn(HIGH, land);
  const after = r.beatTimes(land, land + 4 * beat(84) + 1).map((b) => b.atMs);
  assert.equal(after[0], land, 'the landing beat is the next flight\'s first');
  // the page schedules strictly after what it has already scheduled, so `land` sounds once
  assert.equal(after.filter((t) => t > before.at(-1)).length, 4);
});

test('strip: the ball is one blue key that moves, the target octave amber, flashes once', () => {
  const sent = [];
  const layout = { lowest: LOW, highest: HIGH };
  const s = new StripNotes((m) => sent.push(m), layout);
  const { r, flyAt } = served('low');
  s.frame(r.view(flyAt));
  assert.deepEqual(sent.filter((m) => m[0] === 0x90), [[0x90, LOW, 127]]);
  assert.equal(sent.filter((m) => m[0] === 0x91).length, 12);
  sent.length = 0;
  s.frame(r.view(flyAt + 10)); // ball still on the same key: nothing new
  assert.deepEqual(sent, []);
  const land = flyAt + 4 * beat(80);
  s.frame(r.view(flyAt + beat(80)));
  assert.ok(sent.some((m) => m[0] === 0x80 && m[1] === LOW), 'the old key goes off');
  r.noteOn(HIGH - 1, land);
  sent.length = 0;
  s.frame(r.view(land));
  assert.deepEqual(sent.filter((m) => m[0] === 0x92), [[0x92, HIGH - 1, 127]]);
  sent.length = 0;
  s.frame(r.view(land + 5));
  assert.equal(sent.filter((m) => m[0] === 0x92).length, 0, 'a flash is sent once');
});

test('strip: the amber zone brightens in steps, so the last beat sends 4 x 12 amber notes, not hundreds', () => {
  let n = 0;
  const s = new StripNotes((m) => { if (m[0] === 0x91) n++; }, { lowest: LOW, highest: HIGH });
  const { r, flyAt } = served('low');
  const land = flyAt + 4 * beat(80);
  for (let t = land - beat(80); t < land; t += 8) s.frame(r.view(t)); // 125 frames a second
  assert.ok(n <= 4 * 12, `${n} amber notes over the last beat`);
});
