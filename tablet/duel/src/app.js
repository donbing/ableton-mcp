// The page: wires the game to the canvas, the on-screen keys, the computer keyboard, Web MIDI (the piano in,
// FP10 Lights out, optionally the piano out for the call) and the browser's audio. What the game decides
// lives in game.js; what it looks like lives in render.js (pixels) and fp10.js (the strip's notes).

import { Game, PHASE, DEFAULTS } from './game.js';
import { makeLayout, isBlack, keyPos, whiteIndex, noteName } from './layout.js';
import { renderPixels, toScreen } from './render.js';
import { Fp10Adapter, FirmwareSim } from './fp10.js';
import { Sound } from './audio.js';

const LIGHTS = /FP10 Lights/i;
const NOT_A_PIANO = /wavetable|through|FP10 Lights/i;
const KEYS = 'awsedftgyhuj';
const LOOKAHEAD_MS = 200;
const STORE = 'fp10-duel-settings';
const METER_MS = 200;
const DEFAULT_SETTINGS = {
  bpm: DEFAULTS.bpm,
  step: DEFAULTS.bpmStep,
  window: DEFAULTS.windowMs,
  comet: DEFAULTS.cometBeats,
  pass: Math.round(DEFAULTS.passScore * 100),
  notes: DEFAULTS.startNotes,
  sound: 'pluck',
  click: true,
  view: 'zones',
  hardware: true,
  autoplay: false,
};

const $ = (id) => document.getElementById(id);
const layout = makeLayout();
const sound = new Sound();
const sim = new FirmwareSim(layout);
const ideal = new Float32Array(layout.numLeds * 3);
const today = new Float32Array(layout.numLeds * 3);

let settings = { ...DEFAULT_SETTINGS };
let mode = 'demo'; // 'demo' (the computer answers, silently, until Start), 'play', 'idle'
let game = new Game();
let lights = [];
let pianos = [];
let inputs = [];
let midiState = 'unasked';
let scheduled = new Set();
let clickedUntil = 0;
let botQueue = [];
let roundDeltas = [];
let lastResult = null;
const log = [];
const held = new Map(); // pitch -> count of sources holding it
const pointers = new Map(); // pointerId -> pitch

const toStrip = (bytes) => {
  sim.receive(bytes, performance.now());
  if (mode !== 'play' || !settings.hardware) return;
  for (const out of lights) {
    try {
      out.send(bytes);
    } catch (e) {
      /* unplugged */
    }
  }
};
const adapter = new Fp10Adapter(toStrip, layout);

// ---------- settings ----------

function loadSettings(extra) {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || '{}');
    settings = { ...DEFAULT_SETTINGS, ...saved, ...(extra || {}) };
  } catch (e) {
    settings = { ...DEFAULT_SETTINGS, ...(extra || {}) };
  }
}

function saveSettings() {
  try {
    localStorage.setItem(STORE, JSON.stringify(settings));
  } catch (e) {
    /* storage blocked: settings last until the page closes */
  }
}

function config() {
  return {
    bpm: settings.bpm,
    bpmStep: settings.step,
    windowMs: settings.window,
    cometBeats: settings.comet,
    passScore: settings.pass / 100,
    startNotes: settings.notes,
    seed: (Math.random() * 2 ** 31) | 0,
  };
}

const FIELDS = {
  'set-bpm': ['bpm', Number],
  'set-step': ['step', Number],
  'set-window': ['window', Number],
  'set-comet': ['comet', Number],
  'set-pass': ['pass', Number],
  'set-notes': ['notes', Number],
  'set-sound': ['sound', String],
  'set-click': ['click', Boolean],
  'set-view': ['view', String],
  'set-hardware': ['hardware', Boolean],
  autoplay: ['autoplay', Boolean],
};

function bindSettings() {
  for (const [id, [key, type]] of Object.entries(FIELDS)) {
    const el = $(id);
    if (type === Boolean) el.checked = !!settings[key];
    else el.value = String(settings[key]);
    el.addEventListener(el.type === 'range' ? 'input' : 'change', () => {
      const before = settings[key];
      settings[key] = type === Boolean ? el.checked : type(el.value);
      saveSettings();
      if (key === 'window') {
        $('set-window-out').textContent = `±${settings.window} ms`;
        renderMeter();
      }
      if (key === 'hardware' && before && !settings.hardware) {
        for (const out of lights) {
          try {
            out.send([0xb0, 123, 0]);
          } catch (e) {
            /* unplugged */
          }
        }
      }
      if (key === 'hardware' && settings.hardware) adapter.clear();
      if (key === 'view') resize();
    });
  }
  $('set-window-out').textContent = `±${settings.window} ms`;
}

