// Browser sound: a plucked string for the call (Karplus-Strong, rendered once per pitch) and a metronome click.
// Everything is scheduled in performance.now() milliseconds and converted to the AudioContext time that is
// heard then (getOutputTimestamp), so the sound lands with the light despite the output latency.

export class Sound {
  constructor() {
    this.ctx = null;
    this.cache = new Map();
  }

  // Call from a click or key press: browsers only start audio after one.
  async start() {
    const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!AC) return false;
    if (!this.ctx) {
      this.ctx = new AC({ latencyHint: 'interactive' });
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.5;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state !== 'running') {
      try {
        await this.ctx.resume();
      } catch (e) {
        return false;
      }
    }
    return true;
  }

  get ready() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  timeAt(ms) {
    const ctx = this.ctx;
    const ts = ctx.getOutputTimestamp ? ctx.getOutputTimestamp() : null;
    if (ts && ts.performanceTime > 0) return ts.contextTime + (ms - ts.performanceTime) / 1000;
    return ctx.currentTime + (ms - performance.now()) / 1000 - (ctx.outputLatency || ctx.baseLatency || 0);
  }

  string(pitch, bright) {
    const id = `${pitch}:${bright}`;
    if (this.cache.has(id)) return this.cache.get(id);
    const sr = this.ctx.sampleRate;
    const period = sr / (440 * Math.pow(2, (pitch - 69) / 12));
    const n = Math.max(2, Math.floor(period - 0.5));
    const len = Math.floor(sr * 1.4);
    const buffer = this.ctx.createBuffer(1, len, sr);
    const d = buffer.getChannelData(0);
    let lp = 0;
    let mean = 0;
    for (let i = 0; i < n; i++) {
      lp += (Math.random() * 2 - 1 - lp) * (0.25 + 0.7 * bright);
      d[i] = lp;
      mean += lp / n;
    }
    for (let i = 0; i < n; i++) d[i] -= mean;
    for (let i = n; i < len; i++) d[i] = 0.4985 * (d[i - n] + (i - n - 1 >= 0 ? d[i - n - 1] : 0));
    const fade = Math.floor(sr * 0.03);
    for (let i = 0; i < fade; i++) d[len - 1 - i] *= i / fade;
    // the loop sounds at sr / (n + 0.5); playbackRate brings it to the exact pitch
    const entry = { buffer, rate: (n + 0.5) / period };
    this.cache.set(id, entry);
    return entry;
  }

  pluck(pitch, ms, { gain = 0.8, bright = 0.5 } = {}) {
    if (!this.ready) return;
    const ctx = this.ctx;
    const { buffer, rate } = this.string(pitch, bright);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.playbackRate.value = rate;
    const g = ctx.createGain();
    g.gain.value = gain;
    src.connect(g).connect(this.master);
    src.start(Math.max(ctx.currentTime, this.timeAt(ms)));
  }

  click(ms, accent) {
    if (!this.ready) return;
    const ctx = this.ctx;
    const t = Math.max(ctx.currentTime, this.timeAt(ms));
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.frequency.value = accent ? 2200 : 1500;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(accent ? 0.35 : 0.18, t + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.04);
    osc.connect(g).connect(this.master);
    osc.start(t);
    osc.stop(t + 0.05);
  }
}
