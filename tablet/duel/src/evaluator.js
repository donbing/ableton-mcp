// Scores NoteOns against a phrase's targets: right key within +/- windowMs of the target's time is a hit.
// Targets are taken in order; the first one still pending is the active target (N).
//
//   hit    right key, inside the window. The target is done and the next one becomes active.
//   miss   the window closed with no hit (found on the next expire() or noteOn()).
//   wrong  a key no pending target wants at that moment.
//   early  the active target's key, before its window opened.
//
// Hitting a later target inside its window counts the ones skipped as missed, so a player who drops a note
// stays in step instead of being stuck on it. NoteOns before `opensAtMs` are ignored (noodling during the
// call), and so are NoteOns after the last target.

export class Evaluator {
  constructor(targets, { windowMs = 80, opensAtMs = -Infinity } = {}) {
    this.windowMs = windowMs;
    this.opensAtMs = opensAtMs;
    this.results = targets
      .map((t) => ({ ...t, state: 'pending', deltaMs: null, atMs: null }))
      .sort((a, b) => a.timeMs - b.timeMs);
    this.active = 0;
    this.wrong = 0;
    this.early = 0;
  }

  get done() {
    return this.active >= this.results.length;
  }

  miss(r) {
    r.state = 'missed';
    return { kind: 'miss', pitch: r.pitch, target: r, deltaMs: null };
  }

  // Targets whose window has closed by `nowMs` become misses.
  expire(nowMs) {
    const missed = [];
    while (!this.done && nowMs > this.results[this.active].timeMs + this.windowMs) {
      missed.push(this.miss(this.results[this.active]));
      this.active++;
    }
    return missed;
  }

  // -> { kind: 'hit'|'wrong'|'early'|'ignored', pitch, deltaMs, target, missed: [...] }
  noteOn(pitch, timeMs) {
    const missed = this.expire(timeMs);
    if (timeMs < this.opensAtMs || this.done) return { kind: 'ignored', pitch, deltaMs: null, missed };

    for (let i = this.active; i < this.results.length; i++) {
      const r = this.results[i];
      if (r.timeMs - this.windowMs > timeMs) break; // later windows haven't opened yet
      if (r.pitch === pitch && Math.abs(timeMs - r.timeMs) <= this.windowMs) {
        while (this.active < i) missed.push(this.miss(this.results[this.active++]));
        r.state = 'hit';
        r.deltaMs = timeMs - r.timeMs;
        r.atMs = timeMs;
        this.active = i + 1;
        return { kind: 'hit', pitch, deltaMs: r.deltaMs, target: r, missed };
      }
    }

    const active = this.results[this.active];
    if (active.pitch === pitch && timeMs < active.timeMs - this.windowMs) {
      this.early++;
      return { kind: 'early', pitch, deltaMs: timeMs - active.timeMs, target: active, missed };
    }
    this.wrong++;
    return { kind: 'wrong', pitch, deltaMs: null, target: null, missed };
  }

  // The response is over: whatever is still pending is missed.
  finish() {
    const missed = [];
    while (!this.done) missed.push(this.miss(this.results[this.active++]));
    return missed;
  }

  summary() {
    const hits = this.results.filter((r) => r.state === 'hit');
    const misses = this.results.filter((r) => r.state === 'missed').length;
    const n = this.results.length;
    const mean = hits.length ? hits.reduce((s, r) => s + Math.abs(r.deltaMs), 0) / hits.length : null;
    return {
      targets: n,
      hits: hits.length,
      misses,
      wrong: this.wrong,
      early: this.early,
      meanAbsDeltaMs: mean,
      // Each error press costs as much as a missed note, so mashing keys doesn't pay.
      score: n ? hits.length / (n + this.wrong + this.early) : 0,
    };
  }
}