// ---------- start / stop ----------

function begin(newMode) {
  mode = newMode;
  game = new Game(config());
  scheduled = new Set();
  clickedUntil = 0;
  botQueue = [];
  roundDeltas = [];
  lastResult = null;
  log.length = 0;
  renderLog();
  renderMeter();
  adapter.clear();
  handle(game.start(performance.now()));
  renderMode();
}

async function start() {
  begin('play');
  connectMidi(); // not awaited: a permission prompt can sit unanswered
  await sound.start();
}

function stop(reason) {
  handle(game.stop());
  adapter.frame(game.view(performance.now()));
  adapter.clear();
  for (const out of pianos) {
    try {
      out.send([0xb0, 123, 0]);
    } catch (e) {
      /* unplugged */
    }
  }
  botQueue = [];
  mode = 'idle';
  if (reason) addLog(reason, 'note');
  renderMode();
}

function renderMode() {
  const playing = mode === 'play';
  $('start').textContent = playing ? 'Stop' : 'Start';
  $('start').setAttribute('aria-pressed', String(playing));
  $('demo').hidden = mode !== 'demo';
  renderMidi();
}

// ---------- MIDI ----------

function connectMidi() {
  if (midiState === 'ok' || midiState === 'asking') return;
  if (!navigator.requestMIDIAccess) {
    midiState = 'unsupported';
    renderMidi();
    return;
  }
  midiState = 'asking';
  renderMidi();
  navigator.requestMIDIAccess({ sysex: false }).then(
    (access) => {
      midiState = 'ok';
      const scan = () => {
        const outs = [...access.outputs.values()];
        lights = outs.filter((o) => LIGHTS.test(o.name || ''));
        pianos = outs.filter((o) => !NOT_A_PIANO.test(o.name || ''));
        inputs = [...access.inputs.values()].filter((i) => !LIGHTS.test(i.name || ''));
        for (const i of access.inputs.values()) i.onmidimessage = LIGHTS.test(i.name || '') ? null : onMidi;
        adapter.clear(); // a board just plugged in starts dark; the next frame sends what's lit
        renderMidi();
      };
      access.onstatechange = scan;
      scan();
    },
    () => {
      midiState = 'blocked';
      renderMidi();
    }
  );
}

function renderMidi() {
  const el = $('midi');
  const keys = 'or your computer keys (A W S E D F T G Y H U J)';
  if (mode === 'demo') {
    el.textContent = 'Demo: the computer is answering, with the sound off. Press Start to play.';
  } else if (midiState === 'ok') {
    const piano = inputs.map((i) => i.name).join(', ') || 'no keyboard found';
    const strip = lights.length ? 'FP10 Lights connected' : 'FP10 Lights not found';
    el.textContent = `Playing from: ${piano}. ${strip}${lights.length && !settings.hardware ? ' (sending is off)' : ''}.`;
  } else if (midiState === 'asking') {
    el.textContent = 'Asking for MIDI. Allow it to play from the piano and light the strip.';
  } else if (midiState === 'blocked' || midiState === 'unsupported') {
    el.textContent = `MIDI isn't available here. Play on these keys ${keys}; on the Surface, run Duel.cmd for the piano and the strip.`;
  } else {
    el.textContent = `Play on these keys ${keys}.`;
  }
}

const stamp = (t) => {
  const now = performance.now();
  return t > 0 && Math.abs(now - t) < 1000 ? t : now;
};

function onMidi(e) {
  const [status, d1, d2] = e.data;
  const cmd = status & 0xf0;
  if (cmd === 0x90 && d2 > 0) press(d1, stamp(e.timeStamp), 'midi');
  else if (cmd === 0x80 || cmd === 0x90) release(d1);
}

// ---------- input ----------

