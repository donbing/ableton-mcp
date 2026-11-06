// FP10 Lights as it is today. The firmware takes notes, not pixels (firmware/fp10_lights/README.md), and
// lights the one LED nearest each key's middle:
//
//   ch 1  blue, steady while held, then fades ~450 ms (and throws sparks if they're switched on)
//   ch 2  amber, steady while held, brightness from velocity
//   ch 3  green flash, ~400 ms        ch 4  red flash, ~400 ms        CC123  clears everything
//
// Fp10Adapter turns the same game view the pixel renderer draws into those notes, and sends only what changed
// since the last frame. Cyan, magenta and gliding halos aren't possible, so it maps:
//
//   breadcrumbs  ch 2 amber, velocity 127 / 45 / 10 for active / next / the rest
//   call         ch 2 amber in the caller's zone, ch 1 blue echo in the player's zone
//   halos        ch 1 blue, stepping in a key at a time (+/-3, +/-2, +/-1 keys), each step a third of a beat
//   comets       ch 1 blue, a key at a time; the firmware's fade-out draws the tail
//   pulse        ch 1 blue on the strip's lowest and highest keys, harder on each phase's first beat
//   hit / wrong / miss, result   ch 3 green / ch 4 red flashes (the result over the whole player zone)
//
// FirmwareSim draws what the firmware would show for the notes it's sent: the page's second strip.

import { PHASE } from './game.js';

export const STRIP_LOOK = {
  breadcrumb: [127, 45, 10],
  halo: { 3: 40, 2: 70, 1: 100 },
  haloNotActive: 0.6,
  comet: 100,
  call: 100,
  echo: 70,
  pulse: 40,
  accent: 127,
  pulseMs: 60,
};

export class Fp10Adapter {
  constructor(send, layout, look = STRIP_LOOK) {
    this.send = send;
    this.layout = layout;
    this.look = look;
    this.sent = [new Map(), new Map()]; // ch 1 and ch 2: key -> velocity currently on
    this.lastFlash = 0;
    this.lastResult = 0;
  }

  inRange(pitch) {
    return pitch >= this.layout.lowest && pitch <= this.layout.highest;
  }

  frame(view) {
    const L = this.look;
    const now = view.now;
    const want = [new Map(), new Map()];
    const raise = (ch, pitch, vel) => {
      const p = Math.round(pitch);
      const v = Math.max(1, Math.min(127, Math.round(vel)));
      if (this.inRange(p) && (want[ch].get(p) || 0) < v) want[ch].set(p, v);
    };

    if (view.phase !== PHASE.IDLE) {
      if (view.beat >= 0) {
        const b = Math.floor(view.beat);
        if ((view.beat - b) * view.beatMs < L.pulseMs) {
          const v = view.accentBeats.includes(b) ? L.accent : L.pulse;
          raise(0, this.layout.lowest, v);
          raise(0, this.layout.highest, v);
        }
      }

      for (const c of view.callNotes) {
        if (now >= c.startMs && now < c.endMs) {
          raise(1, c.pitch, L.call);
          raise(0, c.echo, L.echo);
        }
      }

      if (view.phase === PHASE.COMET_TRANSITION || view.phase === PHASE.PLAYER_RESPONSE) {
        view.targets.forEach((t, i) => {
          if (t.state !== 'pending') return;
          raise(1, t.pitch, L.breadcrumb[Math.min(2, i - view.activeIndex)]);
          const start = t.timeMs - view.haloMs;
          if (now >= start && now < t.timeMs) {
            const step = Math.max(1, Math.ceil(3 * (1 - (now - start) / view.haloMs)));
            const v = L.halo[step] * (i === view.activeIndex ? 1 : L.haloNotActive);
            raise(0, t.pitch - step, v);
            raise(0, t.pitch + step, v);
          }
        });
      }

      for (const c of view.comets) {
        if (now >= c.startMs && now < c.endMs) {
          raise(0, c.from + ((c.to - c.from) * (now - c.startMs)) / (c.endMs - c.startMs), L.comet);
        }
      }
    }

    for (let ch = 0; ch < 2; ch++) {
      const sent = this.sent[ch];
      for (const p of [...sent.keys()]) {
        if (!want[ch].has(p)) {
          this.send([0x80 | ch, p, 0]);
          sent.delete(p);
        }
      }
      for (const [p, v] of want[ch]) {
        if (sent.get(p) !== v) {
          this.send([0x90 | ch, p, v]);
          sent.set(p, v);
        }
      }
    }

    let newest = this.lastFlash;
    for (const f of view.flashes) {
      if (f.id <= this.lastFlash) continue;
      newest = Math.max(newest, f.id);
      if (this.inRange(f.pitch)) this.send([f.kind === 'hit' ? 0x92 : 0x93, f.pitch, 127]);
    }
    this.lastFlash = newest;

    const r = view.result;
    if (r && r.id > this.lastResult && view.phase === PHASE.ROUND_ESCALATION) {
      this.lastResult = r.id;
      for (let p = view.zones.player.low; p <= view.zones.player.high; p++) {
        if (this.inRange(p)) this.send([r.pass ? 0x92 : 0x93, p, 127]);
      }
    }
  }

