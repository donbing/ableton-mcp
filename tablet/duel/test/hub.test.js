import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Hub, HEARTBEAT_MS, RETRY_MS, MAX_ONE_WAY_MS } from '../src/hub.js';

// A fake WebSocket and clock: the hub is driven by hand.
function rig() {
  const t = { now: 1000, sockets: [], timers: [], laters: [], midi: [], states: [] };
  const hub = new Hub({
    url: 'ws://moo:8484/hub',
    now: () => t.now,
    makeSocket: (url) => {
      const ws = { url, readyState: 0, sent: [], send(s) { this.sent.push(JSON.parse(s)); }, close() { this.readyState = 3; } };
      t.sockets.push(ws);
      return ws;
    },
    onMidi: (data, atMs, src) => t.midi.push({ data, atMs, src }),
    onState: (s) => t.states.push(s),
    setTimer: (fn) => { t.timers.push(fn); return t.timers.length; },
    clearTimer: () => {},
    later: (fn) => { t.laters.push(fn); return t.laters.length; },
    cancel: () => {},
  });
  const open = (ws) => { ws.readyState = 1; ws.onopen(); };
  const recv = (ws, msg) => ws.onmessage({ data: JSON.stringify(msg) });
  return { t, hub, open, recv };
}

test('hub: finds the strip and the pianos from hello, and sends to the strip by its hub name', () => {
  const { t, hub, open, recv } = rig();
  hub.connect();
  const ws = t.sockets[0];
  assert.equal(ws.url, 'ws://moo:8484/hub');
  assert.equal(hub.send([0x91, 60, 100]), false, 'nothing to send to before hello');
  open(ws);
  recv(ws, { type: 'hello', sources: ['Roland Digital Piano MIDI 1'], outputs: ['FP10 Lights MIDI 1'] });
  const s = t.states.at(-1);
  assert.equal(s.open, true);
  assert.equal(s.lights, 'FP10 Lights MIDI 1');
  assert.deepEqual(s.sources, ['Roland Digital Piano MIDI 1']);
  assert.equal(hub.send([0xbf, 114, 25]), true);
  assert.deepEqual(ws.sent.at(-1), { type: 'midi', to: 'FP10 Lights MIDI 1', data: [0xbf, 114, 25] });
});

test('hub: notes are stamped earlier by half the ping round trip, smoothed and capped', () => {
  const { t, hub, open, recv } = rig();
  hub.connect();
  const ws = t.sockets[0];
  open(ws);
  // no ping answered yet: arrival time as it is
  t.now = 2000;
  recv(ws, { type: 'midi', src: 'Roland Digital Piano MIDI 1', data: [0x90, 60, 80] });
  assert.equal(t.midi.at(-1).atMs, 2000);
  // a 60 ms round trip: notes count 30 ms before they arrived
  recv(ws, { type: 'pong', t: t.now - 60 });
  t.now = 3000;
  recv(ws, { type: 'midi', src: 'Roland Digital Piano MIDI 1', data: [0x90, 62, 80] });
  assert.equal(t.midi.at(-1).atMs, 3000 - 30);
  assert.deepEqual(t.midi.at(-1).data, [0x90, 62, 80]);
  // a terrible Wi-Fi spell can't push notes back by more than MAX_ONE_WAY_MS
  for (let i = 0; i < 20; i++) recv(ws, { type: 'pong', t: t.now - 2000 });
  assert.equal(hub.oneWayMs, MAX_ONE_WAY_MS);
});

test('hub: a Push that goes silent for two heartbeats is dropped and reconnected', () => {
  const { t, hub, open, recv } = rig();
  hub.connect();
  const ws = t.sockets[0];
  open(ws);
  recv(ws, { type: 'hello', sources: [], outputs: ['FP10 Lights MIDI 1'] });
  t.now += HEARTBEAT_MS;
  t.timers[0]();                                 // heard recently enough: a ping goes out
  assert.equal(ws.sent.at(-1).type, 'ping');
  t.now += 2 * HEARTBEAT_MS + 1;
  t.timers[0]();                                 // silent too long: lost
  assert.equal(t.states.at(-1).open, false);
  assert.equal(t.states.at(-1).lights, null);
  assert.equal(hub.send([0x91, 60, 1]), false);
  assert.equal(t.laters.length, 1);
  t.now += RETRY_MS;
  t.laters[0]();
  assert.equal(t.sockets.length, 2, 'a new socket after the retry delay');
  hub.close();
  assert.equal(t.sockets[1].readyState, 3);
});