function press(pitch, atMs, source) {
  held.set(pitch, (held.get(pitch) || 0) + 1);
  padKey(pitch);
  // the piano sounds by itself; on-screen and computer keys get the browser's string
  if (source !== 'midi' && source !== 'bot' && settings.sound !== 'off') {
    sound.start().then(() => sound.pluck(pitch, atMs, { bright: 0.3, gain: 0.75 }));
  }
  if (mode === 'demo' && source !== 'bot') return;
  handle(game.noteOn(pitch, atMs));
}

function release(pitch) {
  const n = (held.get(pitch) || 0) - 1;
  if (n > 0) held.set(pitch, n);
  else held.delete(pitch);
  padKey(pitch);
}

function buildPad() {
  const pad = $('pad');
  pad.textContent = '';
  const z = game.cfg.playerZone;
  const notes = [];
  for (let p = z.low; p <= z.high; p++) notes.push(p);
  const whites = notes.filter((p) => !isBlack(p));
  const blackW = (100 / whites.length) * 0.62;
  notes.forEach((p, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = isBlack(p) ? 'k black' : 'k white';
    b.dataset.pitch = String(p);
    b.setAttribute('aria-label', noteName(p));
    const name = document.createElement('span');
    name.className = 'nm';
    name.textContent = noteName(p);
    b.appendChild(name);
    if (KEYS[i]) {
      const k = document.createElement('kbd');
      k.textContent = KEYS[i].toUpperCase();
      b.appendChild(k);
    }
    if (isBlack(p)) {
      const below = whites.filter((w) => w < p).length;
      b.style.left = `${(below * 100) / whites.length - blackW / 2}%`;
      b.style.width = `${blackW}%`;
    }
    pad.appendChild(b);
  });

  pad.addEventListener('pointerdown', (e) => {
    const k = e.target.closest('.k');
    if (!k) return;
    e.preventDefault();
    try {
      k.setPointerCapture(e.pointerId);
    } catch (err) {
      /* not supported */
    }
    const pitch = Number(k.dataset.pitch);
    pointers.set(e.pointerId, pitch);
    press(pitch, stamp(e.timeStamp), 'pad');
  });
  const up = (e) => {
    if (!pointers.has(e.pointerId)) return;
    release(pointers.get(e.pointerId));
    pointers.delete(e.pointerId);
  };
  pad.addEventListener('pointerup', up);
  pad.addEventListener('pointercancel', up);
  pad.addEventListener('contextmenu', (e) => e.preventDefault());
}

function padKey(pitch) {
  const el = document.querySelector(`#pad .k[data-pitch="${pitch}"]`);
  if (el) el.classList.toggle('down', held.has(pitch));
}

function bindKeyboard() {
  const typing = (t) => t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) && t.type !== 'checkbox';
  window.addEventListener('keydown', (e) => {
    if (e.repeat || e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
    const i = KEYS.indexOf(e.key.toLowerCase());
    if (i < 0) return;
    e.preventDefault();
    press(game.cfg.playerZone.low + i, stamp(e.timeStamp), 'keys');
  });
  window.addEventListener('keyup', (e) => {
    const i = KEYS.indexOf(e.key.toLowerCase());
    if (i >= 0) release(game.cfg.playerZone.low + i);
  });
}

// ---------- the bot (autoplay and the demo) ----------

const gauss = () => Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());

function planBot(round) {
  botQueue = round.evaluator.results
    .map((t) => {
      const slip = Math.random() < 0.06;
      return { pitch: slip ? t.pitch + (Math.random() < 0.5 ? -2 : 2) : t.pitch, atMs: t.timeMs + gauss() * 28, sounded: false };
    })
    .sort((a, b) => a.atMs - b.atMs);
}

function runBot(now) {
  for (const b of botQueue) {
    if (!b.sounded && b.atMs < now + LOOKAHEAD_MS) {
      b.sounded = true;
      if (mode === 'play' && settings.sound !== 'off') sound.pluck(b.pitch, b.atMs, { bright: 0.3, gain: 0.75 });
    }
  }
  while (botQueue.length && botQueue[0].atMs <= now) {
    const b = botQueue.shift();
    press(b.pitch, b.atMs, 'bot');
    setTimeout(() => release(b.pitch), 120);
  }
}

// ---------- game events ----------

