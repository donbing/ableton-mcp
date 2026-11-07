// Rally on FP10 Lights as the firmware is today (notes, not pixels; see tablet/duel/src/fp10.js):
//
//   ball         ch 1 blue on the key under it; the firmware's 450 ms fade draws its tail
//   target zone  ch 2 amber, dim, brightening over the last beat before the ball lands
//   serve        ch 2 amber on the ball at the serving end, harder on each count-in beat
//   return       ch 3 green flash on the key that hit it
//   miss         ch 4 red flash over the zone that missed
//
// Sends only what changed since the last frame.

import { PHASE } from './rally.js';

export const LOOK = { ball: 127, zoneIdle: 6, zoneHot: 70, serve: 50, serveBeat: 127, serveBeatMs: 120 };

export class StripNotes {
  constructor(send, layout, look = LOOK) {
    this.send = send;
    this.layout = layout;
    this.look = look;
    this.sent = [new Map(), new Map()]; // ch 1, ch 2: key -> velocity on
    this.lastFlash = 0;
  }

  inRange(p) { return p >= this.layout.lowest && p <= this.layout.highest; }

  frame(view) {
    const L = this.look;
    const want = [new Map(), new Map()];
    const raise = (ch, pitch, vel) => {
      const p = Math.round(pitch);
      const v = Math.max(1, Math.min(127, Math.round(vel)));
      if (this.inRange(p) && (want[ch].get(p) || 0) < v) want[ch].set(p, v);
    };
    if (view.phase === PHASE.FLIGHT) {
      raise(0, view.ball, L.ball);
      const z = view.zones[view.target];
      const v = L.zoneIdle + (L.zoneHot - L.zoneIdle) * view.heat;
      for (let p = z.low; p <= z.high; p++) raise(1, p, v);
    } else if (view.phase === PHASE.SERVE) {
      raise(1, view.ball, view.intoBeatMs < L.serveBeatMs ? L.serveBeat : L.serve);
      const z = view.zones[view.target];
      for (let p = z.low; p <= z.high; p++) raise(1, p, L.zoneIdle);
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
      if (f.kind === 'hit') {
        if (this.inRange(f.pitch)) this.send([0x92, f.pitch, 127]);
      } else {
        const z = view.zones[f.side];
        for (let p = z.low; p <= z.high; p++) if (this.inRange(p)) this.send([0x93, p, 127]);
      }
    }
    this.lastFlash = newest;
  }

  // All Notes Off: the firmware clears every channel.
  clear() {
    this.send([0xb0, 123, 0]);
    for (const m of this.sent) m.clear();
  }
}
