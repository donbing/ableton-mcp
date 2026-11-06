// Fold NeoKeys' settings panel into a few sections (tablet/neokeys stays untouched upstream).
//
// serve.ps1 loads this last. It moves the panel's existing headings and controls into folding sections
// (Play open, Sound / Display / Advanced folded); the elements themselves, their ids and their handlers
// are unchanged, only their parent. Each section remembers whether it was open. A heading it doesn't know
// goes into Advanced; if the panel isn't there, it does nothing.
(() => {
  'use strict';
  const panel = document.getElementById('panel');
  if (!panel || !panel.querySelector(':scope > h3')) return;

  const GROUPS = [
    { id: 'play', title: 'Play', open: true,
      headings: ['tracks', 'midi file', 'mode', 'practice hands', 'speed'] },
    { id: 'sound', title: 'Sound', open: false, headings: ['volume', 'sound engine'] },
    { id: 'display', title: 'Display', open: false, headings: ['note naming', 'falling notes'] },
    { id: 'advanced', title: 'Advanced', open: false, headings: [] },   // timeline, hand split, anything new
  ];
  const groupOf = (heading) => {
    const h = heading.trim().toLowerCase();
    return GROUPS.find(g => g.headings.includes(h)) || GROUPS[GROUPS.length - 1];
  };

  // Split the panel into sections: each <h3> with everything after it up to the next <h3>.
  const sections = [];
  let lead = [];                                   // anything before the first heading stays on top
  for (const el of [...panel.children]) {
    if (el.tagName === 'H3') sections.push({ heading: el.textContent, nodes: [el] });
    else if (sections.length) sections[sections.length - 1].nodes.push(el);
    else lead.push(el);
  }

  const style = document.createElement('style');
  style.textContent = `
    #panel details.pf-group{border-top:1px solid var(--panel-border);padding:2px 0}
    #panel details.pf-group:first-of-type{border-top:0}
    #panel details.pf-group > summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;
      padding:8px 2px;font-size:13px;font-weight:700;letter-spacing:.02em;color:var(--text);user-select:none}
    #panel details.pf-group > summary::-webkit-details-marker{display:none}
    #panel details.pf-group > summary::before{content:'▸';color:var(--text-dim);font-size:11px;width:10px}
    #panel details.pf-group[open] > summary::before{content:'▾'}
    #panel details.pf-group > summary:hover{color:var(--accent)}
    #panel details.pf-group > .pf-body{padding:0 0 8px}
    #panel details.pf-group > .pf-body > h3:first-child{margin-top:0 !important}`;
  document.head.appendChild(style);

  const KEY = 'neokeys.panelFolds.v1';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }

  const bodies = new Map();
  for (const g of GROUPS) {
    const details = document.createElement('details');
    details.className = 'pf-group';
    details.dataset.group = g.id;
    details.open = g.id in saved ? !!saved[g.id] : g.open;
    const summary = document.createElement('summary');
    summary.textContent = g.title;
    const body = document.createElement('div');
    body.className = 'pf-body';
    details.append(summary, body);
    details.addEventListener('toggle', () => {
      saved[g.id] = details.open;
      try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { /* ignore */ }
    });
    bodies.set(g, { details, body });
  }

  // Play keeps its own order (Tracks, MIDI File, Mode, Hands, Speed); the others keep the panel's order.
  const play = GROUPS[0];
  const key = s => s.heading.trim().toLowerCase();
  for (const h of play.headings) {
    for (const s of sections) if (key(s) === h) bodies.get(play).body.append(...s.nodes);
  }
  for (const s of sections) {
    const g = groupOf(s.heading);
    if (g !== play) bodies.get(g).body.append(...s.nodes);
  }

  for (const g of GROUPS) {
    const { details, body } = bodies.get(g);
    if (body.childElementCount) panel.appendChild(details);
  }
  // Keep anything that sat above the first heading at the top.
  for (const el of lead.reverse()) panel.prepend(el);
})();