function handle(events) {
  for (const e of events) {
    if (e.type === 'phase') {
      if (e.phase === PHASE.COMET_TRANSITION) {
        roundDeltas = [];
        renderMeter();
        if (mode === 'demo' || settings.autoplay) planBot(e.round);
      }
      renderRail(e.phase);
    } else if (e.type === 'judgement') {
      if (e.kind === 'hit') {
        roundDeltas.push(e.deltaMs);
        renderMeter();
      }
      addLog(judgementText(e), e.kind);
    } else if (e.type === 'result') {
      lastResult = e;
      addLog(resultText(e), e.pass ? 'pass' : 'fail');
    }
  }
}

const signed = (ms) => `${ms > 0 ? '+' : ms < 0 ? '−' : '±'}${Math.abs(Math.round(ms))} ms`;

function judgementText(e) {
  const name = noteName(e.pitch);
  if (e.kind === 'hit') return `Hit ${name} ${signed(e.deltaMs)}`;
  if (e.kind === 'miss') return `Missed ${name}`;
  if (e.kind === 'early') return `Early ${name} ${signed(e.deltaMs)}`;
  return `Wrong key ${name}`;
}

function resultText(r) {
  const errors = r.wrong + r.early;
  const timing = r.meanAbsDeltaMs == null ? '' : `, ${Math.round(r.meanAbsDeltaMs)} ms off on average`;
  const extra = errors ? `, ${errors} wrong` : '';
  const next = r.pass ? (r.nextBpm > r.bpm ? `up to ${r.nextBpm} BPM` : `stays at ${r.bpm} BPM`) : `again at ${r.bpm} BPM`;
  return `Round ${r.round}: ${r.hits} of ${r.targets}${extra}${timing}. ${r.pass ? 'Passed' : 'Not yet'}, ${next}.`;
}

function addLog(text, kind) {
  log.unshift({ text, kind });
  log.length = Math.min(log.length, 8);
  renderLog();
}

function renderLog() {
  const ol = $('log');
  ol.textContent = '';
  if (!log.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = 'Hits, misses and each round’s result show up here.';
    ol.appendChild(li);
    return;
  }
  for (const entry of log) {
    const li = document.createElement('li');
    li.className = entry.kind;
    li.textContent = entry.text;
    ol.appendChild(li);
  }
}

function renderMeter() {
  const band = $('band');
  const w = (settings.window / METER_MS) * 50;
  band.style.left = `${50 - w}%`;
  band.style.width = `${2 * w}%`;
  const dots = $('dots');
  dots.textContent = '';
  for (const d of roundDeltas) {
    const i = document.createElement('i');
    i.style.left = `${50 + (Math.max(-METER_MS, Math.min(METER_MS, d)) / METER_MS) * 50}%`;
    dots.appendChild(i);
  }
}

function renderRail(phase) {
  for (const li of $('rail').children) li.classList.toggle('on', li.dataset.phase === phase);
}

// ---------- scheduling ----------

function schedule(now) {
  if (mode !== 'play') return;
  for (const c of game.upcomingCallNotes()) {
    if (scheduled.has(c.id) || c.startMs >= now + LOOKAHEAD_MS) continue;
    scheduled.add(c.id);
    if (c.startMs < now - 30) continue; // too late to sound
    if (settings.sound === 'pluck') sound.pluck(c.pitch, c.startMs, { bright: 0.85, gain: 0.9 });
    else if (settings.sound === 'piano') {
      for (const out of pianos) {
        try {
          out.send([0x90, c.pitch, 96], c.startMs);
          out.send([0x80, c.pitch, 0], c.endMs);
        } catch (e) {
          /* unplugged */
        }
      }
    }
  }
  const from = Math.max(clickedUntil, now - 30);
  if (settings.click) for (const b of game.beatsBetween(from, now + LOOKAHEAD_MS)) sound.click(b.ms, b.accent);
  clickedUntil = Math.max(clickedUntil, now + LOOKAHEAD_MS);
}

// ---------- drawing ----------

const canvas = $('strip');
const ctx = canvas.getContext('2d');
const off = document.createElement('canvas');
off.width = layout.numLeds;
off.height = 1;
const offCtx = off.getContext('2d');
const img = offCtx.createImageData(layout.numLeds, 1);
let W = 0;
let H = 0;
let dpr = 1;

function resize() {
  dpr = Math.min(2, window.devicePixelRatio || 1);
  W = canvas.clientWidth;
  H = Math.round(Math.max(200, Math.min(250, W * 0.26)));
  canvas.style.height = `${H}px`;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
}

