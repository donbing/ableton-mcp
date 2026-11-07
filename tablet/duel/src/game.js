// The call-and-response state machine. No DOM, no audio, no MIDI: time comes in as performance.now()
// milliseconds and everything is laid out on one Clock, so a round is a fixed run of beats:
//
//   COUNT_IN (first round only) -> CALL_PLAYBACK -> COMET_TRANSITION -> PLAYER_RESPONSE -> ROUND_ESCALATION
//   -> CALL_PLAYBACK of the next round ...
//
// The caller plays a phrase in its zone, a comet carries it to the player's zone and lands on beat 1 of the
// response, the player plays it back, and the result decides the next round: a pass adds bpmStep and a note,
// a fail repeats the phrase at the same tempo (onFail 'repeat') or deals a new one ('new'). Tempo changes take
// effect at the next call's first beat, so the clock never breaks across a handoff.

import { Clock } from './clock.js';
import { Evaluator } from './evaluator.js';
import { makePhrase, rng } from './phrase.js';

export const PHASE = Object.freeze({
  IDLE: 'IDLE',
  COUNT_IN: 'COUNT_IN',
  CALL_PLAYBACK: 'CALL_PLAYBACK',
  COMET_TRANSITION: 'COMET_TRANSITION',
  PLAYER_RESPONSE: 'PLAYER_RESPONSE',
  ROUND_ESCALATION: 'ROUND_ESCALATION',
});

const ORDER = [PHASE.COUNT_IN, PHASE.CALL_PLAYBACK, PHASE.COMET_TRANSITION, PHASE.PLAYER_RESPONSE, PHASE.ROUND_ESCALATION];
const AFTER_ROUND = ORDER.length;

export const DEFAULTS = Object.freeze({
  bpm: 90, // first round
  bpmStep: 5, // added after each passed round
  maxBpm: 200,
  windowMs: 80, // a hit is the right key within +/- this of the beat
  phraseBeats: 4, // the call, and the response, each last this long
  cometBeats: 2, // rest between call and response, filled by the comet
  resultBeats: 2, // rest between response and the next call
  countInBeats: 4,
  haloBeats: 1, // halos start this long before their note
  callerZone: { low: 72, high: 83 }, // C4-B4 in Live's names
  playerZone: { low: 60, high: 71 }, // C3-B3
  startNotes: 3,
  maxNotes: 6,
  passScore: 0.75, // hits / (notes + wrong + early presses)
  onFail: 'repeat', // 'repeat' the phrase, or deal a 'new' one
  seed: 1,
  leadMs: 150, // start() puts beat 0 this far ahead, so the first beat can be scheduled
  inputGraceMs: 100, // a window is closed this long after it ends, so a NoteOn delivered late still counts
  stripLow: 29, // the count-in comet starts at the strip's bass end
});

// The zones for a player who plays `pitch`: the player gets that key's octave (C to B), the caller the octave
// above, or the one below when the octave above runs off the strip. Octaves the strip can't hold whole move in
// to the nearest one it can. lowest/highest are the strip's end keys (layout.lowest/.highest: 29 and 99).
export function zonesFor(pitch, lowest = 29, highest = 99) {
  const minLow = Math.ceil(lowest / 12) * 12;
  const maxLow = Math.floor((highest - 11) / 12) * 12;
  const low = Math.max(minLow, Math.min(maxLow, Math.floor(pitch / 12) * 12));
  const player = { low, high: low + 11 };
  const above = low + 12 + 11 <= highest;
  const caller = above ? { low: low + 12, high: low + 23 } : { low: low - 12, high: low - 1 };
  return { player, caller };
}

export class Game {
  constructor(options = {}) {
    this.cfg = { ...DEFAULTS, ...options };
    this.phase = PHASE.IDLE;
    this.clock = null;
    this.round = null;
    this.next = null;
    this.lastResult = null;
    this.flashes = [];
    this.presses = [];
    this.serial = 0;
    this.passes = 0;
    this.streak = 0;
    this.roundNo = 0;
  }

