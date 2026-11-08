// Rally's page: the game (rally.js) on a drawn strip over the whole keyboard, FP10 Lights through strip.js, and
// the piano from Web MIDI on localhost (Rally.cmd) or the Push's MIDI hub anywhere else (PianoDeck on
// http://moo). The hub client, the strip layout and the sound are Duel's (../../duel/src/).

import { Rally, PHASE, DEFAULTS } from './rally.js';
import { StripNotes } from './strip.js';
import { SONGS, chordFor } from './songs.js';
import { Hub } from '../../duel/src/hub.js';
import { makeLayout, keyPos, whiteIndex, isBlack, noteName } from '../../duel/src/layout.js';
import { Sound } from '../../duel/src/audio.js';

const LIGHTS = /FP10 Lights/i;
const PUSH_PORT = /Ableton Push/i;
const NOT_A_PIANO = /wavetable|through|FP10 Lights/i;
const LOOKAHEAD_MS = 200;
const STORE = 'fp10-rally';
const $ = (id) => document.getElementById(id);

// As Duel: the Push's hub on any page not served from this computer, Web MIDI on localhost.
// ?hub=ws://host:port picks a hub, ?hub=off never uses one.
const HUB_PARAM = new URLSearchParams(location.search).get('hub');
const LOCAL = /^(localhost|127.0.0.1|\[::1\])$/.test(location.hostname);
const HUB_URL = HUB_PARAM === 'off' ? null
  : HUB_PARAM || (!LOCAL || !navigator.requestMIDIAccess ? `ws://${location.host}/hub` : null);

let settings = { bpm: DEFAULTS.bpm, stepBpm: DEFAULTS.stepBpm, windowMs: DEFAULTS.windowMs, mode: 'notes', chords: true,
                 click: true, hardware: true, best: 0 };
try { Object.assign(settings, JSON.parse(localStorage.getItem(STORE) || '{}')); } catch (e) { /* no storage */ }
const save = () => { try { localStorage.setItem(STORE, JSON.stringify(settings)); } catch (e) { /* no storage */ } };

const song = () => (settings.mode === 'notes' ? SONGS.vamp : null);
const target = () => (game.song ? 'key' : 'octave');

const layout = makeLayout();
const sound = new Sound();
let game = makeGame();
let lights = [];       // [{ name, send }]
let inputs = [];       // names of what plays in
let midiState = 'none';
let hub = null;
let scheduledTo = 0;
let said = { text: '', kind: '' };
const held = new Set();
const trail = [];      // recent ball positions for the drawn tail

function makeGame() {
  const g = new Rally({ lowest: layout.lowest, highest: layout.highest,
                        bpm: settings.bpm, stepBpm: settings.stepBpm,
                        windowMs: settings.windowMs, song: song() });
  g.best = settings.best || 0;
  return g;
}

const strip = new StripNotes((bytes) => {
  if (!settings.hardware) return;
  for (const out of lights) {
    try { out.send(bytes); } catch (e) { /* unplugged */ }
  }
}, layout);

// While a game runs the board hides sparks and the violet left hand (CC114 layers 25: play + hints + flashes),
// which would smear the ball. Not saved by the board and lapses after 2 minutes, so it's re-sent every minute.
let layersTimer = null;
let layersSent = 31;
function syncLayers() {
  const playing = game.phase !== PHASE.IDLE && settings.hardware && !document.hidden;
  const send = (v) => {
    for (const out of lights) {
      try { out.send([0xbf, 114, v]); } catch (e) { /* unplugged */ }
    }
    layersSent = v;
  };
  clearInterval(layersTimer);
  layersTimer = null;
  if (playing) {
    send(25);
    layersTimer = setInterval(() => send(25), 60000);
  } else if (layersSent !== 31) {
    send(31);
  }
}

// ---------- game ----------

function start(from = 'low') {
  sound.start();
  game = makeGame();
  scheduledTo = 0;
  game.start(performance.now(), from);
  const where = from === 'low' ? 'Serving from the bass end' : 'Serving from the treble end';
  // a piano key can't start the browser's sound: only a tap or a click can
  say(sound.ready || !settings.click ? `${where}…` : `${where}… (tap the screen once for the beat click)`, '');
  syncLayers();
  render();
}

function stop(text) {
  game.stop();
  strip.clear();
  syncLayers();
  say(text || '', '');
  render();
}