function visibleRange() {
  if (settings.view === 'strip') return [layout.posOfLed(-0.8), layout.posOfLed(layout.numLeds - 0.2)];
  const { callerZone: c, playerZone: p } = game.cfg;
  return [whiteIndex(Math.min(c.low, p.low)) - 1.6, whiteIndex(Math.max(c.high, p.high)) + 2.6];
}

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const inZone = (n, z) => n >= z.low && n <= z.high;

function drawStrip(buf, top, h, X, label) {
  const n = layout.numLeds;
  const mid = top + h / 2;
  const pxPerLed = Math.abs(X(layout.posOfLed(1)) - X(layout.posOfLed(0)));

  ctx.fillStyle = '#0b0a0e';
  ctx.fillRect(0, top, W, h);

  for (let i = 0; i < n; i++) {
    img.data[i * 4] = toScreen(buf[i * 3]);
    img.data[i * 4 + 1] = toScreen(buf[i * 3 + 1]);
    img.data[i * 4 + 2] = toScreen(buf[i * 3 + 2]);
    img.data[i * 4 + 3] = 255;
  }
  offCtx.putImageData(img, 0, 0);
  const xa = X(layout.posOfLed(-0.5));
  const xb = X(layout.posOfLed(n - 0.5));

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, top - 10, W, h + 20);
  ctx.clip();
  ctx.imageSmoothingEnabled = true;
  ctx.globalCompositeOperation = 'lighter';
  ctx.filter = `blur(${Math.max(2, pxPerLed * 1.4).toFixed(1)}px)`;
  ctx.drawImage(off, xa, top - h * 0.4, xb - xa, h * 1.8);
  ctx.filter = 'none';
  ctx.globalAlpha = 0.55;
  ctx.drawImage(off, xa, top, xb - xa, h);
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';

  const s = Math.max(1.5, Math.min(6, pxPerLed * 0.6));
  for (let i = 0; i < n; i++) {
    const cx = X(layout.posOfLed(i));
    if (cx < -s || cx > W + s) continue;
    const r = img.data[i * 4];
    const g = img.data[i * 4 + 1];
    const b = img.data[i * 4 + 2];
    ctx.fillStyle = r + g + b ? `rgb(${r},${g},${b})` : '#211f27';
    ctx.fillRect(cx - s / 2, mid - s / 2, s, s);
  }
  ctx.restore();

  // In the zones view the strip's ends are off screen: show their beat pulse at the edges.
  if (settings.view !== 'strip') {
    const end = (from, to) => {
      let r = 0;
      let g = 0;
      let b = 0;
      for (let i = from; i <= to; i++) {
        r = Math.max(r, buf[i * 3]);
        g = Math.max(g, buf[i * 3 + 1]);
        b = Math.max(b, buf[i * 3 + 2]);
      }
      return `rgb(${toScreen(r)},${toScreen(g)},${toScreen(b)})`;
    };
    ctx.fillStyle = '#0b0a0e';
    ctx.fillRect(0, top, 14, h);
    ctx.fillRect(W - 14, top, 14, h);
    ctx.fillStyle = end(0, 2);
    ctx.fillRect(4, mid - 3, 6, 6);
    ctx.fillStyle = end(n - 3, n - 1);
    ctx.fillRect(W - 10, mid - 3, 6, 6);
  }

  ctx.font = `600 10px ${css('--body')}`;
  ctx.fillStyle = 'rgba(232,228,240,0.62)';
  ctx.textBaseline = 'bottom';
  ctx.fillText(label, 18, top - 3);
}

