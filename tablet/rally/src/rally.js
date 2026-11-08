// Rally: a ball crosses the whole keyboard in time with the beat, and you knock it back with any key in the
// octave it's heading for: the left hand at the bass end, the right at the treble end. Every return adds a bit of
// tempo; a miss starts the rally again from the end that missed. No DOM: times are performance.now() ms passed
// in, so node --test drives it.
//
//   IDLE     nothing moving
//   SERVE    the ball waits at the serving end for a count-in (SERVE_BEATS clicks), then flies
//   FLIGHT   the ball crosses in `crossBeats` beats and lands on a beat; a key in the far zone from windowMs
//            before landing to lateMs after sends it back, starting on that same beat so the pulse never shifts.
//            Late is more forgiving than early: someone reacting to the light lands ~200-300 ms after it.
//   MISSED   red on the zone that missed, then a fresh serve from there at the start tempo

export const PHASE = { IDLE: 'idle', SERVE: 'serve', FLIGHT: 'flight', MISSED: 'missed' };

export const DEFAULTS = {
  bpm: 80,          // start tempo
  stepBpm: 4,       // faster per return
  maxBpm: 160,
  crossBeats: 4,    // one bar end to end
  windowMs: 150,    // a return counts from this long before landing…
  lateMs: 300,      // …to this long after
  graceMs: 60,      // the window closes this much later, for notes that arrive late (Wi-Fi)
  zoneKeys: 12,     // each end's zone: an octave
  serveBeats: 4,
  missedBeats: 2,
};

const SIDES = ['low', 'high'];
const other = (side) => (side === 'low' ? 'high' : 'low');

export class Rally {
  constructor({ lowest, highest, ...opts }) {
    this.o = { ...DEFAULTS, ...opts };
    this.lowest = lowest;
    this.highest = highest;
    this.zones = {
      low: { low: lowest, high: lowest + this.o.zoneKeys - 1 },
      high: { low: highest - this.o.zoneKeys + 1, high: highest },
    };
    this.phase = PHASE.IDLE;
    this.best = 0;
    this.reset();
  }

  reset() {
    this.rally = 0;
    this.bpm = this.o.bpm;
    this.flight = null;   // { from, to, startMs, landMs }
    this.serveFrom = 'low';
    this.phaseStart = 0;
    this.lastOffset = null;
    this.flashes = [];    // { id, kind: 'hit' | 'miss', pitch?, side?, atMs }
    this.flashId = 0;
  }

  get beatMs() { return 60000 / this.bpm; }

  sideOf(pitch) {
    for (const s of SIDES) if (pitch >= this.zones[s].low && pitch <= this.zones[s].high) return s;
    return null;
  }

  // The end nearer a key: the first serve goes away from the hand that started the game.
  nearer(pitch) {
    return pitch - this.lowest <= this.highest - pitch ? 'low' : 'high';
  }

  start(nowMs, from = 'low') {
    this.reset();
    this.serve(nowMs, from);
    return [{ type: 'start', from }];
  }

  stop() {
    this.phase = PHASE.IDLE;
    this.flight = null;
  }

  serve(nowMs, from) {
    this.phase = PHASE.SERVE;
    this.serveFrom = from;
    this.phaseStart = nowMs;
    this.flight = null;
  }

  fly(from, startMs) {
    this.phase = PHASE.FLIGHT;
    this.flight = { from, to: other(from), startMs, landMs: startMs + this.o.crossBeats * this.beatMs };
  }

  // Beats of the click track: the serve's count-in, then one per beat of each flight.
  beatTimes(fromMs, toMs) {
    const out = [];
    let first, n;
    if (this.phase === PHASE.SERVE) {
      first = this.phaseStart;
      n = this.o.serveBeats + this.o.crossBeats;
    } else if (this.phase === PHASE.FLIGHT) {
      first = this.flight.startMs;
      n = this.o.crossBeats + 1;
    } else return out;
    for (let i = 0; i < n; i++) {
      const t = first + i * this.beatMs;
      if (t >= fromMs && t < toMs) out.push({ atMs: t, accent: this.phase === PHASE.SERVE ? i === 0 : i === 0 || i === this.o.crossBeats });
    }
    return out;
  }