function handle(events) {
  for (const e of events) {
    if (e.type === 'hit') {
      const off = Math.round(e.offsetMs);
      const when = Math.abs(off) <= 30 ? 'right on it' : `${Math.abs(off)} ms ${off < 0 ? 'early' : 'late'}`;
      if (game.song && settings.chords && sound.ready) {
        // the chord of that step, softly, under the note just played
        const c = chordFor(game.song, e.step);
        for (const n of c.notes) sound.pluck(n, performance.now(), { gain: 0.28, bright: 0.25 });
      }
      const chord = game.song ? ` (${chordFor(game.song, e.step).name})` : '';
      say(`${e.rally}${chord} — ${when}`, 'good');
      if (e.rally > settings.best) { settings.best = e.rally; save(); }
    } else if (e.type === 'early') {
      say(`Too early (${Math.round(-e.offsetMs)} ms): hit as the ball reaches the amber ${target()}`, 'bad');
    } else if (e.type === 'wrong') {
      say(`${noteName(e.pitch)} — this one's ${noteName(e.want)}, the amber key`, 'bad');
    } else if (e.type === 'miss') {
      say(e.rally ? `Missed at the ${e.side === 'low' ? 'bass' : 'treble'} end after ${e.rally}. Serving again…`
                  : `Missed at the ${e.side === 'low' ? 'bass' : 'treble'} end. Serving again…`, 'bad');
      if (sound.ready) sound.pluck(e.side === 'low' ? 31 : 40, performance.now(), { gain: 0.5, bright: 0.1 });
    }
  }
  render();
}

function press(pitch, atMs, source) {
  if (game.phase === PHASE.IDLE) {
    if (source === 'midi') start(game.nearer(pitch));
    return; // the starting key isn't a return
  }
  // the piano sounds by itself; taps and computer keys get the browser's string
  if (source !== 'midi') sound.start().then(() => sound.pluck(pitch, atMs, { bright: 0.4, gain: 0.7 }));
  handle(game.noteOn(pitch, atMs));
}

const stamp = (t) => {
  const now = performance.now();
  return t > 0 && Math.abs(now - t) < 1000 ? t : now;
};

function onMidi(e) {
  const [status, d1, d2] = e.data;
  const cmd = status & 0xf0;
  if (cmd === 0x90 && d2 > 0) { held.add(d1); press(d1, stamp(e.timeStamp), 'midi'); }
  else if (cmd === 0x80 || cmd === 0x90) held.delete(d1);
}

// the key a tap or a computer key plays: the target note, or the middle of the octave
const mid = (side) => (game.song ? game.aimOf(side).land
  : Math.round((game.zones[side].low + game.zones[side].high) / 2));

// ---------- MIDI ----------

function connectHub() {
  midiState = 'hub-connecting';
  hub = new Hub({
    url: HUB_URL,
    makeSocket: (url) => new WebSocket(url),
    now: () => performance.now(),
    // the hub passes the Push's own pads too: a bumped pad isn't a return
    onMidi: (data, atMs, src) => { if (!PUSH_PORT.test(src || '')) onMidi({ data, timeStamp: atMs }); },
    onState: (s) => {
      midiState = s.open ? 'hub' : 'hub-connecting';
      lights = s.lights ? [{ name: s.lights, send: (bytes) => hub.send(bytes) }] : [];
      inputs = s.sources.filter((n) => !NOT_A_PIANO.test(n) && !PUSH_PORT.test(n));
      strip.clear();
      syncLayers();
      renderMidi();
    },
  });
  hub.connect();
}

function connectMidi() {
  if (HUB_URL) return connectHub();
  if (!navigator.requestMIDIAccess) { midiState = 'unsupported'; return renderMidi(); }
  midiState = 'asking';
  renderMidi();
  navigator.requestMIDIAccess({ sysex: false }).then((access) => {
    midiState = 'ok';
    const scan = () => {
      lights = [...access.outputs.values()].filter((o) => LIGHTS.test(o.name || ''));
      inputs = [];
      for (const i of access.inputs.values()) {
        const piano = !LIGHTS.test(i.name || '');
        i.onmidimessage = piano ? onMidi : null;
        if (piano) inputs.push(i.name);
      }
      strip.clear();
      syncLayers();
      renderMidi();
    };
    access.onstatechange = scan;
    scan();
  }, () => { midiState = 'blocked'; renderMidi(); });
}

function renderMidi() {
  const found = lights.length ? 'FP10 Lights connected' : 'FP10 Lights not found';
  const off = lights.length && !settings.hardware ? ' (lighting is off)' : '';
  const lag = hub && hub.rttMs !== null ? `; Wi-Fi lag ~${Math.round(hub.oneWayMs)} ms allowed for` : '';
  let t;
  if (midiState === 'hub') t = `Through the Push: ${inputs.join(', ') || 'no keyboard on the Push'}. ${lights.length ? found : found + ' on the Push'}${off}${lag}.`;
  else if (midiState === 'hub-connecting') t = 'Connecting to the Push for the piano and the strip… meanwhile tap the ends or use Z, M and Space.';
  else if (midiState === 'ok') t = `Playing from: ${inputs.join(', ') || 'no keyboard found'}. ${found}${off}.`;
  else if (midiState === 'asking') t = 'Asking for MIDI. Allow it to play from the piano and light the strip.';
  else t = 'MIDI isn\'t available here: tap the ends, or use Z, M and Space.';
  if (game.phase === PHASE.IDLE) t = 'Play any key, or press Start. ' + t;
  $('midi').textContent = t;
}