  // All Notes Off: the firmware clears every channel.
  clear() {
    this.send([0xb0, 123, 0]);
    for (const m of this.sent) m.clear();
  }
}

// The firmware's look (fp10_lights.ino: CH_COLOUR, RELEASE_MS, FLASH_FADE, HINT_LEVEL, MIN_SEEN, HD_GAMMA).
export const FIRMWARE = {
  colours: [
    [0, 140, 255],
    [255, 110, 0],
    [0, 255, 40],
    [255, 0, 0],
  ],
  releaseMs: 450,
  flashMs: 400,
  hintLevel: 0.6,
  minSeen: 0.3,
  gamma: 2.8,
};

export const velLevel = (vel) => Math.pow(FIRMWARE.minSeen + ((1 - FIRMWARE.minSeen) * (vel - 1)) / 126, FIRMWARE.gamma);

export class FirmwareSim {
  constructor(layout) {
    this.layout = layout;
    this.keys = new Map(); // `${ch}:${note}` -> { ch, note, held, level, atMs, offMs }
  }

  receive(bytes, atMs) {
    const [status, d1, d2] = bytes;
    const type = status & 0xf0;
    const ch = status & 0x0f;
    if (type === 0xb0 && (d1 === 120 || d1 === 123)) {
      this.keys.clear();
      return;
    }
    if (ch > 3) return;
    const id = `${ch}:${d1}`;
    if (type === 0x90 && d2 > 0) {
      const level = ch === 0 ? velLevel(d2) : ch === 1 ? FIRMWARE.hintLevel * velLevel(d2) : 1;
      this.keys.set(id, { ch, note: d1, held: true, level, atMs, offMs: null });
    } else if (type === 0x80 || type === 0x90) {
      const s = this.keys.get(id);
      if (s && s.held) {
        s.held = false;
        s.offMs = atMs;
      }
    }
  }

  levelAt(s, now) {
    if (s.ch === 0) {
      if (s.held) return s.level;
      // fades evenly to the eye: in light^(1/gamma), from where it was to dark over releaseMs
      const seen = Math.pow(s.level, 1 / FIRMWARE.gamma) - (now - s.offMs) / FIRMWARE.releaseMs;
      return seen > 0 ? Math.pow(seen, FIRMWARE.gamma) : 0;
    }
    if (s.ch === 1) return s.held ? s.level : 0;
    return Math.max(0, 1 - (now - s.atMs) / FIRMWARE.flashMs);
  }

  render(now, out = new Float32Array(this.layout.numLeds * 3)) {
    const n = this.layout.numLeds;
    out.fill(0);
    for (const [id, s] of this.keys) {
      const level = this.levelAt(s, now);
      if (level <= 0) {
        if (!s.held || s.ch >= 2) this.keys.delete(id);
        continue;
      }
      const i = this.layout.keyLed(s.note);
      if (i < 0 || i >= n) continue;
      const c = FIRMWARE.colours[s.ch];
      out[i * 3] += (c[0] / 255) * level;
      out[i * 3 + 1] += (c[1] / 255) * level;
      out[i * 3 + 2] += (c[2] / 255) * level;
    }
    for (let i = 0; i < out.length; i++) if (out[i] > 1) out[i] = 1;
    return out;
  }
}