  noteOn(pitch, atMs) {
    if (this.phase !== PHASE.FLIGHT) return [];
    const f = this.flight;
    if (this.sideOf(pitch) !== f.to) return [];
    const off = atMs - f.landMs;
    if (off < -this.o.windowMs) {
      if (off < -this.beatMs) return []; // not even in the last beat: just playing
      this.flashes.push({ id: ++this.flashId, kind: 'early', pitch, atMs });
      return [{ type: 'early', pitch, offsetMs: off }];
    }
    if (off > this.o.lateMs) return [];
    // a return: the next flight starts on the landing beat, at the new tempo
    this.rally += 1;
    this.best = Math.max(this.best, this.rally);
    this.lastOffset = off;
    this.flashes.push({ id: ++this.flashId, kind: 'hit', pitch, atMs });
    const landMs = f.landMs;
    this.bpm = Math.min(this.o.maxBpm, this.bpm + this.o.stepBpm);
    this.fly(f.to, landMs);
    return [{ type: 'hit', pitch, offsetMs: off, rally: this.rally, bpm: this.bpm }];
  }

  update(nowMs) {
    const ev = [];
    if (this.phase === PHASE.SERVE) {
      const at = this.phaseStart + this.o.serveBeats * this.beatMs;
      if (nowMs >= at) {
        this.fly(this.serveFrom, at);
        ev.push({ type: 'serve', from: this.serveFrom });
      }
    } else if (this.phase === PHASE.FLIGHT) {
      const f = this.flight;
      if (nowMs > f.landMs + this.o.lateMs + this.o.graceMs) {
        const rally = this.rally;
        this.flashes.push({ id: ++this.flashId, kind: 'miss', side: f.to, atMs: nowMs });
        this.phase = PHASE.MISSED;
        this.phaseStart = f.landMs;
        this.serveFrom = f.to;
        ev.push({ type: 'miss', side: f.to, rally });
      }
    } else if (this.phase === PHASE.MISSED) {
      const at = this.phaseStart + this.o.missedBeats * this.beatMs;
      if (nowMs >= at) {
        this.rally = 0;
        this.bpm = this.o.bpm;
        this.serve(at, this.serveFrom);
      }
    }
    this.flashes = this.flashes.filter((fl) => nowMs - fl.atMs < 2000);
    return ev;
  }

  // Where the ball is, as a fractional key, and how close the target zone's landing is (0 far … 1 now).
  view(nowMs) {
    const v = {
      phase: this.phase, now: nowMs, bpm: this.bpm, beatMs: this.beatMs, rally: this.rally, best: this.best,
      zones: this.zones, ball: null, target: null, heat: 0, flashes: this.flashes, lastOffset: this.lastOffset,
      serveBeat: null, intoBeatMs: 0,
    };
    // The ball lands as it touches a zone's inner edge (the key next to the middle), not the strip's last key:
    // someone hits when the ball reaches their octave, which used to be ~2/3 of a beat before it "landed".
    // After landing it carries on into the zone at the same speed, so a late or missed return shows.
    const edge = (side) => (side === 'low' ? this.zones.low.high : this.zones.high.low);
    if (this.phase === PHASE.SERVE) {
      v.ball = edge(this.serveFrom);
      v.target = other(this.serveFrom);
      const into = nowMs - this.phaseStart;
      v.serveBeat = Math.floor(into / this.beatMs);
      v.intoBeatMs = into - v.serveBeat * this.beatMs;
    } else if (this.phase === PHASE.FLIGHT) {
      const f = this.flight;
      const t = Math.max(0, (nowMs - f.startMs) / (f.landMs - f.startMs));
      const ball = edge(f.from) + (edge(f.to) - edge(f.from)) * t;
      v.ball = Math.min(this.highest, Math.max(this.lowest, ball));
      v.target = f.to;
      v.heat = Math.max(0, 1 - (f.landMs - nowMs) / this.beatMs); // rises over the last beat
    }
    return v;
  }
}
