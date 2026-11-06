// The pixel renderer: a game view -> one RGB value per LED, in linear light (0-1), for any frame time.
// It is a pure function of (view, now), so it runs at whatever rate the display does and draws the same
// picture on a canvas or, given a frame mode in the firmware, on the strip.
//
// Layers, added together:
//   pulse        the strip's end LEDs on every beat, brighter on each phase's first beat
//   zones        a faint tick at each zone's edges
//   call         caller's notes in its zone as they sound, echoed in the player's zone (the spatial echo)
//   breadcrumbs  every note of the response at once: active (cyan), next (amber), the rest (dim blue)
//   halos        two points from +/-3 keys collapsing onto each note over the beat before it
//   comets       the handoff between zones, timed to land on the next phase's first beat
//   flashes      hit (green), wrong / early / missed (red); presses as faint white blips
//   result       the player's zone washed green or red while the next round is set up

import { PHASE } from './game.js';

export const LOOK = {
  active: { rgb: [0.0, 0.85, 1.0], level: 1.0 },
  next: { rgb: [1.0, 0.45, 0.0], level: 0.32 },
  queue: { rgb: [0.15, 0.25, 1.0], level: 0.05 },
  halo: { rgb: [0.75, 0.95, 1.0], level: 0.85, keys: 3, collapseMs: 150 },
  call: { rgb: [1.0, 0.2, 0.62], level: 0.9 },
  echo: { rgb: [0.0, 0.85, 1.0], level: 0.45, residue: 0.03 },
  comet: { head: [1.0, 1.0, 1.0], level: 0.9, tailLeds: 10, burstMs: 160 },
  cometTail: { countin: [1.0, 0.2, 0.62], handoff: [0.0, 0.75, 1.0], pass: [0.1, 1.0, 0.3], fail: [1.0, 0.1, 0.05] },
  hit: { rgb: [0.1, 1.0, 0.3], level: 1.0, ms: 400, perfectMs: 30 },
  wrong: { rgb: [1.0, 0.04, 0.04], level: 1.0, ms: 400 },
  miss: { rgb: [1.0, 0.04, 0.04], level: 0.35, ms: 400 },
  press: { rgb: [1.0, 1.0, 1.0], level: 0.25, ms: 250 },
  pulse: { rgb: [0.35, 0.4, 1.0], accent: [1.0, 1.0, 1.0], level: 0.3, accentLevel: 0.9, leds: 3, decay: 5 },
  zone: { rgb: [0.7, 0.7, 1.0], level: 0.005 },
  result: { pass: [0.1, 1.0, 0.3], fail: [1.0, 0.04, 0.04], level: 0.2 },
};

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