// ---------- page ----------

function say(text, kind) { said = { text, kind }; }

function render() {
  const v = game.view(performance.now());
  $('rally').textContent = v.rally;
  $('best').textContent = Math.max(v.best, settings.best || 0);
  $('bpm').textContent = Math.round(v.bpm);
  const s = $('said');
  s.textContent = said.text;
  s.className = 'said ' + said.kind;
  const playing = game.phase !== PHASE.IDLE;
  $('start').textContent = playing ? 'Stop' : 'Start';
  $('start').setAttribute('aria-pressed', String(playing));
  for (const side of ['low', 'high']) $('zone-' + side).classList.toggle('target', playing && v.target === side);
  renderZones();
  renderMidi();
}

function renderZones() {
  for (const side of ['low', 'high']) {
    const z = game.zones[side];
    $(`zone-${side}-keys`).textContent = game.song ? `next: ${noteName(game.aimOf(side).land)}`
      : `${noteName(z.low)}–${noteName(z.high)}`;
  }
}

function bindSettings() {
  const m = $('set-mode');
  m.value = settings.mode === 'octave' ? 'octave' : 'notes';
  m.addEventListener('change', () => {
    settings.mode = m.value;
    save();
    if (game.phase !== PHASE.IDLE) stop('Stopped: press Start or play a key to go again.');
    game = makeGame();
    render();
  });
  const num = (id, key, lo, hi) => {
    const el = $(id);
    el.value = settings[key];
    el.addEventListener('change', () => {
      const n = Math.round(Number(el.value));
      if (Number.isFinite(n)) settings[key] = Math.min(hi, Math.max(lo, n));
      el.value = settings[key];
      save();
    });
  };
  num('set-bpm', 'bpm', 40, 160);
  num('set-step', 'stepBpm', 0, 10);
  const w = $('set-window');
  w.value = String(settings.windowMs);
  if (!w.value) w.value = '150';
  w.addEventListener('change', () => {
    settings.windowMs = Number(w.value);
    save();
  });
  for (const [id, key] of [['set-click', 'click'], ['set-chords', 'chords'], ['set-hardware', 'hardware']]) {
    const el = $(id);
    el.checked = !!settings[key];
    el.addEventListener('change', () => {
      settings[key] = el.checked;
      save();
      if (key === 'hardware') { if (!el.checked) { for (const o of lights) { try { o.send([0xb0, 123, 0]); } catch (e) { /* gone */ } } } strip.clear(); syncLayers(); }
      renderMidi();
    });
  }
}

function bindInput() {
  for (const side of ['low', 'high']) {
    const el = $('zone-' + side);
    el.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      if (game.phase === PHASE.IDLE) return start(side);
      press(mid(side), stamp(e.timeStamp), 'tap');
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.repeat || e.target.closest('input, select, summary, button')) return;
    const k = e.key.toLowerCase();
    let side = k === 'z' ? 'low' : k === 'm' ? 'high' : null;
    if (k === ' ') side = game.phase === PHASE.IDLE ? 'low' : game.view(performance.now()).target;
    if (!side) return;
    e.preventDefault();
    if (game.phase === PHASE.IDLE) return start(side);
    press(mid(side), stamp(e.timeStamp), 'key');
  });
  // a piano key isn't a gesture the browser accepts for sound: any tap turns the click on
  document.addEventListener('pointerdown', () => sound.start(), { capture: true });
  $('start').addEventListener('click', () => (game.phase === PHASE.IDLE ? start('low') : stop('Stopped.')));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && game.phase !== PHASE.IDLE) stop('Stopped while the page was hidden.');
  });
  window.addEventListener('pagehide', () => {
    game.stop();
    strip.clear();
    syncLayers();
    if (hub) hub.close();
  });
}

// ---------- drawing ----------

