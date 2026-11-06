// The Push's MIDI hub (MCP_Server/midi_hub.py) as Duel's MIDI when Web MIDI isn't there: on PianoDeck's plain
// http page (Chrome allows Web MIDI only on secure pages) the piano and FP10 Lights are on the Push, reached over
// Wi-Fi through the page's own server (/hub). Same protocol as tablet/fp10-bridge.js:
//
//   from the hub  {"type":"hello"|"sources", "sources":[...], "outputs":[...]}, {"type":"midi","src","data"},
//                 {"type":"pong","t"}
//   to the hub    {"type":"midi","to":<output>,"data":[...]}, {"type":"ping","t"}
//
// Wi-Fi adds delay before a note arrives, and Duel judges hits to ±80 ms, so each note is stamped with its arrival
// time less half the measured ping round trip (smoothed, at most MAX_ONE_WAY_MS). A Push that reboots never
// closes its socket, so after two silent pings it reconnects. No DOM: `makeSocket` and `now` are passed in, so
// node --test can drive it.

export const HEARTBEAT_MS = 5000;
export const RETRY_MS = 2000;
export const MAX_ONE_WAY_MS = 150;
const LIGHTS = /FP10 Lights/i;

export class Hub {
  // The timer defaults are wrapped: the browser's setInterval & co. throw "Illegal invocation" when called as
  // methods of another object (this.setTimer(...)).
  constructor({ url, makeSocket, now, onMidi, onState,
                setTimer = (fn, ms) => setInterval(fn, ms), clearTimer = (id) => clearInterval(id),
                later = (fn, ms) => setTimeout(fn, ms), cancel = (id) => clearTimeout(id) }) {
    Object.assign(this, { url, makeSocket, now, onMidi, onState, setTimer, clearTimer, later, cancel });
    this.ws = null;
    this.lights = null;     // the hub's name for the strip, when it has one
    this.sources = [];      // the instruments the hub reads (the FP-10 and others)
    this.rttMs = null;      // smoothed ping round trip
    this.closed = false;
  }

  get oneWayMs() { return this.rttMs === null ? 0 : Math.min(MAX_ONE_WAY_MS, this.rttMs / 2); }
  get open() { return !!this.ws && this.ws.readyState === 1; }

  connect() {
    if (this.closed) return;
    const ws = (this.ws = this.makeSocket(this.url));
    this.heard = this.now();
    this.state();
    this.beat = this.setTimer(() => {
      if (this.ws !== ws || ws.readyState !== 1) return;
      if (this.now() - this.heard > 2 * HEARTBEAT_MS) return this.lost(ws);
      ws.send(JSON.stringify({ type: 'ping', t: this.now() }));
    }, HEARTBEAT_MS);
    ws.onopen = () => {
      this.heard = this.now();
      ws.send(JSON.stringify({ type: 'ping', t: this.now() }));
      this.state();
    };
    ws.onmessage = (e) => this.message(ws, e.data);
    ws.onclose = () => this.lost(ws);
    ws.onerror = () => {};
  }

  message(ws, text) {
    if (this.ws !== ws) return;
    const arrived = this.now();
    this.heard = arrived;
    let msg;
    try { msg = JSON.parse(text); } catch (e) { return; }
    if (msg.type === 'midi' && Array.isArray(msg.data)) {
      this.onMidi(msg.data, arrived - this.oneWayMs, msg.src);
    } else if (msg.type === 'hello' || msg.type === 'sources') {
      this.lights = (msg.outputs || []).find((n) => LIGHTS.test(n)) || null;
      this.sources = (msg.sources || []).slice();
      this.state();
    } else if (msg.type === 'pong' && typeof msg.t === 'number') {
      const rtt = arrived - msg.t;
      if (rtt >= 0 && rtt < 5000) this.rttMs = this.rttMs === null ? rtt : 0.7 * this.rttMs + 0.3 * rtt;
    }
  }

  lost(ws) {
    if (this.ws !== ws) return;
    this.clearTimer(this.beat);
    try { ws.close(); } catch (e) { /* gone */ }
    this.ws = null;
    this.lights = null;
    this.sources = [];
    this.state();
    if (!this.closed) this.retry = this.later(() => this.connect(), RETRY_MS);
  }

  // Raw MIDI to the strip; false when there's no strip to send to.
  send(data) {
    if (!this.open || !this.lights) return false;
    this.ws.send(JSON.stringify({ type: 'midi', to: this.lights, data }));
    return true;
  }

  close() {
    this.closed = true;
    this.cancel(this.retry);
    this.clearTimer(this.beat);
    const ws = this.ws;
    this.ws = null;
    try { ws && ws.close(); } catch (e) { /* gone */ }
  }

  state() {
    this.onState({ open: this.open, connecting: !!this.ws && this.ws.readyState === 0, lights: this.lights,
                   sources: this.sources.slice(), oneWayMs: this.oneWayMs });
  }
}