export function renderPixels(view, layout, out = new Float32Array(layout.numLeds * 3), look = LOOK) {
  const n = layout.numLeds;
  const now = view.now;
  out.fill(0);

  const px = (i, rgb, k) => {
    if (i < 0 || i >= n || !(k > 0)) return;
    out[i * 3] += rgb[0] * k;
    out[i * 3 + 1] += rgb[1] * k;
    out[i * 3 + 2] += rgb[2] * k;
  };
  // A point between LEDs, shared by how close each is, so it glides instead of hopping.
  const splat = (x, rgb, k) => {
    const i = Math.floor(x);
    const f = x - i;
    px(i, rgb, k * (1 - f));
    px(i + 1, rgb, k * f);
  };
  const key = (pitch, rgb, k) => px(layout.keyLed(pitch), rgb, k);
  const idle = view.phase === PHASE.IDLE;

  // zones: a tick on the unused LED just outside each zone, breathing while idle
  const zoneK = look.zone.level * (idle ? 1.5 + Math.sin(now / 700) : 1);
  for (const z of [view.zones.caller, view.zones.player]) {
    px(Math.round((layout.ledAt(z.low - 1) + layout.ledAt(z.low)) / 2), look.zone.rgb, zoneK);
    px(Math.round((layout.ledAt(z.high) + layout.ledAt(z.high + 1)) / 2), look.zone.rgb, zoneK);
  }
  if (idle) {
    for (const p of view.presses) key(p.pitch, look.press.rgb, look.press.level * (1 - (now - p.atMs) / look.press.ms));
    return clampAll(out);
  }

  // pulse at both ends, on the quarter-note grid
  if (view.beat >= 0) {
    const b = Math.floor(view.beat);
    const frac = view.beat - b;
    const accent = view.accentBeats.includes(b);
    const k = (accent ? look.pulse.accentLevel : look.pulse.level) * Math.exp(-frac * look.pulse.decay);
    const rgb = accent ? look.pulse.accent : look.pulse.rgb;
    for (let i = 0; i < look.pulse.leds; i++) {
      const fall = 1 - i / look.pulse.leds;
      px(i, rgb, k * fall);
      px(n - 1 - i, rgb, k * fall);
    }
  }

  // the call, and its echo in the player's zone
  const residue = view.phase === PHASE.CALL_PLAYBACK ? look.echo.residue : 0;
  for (const c of view.callNotes) {
    if (now < c.startMs) continue;
    const dur = Math.max(1, c.endMs - c.startMs);
    const k = now < c.endMs ? 1 - 0.6 * ((now - c.startMs) / dur) : 0.4 * (1 - (now - c.endMs) / 200);
    key(c.pitch, look.call.rgb, look.call.level * clamp01(k));
    key(c.echo, look.echo.rgb, Math.max(look.echo.level * clamp01(k), residue));
  }

  const showTargets = view.phase === PHASE.COMET_TRANSITION || view.phase === PHASE.PLAYER_RESPONSE;
  if (showTargets) {
    // breadcrumbs: the best tier wins where one key has several notes
    const fade = view.phase === PHASE.COMET_TRANSITION ? clamp01((now - view.cometMs) / (0.5 * (view.responseMs - view.cometMs))) : 1;
    const tiers = new Map();
    view.targets.forEach((t, i) => {
      if (t.state !== 'pending') return;
      const tier = Math.min(2, i - view.activeIndex);
      if (!tiers.has(t.pitch) || tiers.get(t.pitch) > tier) tiers.set(t.pitch, tier);
    });
    const byTier = [look.active, look.next, look.queue];
    for (const [pitch, tier] of tiers) key(pitch, byTier[tier].rgb, byTier[tier].level * fade);

    // halos
    view.targets.forEach((t, i) => {
      if (t.state !== 'pending') return;
      const start = t.timeMs - view.haloMs;
      const weight = i === view.activeIndex ? 1 : 0.5;
      if (now >= start && now < t.timeMs) {
        const q = (now - start) / view.haloMs;
        const off = look.halo.keys * (1 - q);
        const k = look.halo.level * (0.25 + 0.75 * q) * weight;
        splat(layout.ledAtPitch(t.pitch - off), look.halo.rgb, k);
        splat(layout.ledAtPitch(t.pitch + off), look.halo.rgb, k);
      } else if (now >= t.timeMs && now < t.timeMs + look.halo.collapseMs) {
        key(t.pitch, look.halo.rgb, look.halo.level * weight * (1 - (now - t.timeMs) / look.halo.collapseMs));
      }
    });
  }

  // comets
  for (const c of view.comets) {
    const x0 = layout.ledAtPitch(c.from);
    const x1 = layout.ledAtPitch(c.to);
    const tail = look.cometTail[c.kind] || look.cometTail.handoff;
    if (now >= c.startMs && now < c.endMs) {
      const p = (now - c.startMs) / (c.endMs - c.startMs);
      const x = x0 + (x1 - x0) * p;
      const dir = Math.sign(x1 - x0) || 1;
      const frac = view.beat - Math.floor(view.beat);
      const k = look.comet.level * (0.7 + 0.3 * Math.exp(-frac * 6)); // the head flares on each beat
      splat(x, look.comet.head, k);
      for (let d = 1; d <= look.comet.tailLeds && d <= Math.abs(x - x0) + 1e-9; d++) {
        splat(x - dir * d, tail, k * Math.exp(-d / 3));
      }
    } else if (now >= c.endMs && now < c.endMs + look.comet.burstMs) {
      const k = look.comet.level * (1 - (now - c.endMs) / look.comet.burstMs);
      splat(x1, look.comet.head, k);
      splat(x1 - 1.5, tail, k * 0.5);
      splat(x1 + 1.5, tail, k * 0.5);
    }
  }

  // result wash over the player's zone
  if (view.phase === PHASE.ROUND_ESCALATION && view.result) {
    const span = Math.max(1, view.phaseEndMs - view.phaseStartMs);
    const k = look.result.level * (1 - clamp01((now - view.phaseStartMs) / span));
    const rgb = view.result.pass ? look.result.pass : look.result.fail;
    for (let p = view.zones.player.low; p <= view.zones.player.high; p++) key(p, rgb, k);
  }

  // flashes and presses
  for (const f of view.flashes) {
    const l = f.kind === 'hit' ? look.hit : f.kind === 'miss' ? look.miss : look.wrong;
    const k = l.level * (1 - (now - f.atMs) / l.ms);
    key(f.pitch, l.rgb, k);
    if (f.kind === 'hit' && Math.abs(f.deltaMs) <= look.hit.perfectMs) {
      const i = layout.keyLed(f.pitch);
      px(i - 1, [1, 1, 1], k * 0.5);
      px(i + 1, [1, 1, 1], k * 0.5);
    }
  }
  for (const p of view.presses) key(p.pitch, look.press.rgb, look.press.level * (1 - (now - p.atMs) / look.press.ms));

  return clampAll(out);
}

function clampAll(out) {
  for (let i = 0; i < out.length; i++) if (out[i] > 1) out[i] = 1;
  return out;
}

// Linear light -> 0-255 for a screen (sRGB-ish), for drawing the buffer.
export const toScreen = (linear) => (linear <= 0 ? 0 : Math.round(255 * Math.pow(Math.min(1, linear), 1 / 2.2)));