  start(nowMs) {
    const c = this.cfg;
    this.random = rng(c.seed);
    this.clock = new Clock(c.bpm, nowMs + c.leadMs);
    this.passes = 0;
    this.streak = 0;
    this.roundNo = 0;
    this.lastResult = null;
    this.flashes = [];
    this.presses = [];
    this.round = this.planRound(c.countInBeats, this.newPhrase());
    this.next = null;
    this.phase = PHASE.COUNT_IN;
    return [{ type: 'phase', phase: this.phase, atMs: this.clock.msAt(0), round: this.round }];
  }

  stop() {
    this.phase = PHASE.IDLE;
    this.round = null;
    this.next = null;
    return [{ type: 'phase', phase: PHASE.IDLE }];
  }

  // Moves both zones: while idle, or during the count-in until `marginMs` before the call starts (sound for the
  // call is scheduled ahead). The count-in's phrase moves with the player's zone. -> whether it moved
  setZones({ player, caller }, nowMs = 0, marginMs = 0) {
    const counting = this.phase === PHASE.COUNT_IN && nowMs < this.round.callMs - marginMs;
    if (this.phase !== PHASE.IDLE && !counting) return false;
    const shift = player.low - this.cfg.playerZone.low;
    this.cfg = { ...this.cfg, playerZone: { ...player }, callerZone: { ...caller } };
    if (counting) {
      const phrase = this.round.phrase.map((n) => ({ ...n, pitch: n.pitch + shift }));
      this.roundNo = 0;
      this.round = this.planRound(this.round.callBeat, phrase);
    }
    return true;
  }

  newPhrase() {
    const c = this.cfg;
    const notes = Math.min(c.maxNotes, c.startNotes + this.passes);
    return makePhrase({ random: this.random, zone: c.playerZone, notes, beats: c.phraseBeats });
  }

  planRound(callBeat, phrase) {
    const c = this.cfg;
    const clock = this.clock;
    const cometBeat = callBeat + c.phraseBeats;
    const responseBeat = cometBeat + c.cometBeats;
    const resultBeat = responseBeat + c.phraseBeats;
    const endBeat = resultBeat + c.resultBeats;
    const shift = c.callerZone.low - c.playerZone.low;
    const no = ++this.roundNo;
    const callNotes = phrase.map((n, i) => ({
      id: `${no}.${i}`,
      pitch: n.pitch + shift, // sounds in the caller's zone
      echo: n.pitch, // lit in the player's zone as it sounds
      startMs: clock.msAt(callBeat + n.beat),
      endMs: clock.msAt(callBeat + n.beat + n.dur),
    }));
    const targets = phrase.map((n) => ({ pitch: n.pitch, beat: n.beat, timeMs: clock.msAt(responseBeat + n.beat) }));
    return {
      no,
      phrase,
      bpm: clock.bpmAt(callBeat),
      beatMs: clock.beatMsAt(callBeat),
      callBeat,
      cometBeat,
      responseBeat,
      resultBeat,
      endBeat,
      callMs: clock.msAt(callBeat),
      cometMs: clock.msAt(cometBeat),
      responseMs: clock.msAt(responseBeat),
      resultMs: clock.msAt(resultBeat),
      endMs: clock.msAt(endBeat),
      callNotes,
      evaluator: new Evaluator(targets, {
        windowMs: c.windowMs,
        opensAtMs: clock.msAt(responseBeat - c.haloBeats),
      }),
      result: null,
    };
  }

  phaseIndexAt(beat) {
    const r = this.round;
    if (beat < r.callBeat) return 0;
    if (beat < r.cometBeat) return 1;
    if (beat < r.responseBeat) return 2;
    if (beat < r.resultBeat) return 3;
    if (beat < r.endBeat) return 4;
    return AFTER_ROUND;
  }

