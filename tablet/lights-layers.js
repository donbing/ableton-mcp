// While NeoKeys is open, the strip shows NeoKeys' hints and flashes, and only the extras you choose on top.
//
// FP10 Lights normally also lights your playing (blue, violet below the split) and throws sparks, set on the
// board for Live. In NeoKeys that sits on top of the hints and gets confusing, so this adds a "Lights" section to
// the settings with three switches, off to start with: show my playing, sparks, left-hand colour. They become the
// board's layers (CC114 on channel 16, see firmware/fp10_lights/README.md), which aren't saved on the board and
// lapse back to everything after 2 minutes, so this re-sends them every minute while the page is in view, and
// puts everything back when you leave. Needs fp10-bridge.js (window.fp10Lights); without it, does nothing.
(() => {
  'use strict';
  const panel = document.getElementById('panel');
  if (!panel || !window.fp10Lights || typeof window.fp10Lights.send !== 'function') {
    console.warn('[lights-layers] no settings panel or FP10 bridge; off');
    return;
  }

  const L = { PLAY: 1, SPARKS: 2, LEFT: 4, HINT: 8, FLASH: 16, ALL: 31 };
  const SWITCHES = [
    { bit: L.PLAY, label: 'Show my playing', hint: 'Light the keys you press (blue)' },
    { bit: L.SPARKS, label: 'Sparks', hint: 'If sparks are on for the strip' },
    { bit: L.LEFT, label: 'Left-hand colour', hint: 'Violet below the split, if set' },
  ];
  const KEY = 'neokeys.lightsLayers.v1';
  let extras = 0;                                  // which of PLAY / SPARKS / LEFT to show on top
  try { extras = +(localStorage.getItem(KEY) || 0) & (L.PLAY | L.SPARKS | L.LEFT); } catch (e) { extras = 0; }

  const mask = () => L.HINT | L.FLASH | extras;
  const sendLayers = (value) => window.fp10Lights.send([0xBF, 114, value]);
  let timer = null;
  const apply = () => {
    clearInterval(timer);
    timer = null;
    if (document.hidden) { sendLayers(L.ALL); return; }  // NeoKeys out of view: the strip is the board's again
    sendLayers(mask());
    if (mask() !== L.ALL) timer = setInterval(() => sendLayers(mask()), 60000);   // the board lapses after 2 min
  };

  // ---- settings section, placed before panel-folds.js runs (it files "Lights" under Display) ----
  const h3 = document.createElement('h3');
  h3.style.marginTop = '10px';
  h3.textContent = 'Lights';
  panel.appendChild(h3);
  for (const s of SWITCHES) {
    const row = document.createElement('div');
    row.className = 'toggle-row';
    row.style.marginTop = '6px';
    row.innerHTML = '<span class="toggle-label"><span class="ll-name"></span><span class="hint"></span></span>' +
      '<label class="switch"><input type="checkbox"><span class="slider-track"></span></label>';
    row.querySelector('.ll-name').textContent = s.label;
    row.querySelector('.hint').textContent = s.hint;
    const box = row.querySelector('input');
    box.checked = !!(extras & s.bit);
    box.addEventListener('change', () => {
      extras = box.checked ? extras | s.bit : extras & ~s.bit;
      try { localStorage.setItem(KEY, String(extras)); } catch (e) { /* ignore */ }
      apply();
    });
    panel.appendChild(row);
  }

  // Send when the strip turns up (Start, a replug, the hub reconnecting), when the page shows or hides, and put
  // everything back on the way out.
  window.addEventListener('fp10-status', (e) => { if (e.detail && e.detail.lights) apply(); });
  document.addEventListener('visibilitychange', apply);
  window.addEventListener('pagehide', () => { clearInterval(timer); sendLayers(L.ALL); });
  apply();
})();