function drawKeys(top, h, X, lo, hi, view) {
  const { callerZone: zc, playerZone: zp } = game.cfg;
  const lit = new Set(held.keys());
  ctx.textBaseline = 'alphabetic';
  ctx.font = `600 9px ${css('--body')}`;
  for (let n = 0; n < 128; n++) {
    if (isBlack(n)) continue;
    const w = whiteIndex(n);
    if (w + 1 < lo || w > hi) continue;
    const xa = X(w);
    const xb = X(w + 1);
    ctx.fillStyle = lit.has(n) ? '#9fe7ee' : inZone(n, zp) ? '#e2f1f3' : inZone(n, zc) ? '#f3e3ec' : '#e6e3ea';
    ctx.fillRect(xa + 0.5, top, xb - xa - 1, h);
    if (n % 12 === 0 && xb - xa > 14) {
      ctx.fillStyle = '#5d5866';
      ctx.textAlign = 'center';
      ctx.fillText(noteName(n), (xa + xb) / 2, top + h - 6);
    }
  }
  for (let n = 0; n < 128; n++) {
    if (!isBlack(n)) continue;
    const c = keyPos(n);
    if (c + 0.3 < lo || c - 0.3 > hi) continue;
    const xa = X(c - 0.29);
    const xb = X(c + 0.29);
    ctx.fillStyle = lit.has(n) ? '#1f8a95' : '#1b1920';
    ctx.fillRect(xa, top, xb - xa, h * 0.62);
  }

  // zone names under the keys
  const label = (z, text, colour) => {
    const xa = X(whiteIndex(z.low));
    const xb = X(whiteIndex(z.high) + 1);
    if (xb < 0 || xa > W) return;
    ctx.fillStyle = colour;
    ctx.fillRect(xa + 2, top + h + 5, xb - xa - 4, 2);
    ctx.font = `700 11px ${css('--display')}`;
    ctx.textAlign = 'center';
    ctx.fillText(text, (xa + xb) / 2, top + h + 19);
  };
  label(zc, 'CALLER', '#ff5cb4');
  label(zp, view.phase === PHASE.IDLE ? 'YOUR ZONE' : 'YOU', '#4fe3ef');
  ctx.textAlign = 'start';
}

function draw(view) {
  const [lo, hi] = visibleRange();
  const X = (pos) => ((pos - lo) / (hi - lo)) * W;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = css('--stage') || '#060508';
  ctx.fillRect(0, 0, W, H);
  const stripH = 24;
  drawStrip(ideal, 22, stripH, X, 'IDEAL · pixel renderer');
  drawStrip(today, 68, stripH, X, 'FP10 LIGHTS TODAY · MIDI notes');
  drawKeys(104, H - 104 - 26, X, lo, hi, view);
}

// ---------- the loop ----------

const text = new Map();
const setText = (id, value) => {
  if (text.get(id) === value) return;
  text.set(id, value);
  $(id).textContent = value;
};

function hud(view, now) {
  const running = view.phase !== PHASE.IDLE;
  setText('st-bpm', String(view.bpm));
  setText('st-round', running ? String(view.round) : '–');
  setText('st-notes', running ? String(view.notes) : '–');
  setText('st-streak', String(view.streak));
  setText('st-score', lastResult ? `${Math.round(lastResult.score * 100)}%` : '–');
  const span = view.phaseEndMs - view.phaseStartMs;
  const p = running && span > 0 ? Math.max(0, Math.min(1, (now - view.phaseStartMs) / span)) : 0;
  $('progress').style.transform = `scaleX(${p.toFixed(3)})`;
}

function frame() {
  const now = performance.now();
  runBot(now); // before update(): its presses carry earlier timestamps
  if (game.phase !== PHASE.IDLE) handle(game.update(now));
  schedule(now);
  const view = game.view(now);
  renderPixels(view, layout, ideal);
  adapter.frame(view);
  sim.render(now, today);
  draw(view);
  hud(view, now);
  requestAnimationFrame(frame);
}

function init(data) {
  loadSettings(data && data.settings);
  bindSettings();
  buildPad();
  bindKeyboard();
  renderLog();
  renderMeter();
  resize();
  window.addEventListener('resize', resize);
  $('start').addEventListener('click', () => (mode === 'play' ? stop() : start()));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && mode === 'play') stop('Stopped while the page was hidden.');
  });
  window.addEventListener('pagehide', () => adapter.clear());
  // The demo is all motion: with reduced motion asked for, wait for Start instead.
  const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) {
    mode = 'idle';
    renderMode();
  } else {
    begin('demo');
  }
  requestAnimationFrame(frame);
}

if (window.claude && window.claude.hot && window.claude.hot.snapshot) {
  window.claude.hot.snapshot(() => ({ settings }));
}
if (window.claude && window.claude.hot && window.claude.hot.ready) window.claude.hot.ready(init);
else init((window.claude && window.claude.hot && window.claude.hot.data) || {});