  // Moves through every phase boundary up to nowMs, in order (a long gap, such as a hidden tab, plays out
  // the missed rounds rather than skipping them). -> events
  update(nowMs) {
    if (this.phase === PHASE.IDLE) return [];
    const events = [];
    const beat = this.clock.beatAt(nowMs);
    for (let guard = 0; guard < 1000; guard++) {
      if (this.phaseIndexAt(beat) <= ORDER.indexOf(this.phase)) break;
      this.advance(events);
    }
    if (this.phase === PHASE.COMET_TRANSITION || this.phase === PHASE.PLAYER_RESPONSE) {
      // A NoteOn is judged by its own timestamp, but can arrive a frame or two late (a busy main thread):
      // close windows only once it can't still be on its way.
      this.judge(events, this.round.evaluator.expire(nowMs - this.cfg.inputGraceMs), nowMs);
    }
    this.prune(nowMs);
    return events;
  }

  advance(events) {
    const r = this.round;
    switch (this.phase) {
      case PHASE.COUNT_IN:
        return this.enter(PHASE.CALL_PLAYBACK, r.callMs, events);
      case PHASE.CALL_PLAYBACK:
        return this.enter(PHASE.COMET_TRANSITION, r.cometMs, events);
      case PHASE.COMET_TRANSITION:
        return this.enter(PHASE.PLAYER_RESPONSE, r.responseMs, events);
      case PHASE.PLAYER_RESPONSE:
        this.finishRound(events);
        return this.enter(PHASE.ROUND_ESCALATION, r.resultMs, events);
      case PHASE.ROUND_ESCALATION:
        this.round = this.next;
        this.next = null;
        return this.enter(PHASE.CALL_PLAYBACK, this.round.callMs, events);
    }
  }

  enter(phase, atMs, events) {
    this.phase = phase;
    events.push({ type: 'phase', phase, atMs, round: this.round });
  }

  finishRound(events) {
    const c = this.cfg;
    const r = this.round;
    const ev = r.evaluator;
    this.judge(events, ev.expire(r.resultMs), r.resultMs);
    this.judge(events, ev.finish(), r.resultMs);
    const summary = ev.summary();
    const pass = summary.score >= c.passScore;
    if (pass) {
      this.passes++;
      this.streak++;
    } else {
      this.streak = 0;
    }
    const nextBpm = pass ? Math.min(c.maxBpm, r.bpm + c.bpmStep) : r.bpm;
    const phrase = pass || c.onFail === 'new' ? this.newPhrase() : r.phrase;
    this.clock.setTempo(r.endBeat, nextBpm);
    this.next = this.planRound(r.endBeat, phrase);
    r.result = { id: ++this.serial, ...summary, pass, bpm: r.bpm, nextBpm, round: r.no, atMs: r.resultMs };
    this.lastResult = r.result;
    events.push({ type: 'result', ...r.result });
  }

  judge(events, judgements, atMs) {
    for (const j of judgements) {
      const flash = { id: ++this.serial, kind: j.kind, pitch: j.pitch, deltaMs: j.deltaMs, atMs };
      this.flashes.push(flash);
      events.push({ type: 'judgement', ...flash });
    }
  }

  // A key went down at timeMs (the MIDI or pointer event's own timestamp). -> events
  noteOn(pitch, timeMs) {
    const events = this.update(timeMs);
    this.presses.push({ pitch, atMs: timeMs });
    if (this.phase !== PHASE.COMET_TRANSITION && this.phase !== PHASE.PLAYER_RESPONSE) return events;
    const j = this.round.evaluator.noteOn(pitch, timeMs);
    this.judge(events, j.missed, timeMs);
    if (j.kind !== 'ignored') this.judge(events, [j], timeMs);
    return events;
  }

  prune(nowMs) {
    this.flashes = this.flashes.filter((f) => nowMs - f.atMs < 1000);
    this.presses = this.presses.filter((p) => nowMs - p.atMs < 600);
  }

