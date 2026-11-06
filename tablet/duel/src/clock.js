// The game's one musical clock: beats <-> milliseconds (performance.now() time), with tempo changes that
// take effect from a given beat. Earlier beats keep their times, so the clock never jumps when the tempo
// goes up between rounds.

export class Clock {
  constructor(bpm, originMs) {
    this.segments = [{ beat: 0, ms: originMs, bpm }];
  }

  segmentForBeat(beat) {
    let s = this.segments[0];
    for (const seg of this.segments) if (seg.beat <= beat) s = seg;
    return s;
  }

  segmentForMs(ms) {
    let s = this.segments[0];
    for (const seg of this.segments) if (seg.ms <= ms) s = seg;
    return s;
  }

  msAt(beat) {
    const s = this.segmentForBeat(beat);
    return s.ms + ((beat - s.beat) * 60000) / s.bpm;
  }

  beatAt(ms) {
    const s = this.segmentForMs(ms);
    return s.beat + ((ms - s.ms) * s.bpm) / 60000;
  }

  bpmAt(beat) {
    return this.segmentForBeat(beat).bpm;
  }

  beatMsAt(beat) {
    return 60000 / this.bpmAt(beat);
  }

  // From `beat` on, run at `bpm`. Segments from that beat on are replaced.
  setTempo(beat, bpm) {
    const ms = this.msAt(beat);
    this.segments = this.segments.filter((s) => s.beat < beat);
    this.segments.push({ beat, ms, bpm });
  }
}