const canvas = $('strip');
const ctx = canvas.getContext('2d');
let W = 0, H = 0;
function resize() {
  const r = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  W = r.width; H = r.height;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

const LO = whiteIndex(layout.lowest), HI = whiteIndex(layout.highest) + 1;
const X = (pos) => ((pos - LO) / (HI - LO)) * W;
const pitchPos = (p) => {
  const a = Math.floor(p), f = p - a;
  return f === 0 ? keyPos(a) : keyPos(a) + (keyPos(a + 1) - keyPos(a)) * f;
};

function glow(x, y, r, colour, alpha) {
  if (alpha <= 0.01) return;
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${colour},${alpha})`);
  g.addColorStop(1, `rgba(${colour},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
}

function draw(v) {
  ctx.clearRect(0, 0, W, H);
  const stripY = 22, keysTop = 46, keysH = H - keysTop;
  // the LEDs, dark
  ctx.fillStyle = '#16141b';
  for (let i = 0; i < layout.numLeds; i++) {
    const x = X(layout.posOfLed(i));
    if (x >= 0 && x <= W) ctx.fillRect(x - 1.5, stripY - 1.5, 3, 3);
  }
  const span = (k) => [X(keyPos(k.low) - 0.3), X(keyPos(k.high) + 0.3)];
  // the keys the ball is heading for, amber, brighter as it comes in
  if (v.aim) {
    const [a, b] = span(v.aim);
    ctx.fillStyle = `rgba(255,150,40,${0.12 + 0.6 * v.heat})`;
    ctx.fillRect(a, stripY - 4, b - a, 8);
  }
  // flashes: green where a return was hit, red on an early or wrong key, red over what missed
  for (const f of v.flashes) {
    const age = v.now - f.atMs;
    const a = Math.max(0, 1 - age / 450);
    if (f.kind === 'hit') glow(X(keyPos(f.pitch)), stripY, 26, '60,255,110', a);
    else if (f.kind === 'early' || f.kind === 'wrong') glow(X(keyPos(f.pitch)), stripY, 22, '255,60,50', a);
    else {
      const [x0, x1] = span(f.range);
      ctx.fillStyle = `rgba(255,50,40,${a * 0.9})`;
      ctx.fillRect(x0, stripY - 6, x1 - x0, 12);
    }
  }
  // the ball and its tail
  if (v.ball !== null) {
    trail.push({ t: v.now, x: X(pitchPos(v.ball)) });
    while (trail.length && v.now - trail[0].t > 350) trail.shift();
    for (const p of trail) glow(p.x, stripY, 10, '40,200,255', 0.5 * (1 - (v.now - p.t) / 350));
    const pulse = v.phase === PHASE.SERVE && v.intoBeatMs < 120 ? 1 : 0.85;
    glow(X(pitchPos(v.ball)), stripY, 18, '120,230,255', pulse);
  } else trail.length = 0;

  // the keyboard
  const whiteW = X(1) - X(0);
  for (let n = layout.lowest; n <= layout.highest; n++) {
    if (isBlack(n)) continue;
    const x = X(whiteIndex(n));
    const inZone = v.aim && n >= v.aim.low && n <= v.aim.high;
    ctx.fillStyle = held.has(n) ? '#9fe7ee' : inZone ? '#ffe2bd' : '#ece9f0';
    ctx.fillRect(x + 0.5, keysTop, whiteW - 1, keysH);
    if (n % 12 === 0) {
      ctx.fillStyle = '#4a4553';
      ctx.font = '10px system-ui, sans-serif';
      ctx.fillText(noteName(n), x + 2, keysTop + keysH - 4);
    }
  }
  for (let n = layout.lowest; n <= layout.highest; n++) {
    if (!isBlack(n)) continue;
    const c = X(keyPos(n));
    ctx.fillStyle = held.has(n) ? '#1f8a95' : '#1b1920';
    ctx.fillRect(c - whiteW * 0.3, keysTop, whiteW * 0.6, keysH * 0.6);
  }
}

// ---------- loop ----------

let lastLag = null;
function frame() {
  const now = performance.now();
  if (game.phase !== PHASE.IDLE) {
    handle(game.update(now));
    if (settings.click && sound.ready) {
      for (const b of game.beatTimes(now, now + LOOKAHEAD_MS)) {
        if (b.atMs > scheduledTo) { sound.click(b.atMs, b.accent); scheduledTo = b.atMs; }
      }
    }
  }
  // The strip's notes cross the Wi-Fi to the Push, so they're drawn that much ahead: the ball lands on the real
  // strip on the beat, not ~50 ms after it.
  const lead = midiState === 'hub' && hub ? hub.oneWayMs : 0;
  strip.frame(game.view(now + lead));
  const v = game.view(now);
  draw(v);
  if (hub && hub.rttMs !== null && Math.round(hub.oneWayMs) !== lastLag) { lastLag = Math.round(hub.oneWayMs); renderMidi(); }
  requestAnimationFrame(frame);
}

function init() {
  bindSettings();
  bindInput();
  resize();
  window.addEventListener('resize', resize);
  connectMidi();
  render();
  requestAnimationFrame(frame);
}

init();
// for testing from the console
window.rally = { get game() { return game; }, press, start, stop, onMidi };