  // Call notes not yet over, this round's and the next one's, for the audio scheduler.
  upcomingCallNotes() {
    return [...(this.round ? this.round.callNotes : []), ...(this.next ? this.next.callNotes : [])];
  }

  // Beats from fromMs (inclusive) to toMs (exclusive): [{ beat, ms, accent }], accent on each phase's first beat.
  beatsBetween(fromMs, toMs) {
    if (this.phase === PHASE.IDLE) return [];
    const starts = new Set([0]);
    for (const r of [this.round, this.next]) {
      if (r) [r.callBeat, r.cometBeat, r.responseBeat, r.resultBeat].forEach((b) => starts.add(b));
    }
    const out = [];
    for (let b = Math.max(0, Math.ceil(this.clock.beatAt(fromMs) - 1e-9)); ; b++) {
      const ms = this.clock.msAt(b);
      if (ms >= toMs) break;
      if (ms >= fromMs) out.push({ beat: b, ms, accent: starts.has(b) });
    }
    return out;
  }

  // Everything a renderer needs at nowMs, as plain data.
  view(nowMs) {
    const c = this.cfg;
    const r = this.round;
    const v = {
      now: nowMs,
      phase: this.phase,
      zones: { caller: c.callerZone, player: c.playerZone },
      beat: 0,
      bpm: r ? r.bpm : c.bpm,
      beatMs: 60000 / (r ? r.bpm : c.bpm),
      accentBeats: [],
      callNotes: [],
      targets: [],
      activeIndex: 0,
      haloMs: 0,
      comets: [],
      flashes: this.flashes,
      presses: this.presses,
      result: this.lastResult,
      round: r ? r.no : 0,
      notes: r ? r.phrase.length : 0,
      streak: this.streak,
      passes: this.passes,
      phaseStartMs: 0,
      phaseEndMs: 0,
    };
    if (this.phase === PHASE.IDLE || !r) return v;

    v.beat = this.clock.beatAt(nowMs);
    v.accentBeats = [0, r.callBeat, r.cometBeat, r.responseBeat, r.resultBeat];
    v.callNotes = r.callNotes;
    v.targets = r.evaluator.results;
    v.activeIndex = r.evaluator.active;
    v.haloMs = r.beatMs * c.haloBeats;
    v.cometMs = r.cometMs;
    v.responseMs = r.responseMs;
    const bounds = {
      [PHASE.COUNT_IN]: [this.clock.msAt(0), r.callMs],
      [PHASE.CALL_PLAYBACK]: [r.callMs, r.cometMs],
      [PHASE.COMET_TRANSITION]: [r.cometMs, r.responseMs],
      [PHASE.PLAYER_RESPONSE]: [r.responseMs, r.resultMs],
      [PHASE.ROUND_ESCALATION]: [r.resultMs, r.endMs],
    }[this.phase];
    [v.phaseStartMs, v.phaseEndMs] = bounds;

    const lastCall = r.callNotes[r.callNotes.length - 1].pitch;
    const firstTarget = r.evaluator.results[0].pitch;
    const lastTarget = r.evaluator.results[r.evaluator.results.length - 1].pitch;
    if (this.phase === PHASE.COUNT_IN) {
      v.comets.push({ kind: 'countin', from: c.stripLow, to: r.callNotes[0].pitch, startMs: this.clock.msAt(0), endMs: r.callMs });
    }
    v.comets.push({ kind: 'handoff', from: lastCall, to: firstTarget, startMs: r.cometMs, endMs: r.responseMs });
    if (this.next) {
      v.comets.push({
        kind: r.result && r.result.pass ? 'pass' : 'fail',
        from: lastTarget,
        to: this.next.callNotes[0].pitch,
        startMs: r.resultMs,
        endMs: r.endMs,
      });
    }
    return v;
  }
}
