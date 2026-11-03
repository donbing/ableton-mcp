// FP10 Lights bridge for NeoKeys (tablet/neokeys, untouched upstream).
//
// serve.ps1 loads this after NeoKeys' own script. It wraps a few of NeoKeys'
// global functions and reads its `state`, and talks to the strip on its own:
//
//   ch 1  your playing, echoed from the piano (blue, fades)
//   ch 2  hints: the notes to play, dim while they approach, full when due
//   ch 3  correct (green flash) when practice mode credits a note
//   ch 4  wrong (red flash) when practice mode penalises one
//
// NeoKeys itself sends the song to every MIDI output on channel 1. That's kept
// for the piano, but the strip is taken out of that list so the song doesn't
// light up as if you played it.
//
// With the piano and the strip on the Push instead, both go through the Push's
// MIDI hub (MCP_Server/midi_hub.py) over Wi-Fi: the piano's notes are fed to
// NeoKeys as if they came from Web MIDI, and the strip's messages go back the
// same way. From localhost (serve.ps1) it goes straight to push.local; from any
// other http:// server (PianoDeck on moo) through that server's /hub relay, as
// Chrome won't let such a page connect to another machine on the LAN.
// ?hub=ws://host:port picks the hub, ?hub=off skips it.
(() => {
  'use strict';

  const LIGHTS = /FP10 Lights/i;
  const HUB_URL = new URLSearchParams(location.search).get('hub') ||
    (location.hostname === 'localhost' ? 'ws://push.local:8766' : 'ws://' + location.host + '/hub');
  const HUB_SKIP = /Ableton Push 3/;   // the Push's pads aren't piano keys
  const LOOKAHEAD_MS = 1200;           // real time a hint shows before its note
  const HINT_LEVELS = [20, 45, 80];    // velocities from far to near; 127 = due now

  // Everything we touch in NeoKeys. If an update renames one, the badge says so.
  const HOOKS = ['initMIDI', 'onMIDIMessage', 'awardHit', 'awardMiss', 'sendHardwareNoteOn', 'sendHardwareNoteOff',
                 'sendHardwarePedal', 'allHardwareNotesOff', 'shouldPauseForHand'];
  const missing = HOOKS.filter(name => typeof window[name] !== 'function');
  if (typeof state === 'undefined' || !state.notes || !state.waitingFor) missing.push('state');
  if (typeof midiOutputs === 'undefined') missing.push('midiOutputs');

  const badge = document.createElement('div');
  badge.id = 'fp10Badge';
  badge.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:9999;padding:4px 10px;' +
    'border-radius:999px;font:12px system-ui,sans-serif;color:#fff;background:#555;opacity:.85;pointer-events:none';
  document.body.appendChild(badge);

  // What the badge says, for pages with their own status display (PianoDeck's start card): it's sent as an
  // `fp10-status` event on window on every change, and window.fp10Status() returns the latest.
  //   lights: 'usb' | 'push' | null   hub: 'off' | 'connecting' | 'open'   pianos: the hub's instruments
  const status = { lights: null, hub: 'off', pianos: [], problem: null, text: '' };
  window.fp10Status = () => ({ ...status, pianos: [...status.pianos] });
  const announce = () => window.dispatchEvent(new CustomEvent('fp10-status', { detail: window.fp10Status() }));
  const showBadge = (text, colour) => {
    badge.textContent = status.text = text;
    badge.style.background = colour;
    announce();
  };

  if (missing.length) {
    status.problem = 'NeoKeys changed (' + missing.join(', ') + ')';
    showBadge('FP10 bridge off: NeoKeys changed (' + missing.join(', ') + ')', '#b03040');
    console.warn('[fp10] NeoKeys hooks missing:', missing);
    return;
  }
  showBadge('FP10 Lights: press Start', '#555');

  let lights = [];                     // MIDIOutput ports of the strip
  let hub = null, hubLights = null;    // the Push's hub socket, and its name for the strip
  const lit = new Map();               // hint note -> velocity sent on ch 2

  const send = (bytes) => {
    for (const out of lights) {
      try { out.send(bytes); } catch (e) { /* unplugged */ }
    }
    if (hubLights && hub.readyState === WebSocket.OPEN) {
      hub.send(JSON.stringify({ type: 'midi', to: hubLights, data: bytes }));
    }
  };
  const haveLights = () => lights.length > 0 || hubLights !== null;

  const showStatus = () => {
    status.lights = lights.length ? 'usb' : hubLights ? 'push' : null;
    status.hub = !hub ? 'off' : hub.readyState === WebSocket.OPEN ? 'open' : 'connecting';
    if (lights.length) showBadge('FP10 Lights connected', '#2d8a4e');
    else if (hubLights) showBadge('FP10 Lights on the Push', '#2d8a4e');
    else if (hub && hub.readyState === WebSocket.OPEN) showBadge('Push hub: FP10 Lights not found', '#a06a10');
    else showBadge('FP10 Lights not found', '#a06a10');
  };

  // ---- keep the strip out of NeoKeys' song pass-through ----
  const withoutLights = (fn) => function (...args) {
    midiOutputs = midiOutputs.filter(out => !LIGHTS.test(out.name || ''));
    return fn.apply(this, args);
  };
  for (const name of ['sendHardwareNoteOn', 'sendHardwareNoteOff', 'sendHardwarePedal', 'allHardwareNotesOff']) {
    window[name] = withoutLights(window[name]);
  }

  // ---- right / wrong flashes ----
  const origHit = window.awardHit, origMiss = window.awardMiss;
  window.awardHit = function (midi) {
    send([0x92, midi & 0x7f, 127]);
    return origHit.apply(this, arguments);
  };
  window.awardMiss = function (midi) {
    send([0x93, midi & 0x7f, 127]);
    return origMiss.apply(this, arguments);
  };

  // ---- echo the piano to channel 1 ----
  const echo = (e) => {
    if (hubPlays && e.source !== 'hub') return;  // the hub's copy is echoed instead
    const [status, d1, d2] = e.data;
    const cmd = status & 0xf0;
    if (cmd === 0x90 || cmd === 0x80) send([cmd, d1, d2]);
    else if (cmd === 0xb0 && d1 === 64) send([0xb0, 64, d2]);
  };

  const scan = (access) => {
    lights = [...access.outputs.values()].filter(out => LIGHTS.test(out.name || ''));
    for (const input of access.inputs.values()) {
      input.removeEventListener('midimessage', echo);
      if (!LIGHTS.test(input.name || '')) input.addEventListener('midimessage', echo);
    }
    lit.clear();                       // a replugged board starts dark
    showStatus();
  };

  // ---- the Push's hub: the piano in, the strip out ----
  // Its messages reach NeoKeys as { data, source: 'hub' }. While the hub has an
  // instrument, the same piano may also come by Bluetooth (PianoDeck) or USB:
  // only the hub's copy is played then. Wrappers outside this one (PianoDeck's
  // perf recorder) still see both, to time one against the other.
  const playable = (src) => !HUB_SKIP.test(src) && !LIGHTS.test(src);
  let hubPlays = false;
  const origMidi = window.onMIDIMessage;
  window.onMIDIMessage = function (e) {
    if (hubPlays && e.source !== 'hub') return;
    return origMidi.apply(this, arguments);
  };

  // window.fp10Hub.ping() resolves to the round trip to the hub in ms (null when it isn't connected)
  const pings = new Map();             // t -> resolve
  window.fp10Hub = {
    ping() {
      if (!hub || hub.readyState !== WebSocket.OPEN) return Promise.resolve(null);
      const t = performance.now();
      return new Promise((resolve) => {
        pings.set(t, resolve);
        hub.send(JSON.stringify({ type: 'ping', t }));
        setTimeout(() => { if (pings.delete(t)) resolve(null); }, 5000);
      });
    },
  };

  const connectHub = () => {
    const ws = new WebSocket(HUB_URL);
    hub = ws;
    showStatus();
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (err) { return; }
      if (msg.type === 'hello' || msg.type === 'sources') {
        const name = (msg.outputs || []).find(n => LIGHTS.test(n)) || null;
        if (name !== hubLights) lit.clear();   // a replugged board starts dark
        hubLights = name;
        status.pianos = (msg.sources || []).filter(playable);
        hubPlays = status.pianos.length > 0;
        showStatus();
      } else if (msg.type === 'midi' && playable(msg.src)) {
        const e = { data: msg.data, source: 'hub' };
        window.onMIDIMessage(e);               // NeoKeys' own Web MIDI handler
        echo(e);
      } else if (msg.type === 'pong' && pings.has(msg.t)) {
        const resolve = pings.get(msg.t);
        pings.delete(msg.t);
        resolve(performance.now() - msg.t);
      }
    };
    ws.onclose = () => {
      if (hub !== ws) return;
      hubLights = null;
      hubPlays = false;
      status.pianos = [];
      showStatus();
      setTimeout(connectHub, 2000);            // the Push asleep or the hub not started yet
    };
  };

  // NeoKeys asks for MIDI when Start is pressed; ask for our own access then.
  let started = false;
  const start = async () => {
    if (started) return;
    started = true;
    if (HUB_URL !== 'off') connectHub();
    if (!navigator.requestMIDIAccess) return;
    try {
      const access = await navigator.requestMIDIAccess({ sysex: false });
      scan(access);
      access.addEventListener('statechange', () => scan(access));
    } catch (e) {
      showBadge('FP10 Lights: MIDI blocked', '#b03040');
    }
  };
  const origInit = window.initMIDI;
  window.initMIDI = async function () {
    await origInit.apply(this, arguments);
    await start();
  };
  // PianoDeck starts NeoKeys by itself when sound is already allowed, which can
  // be before this script has loaded.
  if (typeof appStarted !== 'undefined' && appStarted) start();

  // ---- hints, worked out each frame from NeoKeys' state ----
  const wanted = () => {
    const want = new Map();
    if (state.mode === 'freeplay' || !state.notes.length) return want;
    const now = state.songTime;
    const ahead = LOOKAHEAD_MS * (state.speed || 1);
    const mine = (n) => state.mode === 'practice' ? shouldPauseForHand(n.hand)
                                                  : (state.hand === 'both' || state.hand === n.hand);
    const raise = (midi, v) => { if ((want.get(midi) || 0) < v) want.set(midi, v); };

    for (const midi of state.waitingFor) raise(midi, 127);
    for (const n of state.notes) {
      if (n.startMs > now + ahead) break;  // notes are sorted by start
      if (!mine(n)) continue;
      if (n.startMs > now) {
        if (n.triggered) continue;         // already played or being waited for
        const near = 1 - (n.startMs - now) / ahead;
        raise(n.midi, HINT_LEVELS[Math.min(HINT_LEVELS.length - 1, Math.floor(near * HINT_LEVELS.length))]);
      } else if (state.mode === 'normal' && now < n.endMs) {
        raise(n.midi, 127);                // the demo is playing it now
      }
    }
    return want;
  };

  const frame = () => {
    if (haveLights()) {
      const want = wanted();
      for (const [midi] of lit) {
        if (!want.has(midi)) { send([0x81, midi, 0]); lit.delete(midi); }
      }
      for (const [midi, v] of want) {
        if (lit.get(midi) !== v) { send([0x91, midi, v]); lit.set(midi, v); }
      }
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  window.addEventListener('pagehide', () => {
    for (const [midi] of lit) send([0x81, midi, 0]);
    lit.clear();
  });
})();
