// "Claude me" lessons for NeoKeys (tablet/neokeys, untouched upstream).
//
// serve.ps1 loads this after NeoKeys (and fp10-bridge.js). It adds a Lessons tab: "Claude me" sends a
// short summary of the loaded song (key, chords per bar, sections, hands; never the notes) to
// serve.ps1's /api/claude-me/plan, which asks Claude for a lesson plan. Each lesson is built here
// from the song's own notes as a .mid (MidiWriterJS), loaded into NeoKeys and run in practice mode;
// the end-of-song screen then says whether it passed and offers the next step. Plans, progress and
// per-bar results are kept in localStorage; "Review" downloads them as JSON.
//
// Without a key (or offline) "Quick plan" makes a plan here from the same summary.
(() => {
  'use strict';

  // ---------------------------------------------------------------- hooks
  const HOOKS = ['loadMidiObject', 'showVictoryOverlay', 'hideVictoryOverlay', 'setTracksTab', 'setMode',
                 'setHand', 'awardHit', 'awardMiss', 'restartCurrentSong', 'initAudio', 'showToast',
                 'arrayBufferToBase64', 'base64ToArrayBuffer'];
  const missing = HOOKS.filter(name => typeof window[name] !== 'function');
  if (typeof state === 'undefined' || !Array.isArray(state.notes) || !state.practiceStats) missing.push('state');
  if (typeof Midi !== 'function') missing.push('Midi');
  if (typeof MidiWriter === 'undefined' || !MidiWriter.Track) missing.push('MidiWriter');
  if (typeof Tonal === 'undefined' || !Tonal.Key) missing.push('Tonal');
  const tabsRow = document.querySelector('.tracks-tabs');
  const panelRecentEl = document.getElementById('panelRecent');
  if (!tabsRow || !panelRecentEl) missing.push('tracks tabs');
  if (missing.length) {
    console.warn('[claude-me] NeoKeys hooks missing, lessons off:', missing);
    return;
  }
  const { Key, Chord, Note } = Tonal;

  // ---------------------------------------------------------------- storage
  const STORE_KEY = 'neokeys.claudeMe.v1';
  const load = () => {
    try { const v = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); return v && v.songs ? v : { songs: {} }; }
    catch (e) { return { songs: {} }; }
  };
  const save = (db) => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(db)); return true; }
    catch (e) { toast('Storage full: lessons not saved', 'err'); return false; }
  };
  const toast = (msg, kind) => { try { showToast(msg, kind); } catch (e) { /* ignore */ } };

  // ---------------------------------------------------------------- the loaded song
  let current = null;          // { midi, title }: the last song NeoKeys loaded that isn't a lesson
  let lesson = null;           // the lesson now loaded: { fp, id, bpm, barMs, b0, nBars, log: [] }
  let loadingLesson = false;

  const origLoad = window.loadMidiObject;
  window.loadMidiObject = function (midi) {
    if (!loadingLesson) {
      current = { midi, title: state.currentTrackTitle || midi.name || 'Song' };
      lesson = null;
      renderPanel();
    }
    return origLoad.apply(this, arguments);
  };

  // A song's id. crypto.subtle exists only on secure pages (https, localhost); pianodeck is plain http on the
  // LAN, so there a fast 53-bit hash (cyrb53) does: it only has to tell songs apart.
  const sha256 = async (bytes) => {
    if (window.crypto && crypto.subtle) {
      const d = await crypto.subtle.digest('SHA-256', bytes);
      return 'sha256:' + [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
    }
    let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
    for (const b of bytes) { h1 = Math.imul(h1 ^ b, 2654435761); h2 = Math.imul(h2 ^ b, 1597334677); }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return 'cyrb53:' + (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16) + '-' + bytes.length;
  };

  // ---------------------------------------------------------------- analysis
  const FLATS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  const SHARPS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

  // Song shape shared by analysis and lesson building: ticks at the file's resolution, hands as
  // NeoKeys assigns them (a track named left/bass, else the lower of two tracks, else split at C4).
  function songShape(midi) {
    const ppq = midi.header.ppq;
    const ts = (midi.header.timeSignatures[0] || { timeSignature: [4, 4] }).timeSignature;
    const [num, den] = ts;
    const barTicks = ppq * num * 4 / den;
    const bpm = (midi.header.tempos[0] || { bpm: 120 }).bpm;
    const tracks = midi.tracks.filter(t => t.notes.length);
    const avg = t => t.notes.reduce((s, n) => s + n.midi, 0) / t.notes.length;
    let lhTrack = null;
    if (tracks.length >= 2) {
      lhTrack = tracks.find(t => /left|bass|l\.h|lh/i.test(t.name || '')) ||
                (tracks.some(t => /right|treble|r\.h|rh|melody/i.test(t.name || '')) ? null
                  : [...tracks].sort((a, b) => avg(a) - avg(b))[0]);
    }
    const notes = [];
    for (const t of tracks) for (const n of t.notes) {
      notes.push({ midi: n.midi, tick: n.ticks, dur: Math.max(1, n.durationTicks), vel: n.velocity,
                   hand: tracks.length >= 2 ? (t === lhTrack ? 'lh' : 'rh') : (n.midi < 60 ? 'lh' : 'rh') });
    }
    notes.sort((a, b) => a.tick - b.tick || a.midi - b.midi);
    const end = notes.length ? Math.max(...notes.map(n => n.tick + n.dur)) : 0;
    return { ppq, num, den, barTicks, bpm, notes, bars: Math.max(1, Math.ceil(end / barTicks)), lhTrack };
  }

  function findKey(shape, midi) {
    // Krumhansl-Kessler: correlate the duration-weighted pitch classes with each key's profile.
    const MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
    const MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];
    const w = new Array(12).fill(0);
    for (const n of shape.notes) w[n.midi % 12] += n.dur;
    const corr = (prof, t) => {
      const p = prof.map((_, i) => prof[(i - t + 12) % 12]);
      const mw = w.reduce((a, b) => a + b, 0) / 12, mp = p.reduce((a, b) => a + b, 0) / 12;
      let num = 0, dw = 0, dp = 0;
      for (let i = 0; i < 12; i++) { num += (w[i] - mw) * (p[i] - mp); dw += (w[i] - mw) ** 2; dp += (p[i] - mp) ** 2; }
      return num / Math.sqrt(dw * dp || 1);
    };
    let best = null;
    for (let t = 0; t < 12; t++) {
      for (const minor of [false, true]) {
        const score = corr(minor ? MINOR : MAJOR, t);
        if (!best || score > best.score) best = { tonic: minor ? SHARPS[t] : FLATS[t], minor, score };
      }
    }
    // Many files carry a default "C major" key signature; believe the file only when the notes agree.
    const ks = midi.header.keySignatures[0];
    if (ks && ks.key) {
      const t = Note.chroma(ks.key), minor = ks.scale === 'minor';
      if (t >= 0 && corr(minor ? MINOR : MAJOR, t) >= best.score - 0.05) return { tonic: ks.key, minor, from: 'key signature' };
      return { tonic: best.tonic, minor: best.minor, from: 'notes (file says ' + ks.key + ' ' + ks.scale + ')' };
    }
    return { tonic: best.tonic, minor: best.minor, from: 'notes' };
  }

  function analyse(midi, title) {
    const shape = songShape(midi);
    const { notes, barTicks, bars } = shape;
    const key = findKey(shape, midi);
    const K = key.minor ? Key.minorKey(key.tonic) : Key.majorKey(key.tonic);
    const NAMES = K.alteration < 0 ? FLATS : SHARPS;
    const nameOf = m => NAMES[m % 12] + (Math.floor(m / 12) - 1);

    // Chords: per half bar, fit the key's chords to the duration-weighted pitch classes.
    const names = key.minor
      ? [...K.natural.triads, K.harmonic.triads[4], K.harmonic.chords[4]]
      : [...K.triads, K.chords[4], ...K.secondaryDominants.filter(Boolean)];
    const diatonic = new Set(key.minor ? K.natural.triads : K.triads);
    const candidates = [...new Set(names)].map(name => {
      const c = Chord.get(name);
      return { name, pcs: c.notes.map(Note.chroma), root: Note.chroma(c.tonic) };
    }).filter(c => c.pcs.length >= 3);
    const chordAt = (from, to) => {
      const sounding = notes.filter(n => n.tick < to && n.tick + n.dur > from);
      if (!sounding.length) return '-';
      const w = new Array(12).fill(0);
      for (const n of sounding) {
        const ov = Math.min(to, n.tick + n.dur) - Math.max(from, n.tick);
        w[n.midi % 12] += ov * (n.tick >= from ? 1.5 : 1);
      }
      const bass = sounding.filter(n => n.hand === 'lh').sort((a, b) => a.midi - b.midi)[0] ||
                   [...sounding].sort((a, b) => a.midi - b.midi)[0];
      const total = w.reduce((a, b) => a + b, 0);
      let pick = null;
      for (const c of candidates) {
        const score = c.pcs.reduce((s, pc) => s + w[pc], 0) / total - 0.08 * (c.pcs.length - 3)
          + (bass.midi % 12 === c.root ? 0.15 : 0) - (diatonic.has(c.name) ? 0 : 0.06);
        if (!pick || score > pick.score) pick = { ...c, score };
      }
      return pick.name + (bass.midi % 12 !== pick.root ? '/' + NAMES[bass.midi % 12] : '');
    };
    const chordsPerBar = [];
    for (let b = 0; b < bars; b++) {
      const a = chordAt(b * barTicks, b * barTicks + barTicks / 2);
      const c = chordAt(b * barTicks + barTicks / 2, (b + 1) * barTicks);
      chordsPerBar.push(a === c ? a : a + ' ' + c);
    }

    // Sections: phrases of about 16 beats (4 bars of 4/4, 8 of 3/8) compared by the right hand's top line.
    // The grid is shifted by up to a phrase so a pickup or intro doesn't hide the repeats; the shift that
    // finds the fewest different phrases wins, and bars before it become an intro.
    const barSig = b => {
      const top = new Map();
      for (const n of notes) if (n.hand === 'rh' && n.tick >= b * barTicks && n.tick < (b + 1) * barTicks)
        top.set(n.tick, Math.max(top.get(n.tick) || 0, n.midi));
      // Onsets on a 24-step grid, so a performed (unquantised) repeat still matches.
      return [...top].map(([t, m]) => Math.round((t - b * barTicks) * 24 / barTicks) + ':' + m).join(',');
    };
    const sigs = Array.from({ length: bars }, (_, b) => barSig(b));
    const quarters = shape.num * 4 / shape.den;
    const phrase = Math.max(2, Math.min(16, Math.round(16 / quarters)));
    const labelFor = i => i < 26 ? String.fromCharCode(65 + i) : 'S' + (i + 1);
    const sectionsAt = (offset) => {
      const seen = [], out = [];
      if (offset > 0) out.push({ label: 'intro', bars: [1, offset] });
      for (let b = offset; b < bars; b += phrase) {
        const p = sigs.slice(b, Math.min(bars, b + phrase));
        let label = null;
        for (const s of seen) {
          const same = p.filter((x, i) => x === s.p[i]).length;
          if (same === p.length && p.length === s.p.length) { label = s.label; break; }
          if (p.length > 1 && same >= p.length - Math.max(1, Math.floor(p.length / 4))) { label = s.label + "'"; break; }
        }
        if (!label) { label = labelFor(seen.length); seen.push({ p, label }); }
        out.push({ label, bars: [b + 1, Math.min(bars, b + phrase)] });
      }
      return { out, distinct: seen.length };
    };
    let pick = null;
    for (let off = 0; off < Math.min(phrase, bars); off++) {
      const r = sectionsAt(off);
      if (!pick || r.distinct < pick.distinct) pick = r;
    }
    const sections = pick.out;

    const hand = h => {
      const m = notes.filter(n => n.hand === h).map(n => n.midi);
      return { notes: m.length, range: m.length ? [nameOf(Math.min(...m)), nameOf(Math.max(...m))] : null };
    };
    const busy = Array.from({ length: bars }, (_, b) => {
      const inBar = notes.filter(n => n.tick >= b * barTicks && n.tick < (b + 1) * barTicks);
      const on = h => new Set(inBar.filter(n => n.hand === h).map(n => n.tick)).size;
      return [on('rh'), on('lh')];
    });
    return {
      title, meter: shape.num + '/' + shape.den, bpm: Math.round(shape.bpm), bars,
      key: key.tonic + (key.minor ? ' minor' : ' major'), keyFrom: key.from,
      hands: { source: shape.lhTrack ? 'tracks' : (midi.tracks.filter(t => t.notes.length).length >= 2 ? 'tracks (named)' : 'split at C4'),
               rh: hand('rh'), lh: hand('lh') },
      form: sections.map(s => s.label).join(' '), sections, chordsPerBar,
      onsetsPerBar: { note: '[right hand, left hand] note onsets in each bar', bars: busy },
    };
  }

  // ---------------------------------------------------------------- plans
  const TRANSFORMS = ['original', 'melody', 'block_chords', 'melody_and_chords'];
  const clamp = (v, lo, hi, d) => Number.isFinite(+v) ? Math.min(hi, Math.max(lo, Math.round(+v))) : d;

  function normalisePlan(raw, summary) {
    const lessons = [];
    const ids = new Set();
    for (const l of (raw && Array.isArray(raw.lessons) ? raw.lessons : []).slice(0, 16)) {
      let [a, b] = Array.isArray(l.bars) ? l.bars : [1, summary.bars];
      a = clamp(a, 1, summary.bars, 1); b = clamp(b, a, summary.bars, summary.bars);
      let id = String(l.id || 'lesson').toLowerCase().replace(/[^a-z0-9-]+/g, '-').slice(0, 32) || 'lesson';
      while (ids.has(id)) id += '-2';
      ids.add(id);
      lessons.push({
        id, title: String(l.title || 'Bars ' + a + '-' + b).slice(0, 60), why: String(l.why || '').slice(0, 200),
        bars: [a, b], hand: ['lh', 'rh', 'both'].includes(l.hand) ? l.hand : 'both',
        transform: TRANSFORMS.includes(l.transform) ? l.transform : 'original',
        tempoPct: clamp(l.tempoPct, 40, 110, 70), loops: clamp(l.loops, 1, 4, 1),
        pass: { accuracyPct: clamp(l.pass && l.pass.accuracyPct, 60, 100, 85),
                maxWrong: clamp(l.pass && l.pass.maxWrong, 0, 50, 5) },
        onFail: ['repeat', 'slower', 'split_hands'].includes(l.onFail) ? l.onFail : 'repeat',
      });
    }
    if (!lessons.length) throw new Error('the plan had no lessons');
    return { version: 1, coach: String((raw && raw.coach) || '').slice(0, 400), lessons };
  }

  // A plan made here, without Claude: each new section's tune, chords and both, then the whole song.
  function quickPlan(summary) {
    // The first time each section appears, up to four sections, then the whole song.
    const firstOf = new Map();
    for (const s of summary.sections) {
      const base = s.label.replace(/'+$/, '');
      if (base !== 'intro' && !firstOf.has(base) && firstOf.size < 4) firstOf.set(base, s);
    }
    const lessons = [];
    for (const [label, s] of firstOf) {
      const k = label.toLowerCase();
      lessons.push({ id: k + '-tune', title: label + ' tune, right hand', why: 'Learn the melody first.',
        bars: s.bars, hand: 'rh', transform: 'melody', tempoPct: 60, loops: 2, pass: { accuracyPct: 90, maxWrong: 3 }, onFail: 'slower' });
      lessons.push({ id: k + '-chords', title: label + ' chords, left hand', why: 'Held block chords under the tune.',
        bars: s.bars, hand: 'lh', transform: 'block_chords', tempoPct: 60, loops: 2, pass: { accuracyPct: 85, maxWrong: 4 }, onFail: 'repeat' });
      lessons.push({ id: k + '-together', title: label + ' tune over chords', why: 'Both hands, simplified.',
        bars: s.bars, hand: 'both', transform: 'melody_and_chords', tempoPct: 60, loops: 1, pass: { accuracyPct: 85, maxWrong: 6 }, onFail: 'split_hands' });
    }
    const all = [1, summary.bars];
    lessons.push({ id: 'whole-rh', title: 'Whole song, right hand', why: 'As written.', bars: all, hand: 'rh',
      transform: 'original', tempoPct: 75, loops: 1, pass: { accuracyPct: 90, maxWrong: 6 }, onFail: 'slower' });
    lessons.push({ id: 'whole-lh', title: 'Whole song, left hand', why: 'As written.', bars: all, hand: 'lh',
      transform: 'original', tempoPct: 75, loops: 1, pass: { accuracyPct: 90, maxWrong: 6 }, onFail: 'slower' });
    lessons.push({ id: 'whole', title: 'Whole song, both hands', why: 'Put it together.', bars: all, hand: 'both',
      transform: 'original', tempoPct: 85, loops: 1, pass: { accuracyPct: 90, maxWrong: 8 }, onFail: 'split_hands' });
    return normalisePlan({ coach: 'Quick plan (made without Claude): each new section in small steps, then the whole song.', lessons }, summary);
  }

  // The history Claude sees: the last few runs of each lesson, scores only.
  function historyFor(song) {
    const out = [];
    for (const [id, p] of Object.entries(song.progress || {})) {
      for (const a of (p.attempts || []).slice(-3)) {
        out.push({ lesson: id, accuracyPct: a.accuracyPct, wrong: a.wrong, passed: a.passed, weakBars: a.weakBars });
      }
    }
    return out.slice(-30);
  }

  async function claudePlan(summary, history) {
    const res = await fetch('/api/claude-me/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ summary, history }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || ('HTTP ' + res.status));
    return body.plan;
  }

  // ---------------------------------------------------------------- lesson MIDI
  function buildLessonMidi(song, l) {
    const midi = new Midi(base64ToArrayBuffer(song.b64));
    const shape = songShape(midi);
    const PPQ = 128;                                  // MidiWriterJS' resolution
    const k = PPQ / shape.ppq;
    const barTicks = shape.barTicks * k;
    const [b0, b1] = l.bars;
    const from = (b0 - 1) * barTicks, to = b1 * barTicks, span = to - from;
    const all = shape.notes.map(n => ({ ...n, tick: Math.round(n.tick * k), dur: Math.max(1, Math.round(n.dur * k)) }));
    const inRange = all.filter(n => n.tick >= from && n.tick < to);

    const melody = () => {
      const top = new Map();
      for (const n of inRange) if (n.hand === 'rh' && (!top.has(n.tick) || top.get(n.tick).midi < n.midi)) top.set(n.tick, n);
      return [...top.values()].map(n => ({ ...n, dur: Math.min(n.dur, to - n.tick) }));
    };
    const blockChords = () => {
      const blocks = [];
      for (let b = b0; b <= b1; b++) {
        const parts = (song.summary.chordsPerBar[b - 1] || '-').split(' ');
        const pair = parts.length === 1 ? [parts[0], parts[0]] : parts;
        pair.forEach((c, i) => {
          const name = c.split('/')[0];
          const tick = (b - 1) * barTicks + i * barTicks / 2;
          const last = blocks[blocks.length - 1];
          if (last && last.name === name && name !== '-') last.dur += barTicks / 2;
          else blocks.push({ name, tick, dur: barTicks / 2 });
        });
      }
      let prev = [43, 47, 50];                        // G2 B2 D3
      const out = [];
      for (const blk of blocks) {
        if (blk.name === '-') continue;
        const pcs = Chord.get(blk.name).notes.slice(0, 3).map(Note.chroma);
        if (pcs.length < 3) continue;
        let best = null;
        for (let base = 40; base <= 52; base++) {     // lowest note E2..E3, top note below C4
          if (!pcs.includes(base % 12)) continue;
          const v = [base];
          let x = base;
          while (v.length < 3) { x++; if (pcs.includes(x % 12) && !v.some(m => m % 12 === x % 12)) v.push(x); }
          if (v[2] > 59) continue;
          const cost = v.reduce((s, m, i) => s + Math.abs(m - prev[i]), 0);
          if (!best || cost < best.cost) best = { v, cost };
        }
        if (!best) continue;
        prev = best.v;
        for (const m of best.v) out.push({ midi: m, tick: blk.tick, dur: Math.max(8, blk.dur - 8), vel: 0.7, hand: 'lh' });
      }
      return out;
    };
    const original = () => inRange.filter(n => l.hand === 'both' || n.hand === l.hand)
      .map(n => ({ ...n, dur: Math.min(n.dur, to - n.tick) }));
    const notes = { original, melody, block_chords: blockChords,
                    melody_and_chords: () => [...melody(), ...blockChords()] }[l.transform]();
    if (!notes.length) throw new Error('no notes for that hand in bars ' + b0 + '-' + b1);

    const bpm = Math.max(20, Math.round(shape.bpm * l.tempoPct / 100));
    const mk = (name) => { const t = new MidiWriter.Track(); t.addTrackName(name); t.setTempo(bpm); t.setTimeSignature(shape.num, shape.den); return t; };
    const tracks = { rh: mk('Right hand'), lh: mk('Left hand') };
    const placed = [];
    for (let i = 0; i < l.loops; i++) {
      for (const n of notes) {
        const startTick = n.tick - from + i * span;
        tracks[n.hand].addEvent(new MidiWriter.NoteEvent({
          pitch: [n.midi], duration: 'T' + n.dur, startTick,
          velocity: Math.max(30, Math.min(100, Math.round((n.vel || 0.7) * 100))),
        }));
        placed.push({ midi: n.midi, ms: startTick * 60000 / (bpm * PPQ), hand: n.hand });
      }
    }
    const used = ['rh', 'lh'].filter(h => notes.some(n => n.hand === h)).map(h => tracks[h]);
    const bytes = new MidiWriter.Writer(used).buildFile();
    return { bytes, bpm, barMs: (barTicks / PPQ) * 60000 / bpm, nBars: b1 - b0 + 1, placed };
  }

  async function startLesson(fp, lessonId, override) {
    const db = load();
    const song = db.songs[fp];
    const base = song && song.plan.lessons.find(x => x.id === lessonId);
    if (!base) { toast('Lesson not found', 'err'); return; }
    const l = { ...base, ...(override || {}) };
    let built;
    try { built = buildLessonMidi(song, l); }
    catch (e) { console.error(e); toast('Could not build the lesson: ' + e.message, 'err'); return; }
    await initAudio();
    const midi = new Midi(built.bytes);
    loadingLesson = true;
    try {
      state.currentTrackId = 'lesson:' + lessonId;
      state.currentTrackTitle = song.title + ' · ' + l.title;
      if (typeof fileNameEl !== 'undefined' && fileNameEl) fileNameEl.textContent = state.currentTrackTitle;
      origLoad(midi);
    } finally { loadingLesson = false; }
    // Keep each note in the hand the lesson put it in, whatever NeoKeys' guess or split slider said.
    const byKey = new Map();
    for (const p of built.placed) byKey.set(p.midi + '@' + Math.round(p.ms / 5), p.hand);
    for (const n of state.notes) {
      const h = byKey.get(n.midi + '@' + Math.round(n.startMs / 5));
      if (h) n.hand = h;
    }
    lesson = { fp, id: lessonId, lesson: l, bpm: built.bpm, barMs: built.barMs, b0: l.bars[0], nBars: built.nBars, log: [] };
    // The lesson's tempo is in the file, so the speed slider goes back to 1x.
    if (typeof speedSlider !== 'undefined' && speedSlider) { speedSlider.value = '1'; speedSlider.dispatchEvent(new Event('input')); }
    setMode('practice');
    setHand(l.hand);
    restartCurrentSong();
    lastDownload = { name: (song.title + '-' + lessonId).replace(/[^\w.-]+/g, '-') + '.mid', bytes: built.bytes };
    renderPanel();
    toast('🎓  ' + l.title + ' · ' + built.bpm + ' bpm', 'ok');
  }
  let lastDownload = null;

  // ---------------------------------------------------------------- scoring per bar
  // Practice mode stops the clock just before the notes it waits for (WAIT_LEAD_MS, 50 ms), so look a
  // little ahead or a chord on a downbeat counts in the bar before.
  const LEAD_MS = (typeof WAIT_LEAD_MS === 'number' ? WAIT_LEAD_MS : 50) + 20;
  const barOf = () => lesson
    ? lesson.b0 + (Math.floor(Math.max(0, state.songTime + LEAD_MS) / lesson.barMs) % lesson.nBars) : 0;
  const origHit = window.awardHit, origMiss = window.awardMiss;
  window.awardHit = function (midi) {
    if (lesson && state.mode === 'practice') lesson.log.push({ bar: barOf(), ok: true });
    return origHit.apply(this, arguments);
  };
  window.awardMiss = function (midi) {
    if (lesson && state.mode === 'practice') lesson.log.push({ bar: barOf(), ok: false });
    return origMiss.apply(this, arguments);
  };
  // A restart (rewind, "Try again") starts a fresh log.
  const origRestart = window.restartCurrentSong;
  window.restartCurrentSong = function () {
    if (lesson) lesson.log = [];
    return origRestart.apply(this, arguments);
  };

  function recordAttempt() {
    const s = state.practiceStats;
    const l = lesson.lesson;
    const accuracyPct = s.notesExpected ? Math.round(100 * s.notesHit / s.notesExpected) : 0;
    const passed = accuracyPct >= l.pass.accuracyPct && s.wrongNotes <= l.pass.maxWrong;
    const perBar = {};
    for (const e of lesson.log) {
      const b = perBar[e.bar] || (perBar[e.bar] = { hit: 0, wrong: 0 });
      if (e.ok) b.hit++; else b.wrong++;
    }
    const weakBars = Object.entries(perBar).filter(([, v]) => v.wrong > 0)
      .sort((a, b) => b[1].wrong - a[1].wrong).slice(0, 4).map(([bar]) => +bar);
    const attempt = {
      at: new Date().toISOString(), tempoPct: l.tempoPct, hand: l.hand, accuracyPct, wrong: s.wrongNotes,
      avgReactionMs: s.reactionCount ? Math.round(s.reactionSum / s.reactionCount) : null,
      notes: s.notesExpected, passed, weakBars, perBar,
    };
    const db = load();
    const song = db.songs[lesson.fp];
    if (song) {
      const p = song.progress[lesson.id] || (song.progress[lesson.id] = { attempts: [], passed: false, best: 0 });
      p.attempts.push(attempt);
      if (p.attempts.length > 20) p.attempts.splice(0, p.attempts.length - 20);
      p.passed = p.passed || passed;
      p.best = Math.max(p.best || 0, accuracyPct);
      save(db);
    }
    return { attempt, song };
  }

  // ---------------------------------------------------------------- end-of-song screen
  const origVictory = window.showVictoryOverlay;
  window.showVictoryOverlay = function () {
    const r = origVictory.apply(this, arguments);
    try { decorateVictory(); } catch (e) { console.warn('[claude-me] victory', e); }
    return r;
  };

  function decorateVictory() {
    const card = document.querySelector('#victoryOverlay .victory-card');
    const actions = document.getElementById('victoryActions');
    if (!card || !actions) return;
    card.querySelectorAll('.cm-result').forEach(el => el.remove());
    const button = (label, primary, fn) => {
      const b = document.createElement('button');
      b.textContent = label;
      if (primary) b.classList.add('primary');
      b.addEventListener('click', () => { hideVictoryOverlay(); fn(); });
      return b;
    };

    if (lesson && state.mode === 'practice') {
      const { attempt, song } = recordAttempt();
      const l = lesson.lesson;
      const box = document.createElement('div');
      box.className = 'cm-result ' + (attempt.passed ? 'pass' : 'fail');
      box.innerHTML = '<div class="cm-head"></div><div class="cm-sub"></div>';
      box.querySelector('.cm-head').textContent = (attempt.passed ? '✅  Lesson passed: ' : '🔁  Not yet: ') + l.title;
      box.querySelector('.cm-sub').textContent =
        attempt.accuracyPct + '% (need ' + l.pass.accuracyPct + '%), ' + attempt.wrong + ' wrong (max ' + l.pass.maxWrong + ')' +
        (attempt.weakBars.length ? ' · wrong notes in bar' + (attempt.weakBars.length > 1 ? 's ' : ' ') +
          [...attempt.weakBars].sort((a, b) => a - b).join(', ') : '');
      actions.insertAdjacentElement('beforebegin', box);

      // Lesson buttons go first; NeoKeys' own stay after them.
      const first = actions.firstChild;
      const add = (b) => actions.insertBefore(b, first);
      const lessons = song ? song.plan.lessons : [];
      const i = lessons.findIndex(x => x.id === lesson.id);
      const fp = lesson.fp, id = lesson.id;
      if (attempt.passed && i >= 0 && i + 1 < lessons.length) {
        add(button('➡️  Next: ' + lessons[i + 1].title, true, () => startLesson(fp, lessons[i + 1].id)));
      }
      if (!attempt.passed && l.onFail === 'slower' && l.tempoPct > 40) {
        add(button('🐢  Again at ' + Math.max(40, l.tempoPct - 10) + '%', true,
          () => startLesson(fp, id, { tempoPct: Math.max(40, l.tempoPct - 10) })));
      }
      if (!attempt.passed && l.onFail === 'split_hands' && l.hand === 'both') {
        add(button('✋  Right hand alone', true, () => startLesson(fp, id, { hand: 'rh', transform: l.transform === 'melody_and_chords' ? 'melody' : l.transform })));
        add(button('🤚  Left hand alone', false, () => startLesson(fp, id, { hand: 'lh', transform: l.transform === 'melody_and_chords' ? 'block_chords' : l.transform })));
      }
      add(button('🔁  Try lesson again', !actions.querySelector('.primary'), () => startLesson(fp, id, lesson.lesson)));
      // NeoKeys' "Restart Song" is now a duplicate of Try again; drop its primary look.
      [...actions.children].forEach((b, n) => { if (n > 0 && /Restart Song/.test(b.textContent)) b.classList.remove('primary'); });
      renderPanel();
    } else if (current) {
      actions.appendChild(button('🎓  Claude me', false, () => { openLessonsTab(); planCurrent(true); }));
    }
  }

  // ---------------------------------------------------------------- Lessons tab
  const style = document.createElement('style');
  style.textContent = `
    .tracks-tabs .tracks-tab{white-space:nowrap;padding-left:4px;padding-right:4px;min-width:0}
    #cmPanel .cm-now{font-size:12px;color:var(--text-dim);margin:2px 0 6px}
    #cmPanel .cm-now b{color:var(--text);font-weight:600}
    #cmPanel .cm-row{display:flex;gap:6px;margin-bottom:6px}
    #cmPanel .cm-row .btn{flex:1}
    #cmPanel .cm-status{font-size:11px;color:var(--text-dim);min-height:14px;margin-bottom:6px}
    #cmPanel .cm-status.err{color:#ff7a90}
    #cmPanel .cm-song{border:1px solid var(--panel-border);border-radius:10px;padding:6px;margin-bottom:8px}
    #cmPanel .cm-song-head{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;margin-bottom:4px}
    #cmPanel .cm-song-head span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    #cmPanel .cm-coach{font-size:11px;color:var(--text-dim);margin:0 2px 4px}
    #cmPanel .cm-act{background:none;border:0;color:var(--text-dim);cursor:pointer;font-size:12px;padding:2px 4px}
    #cmPanel .cm-act:hover{color:var(--text)}
    #cmPanel .cm-lesson{display:flex;align-items:center;gap:6px;width:100%;text-align:left;background:rgba(255,255,255,.03);
      border:1px solid transparent;border-radius:8px;color:var(--text);padding:5px 6px;margin:2px 0;cursor:pointer;font:inherit;font-size:12px}
    #cmPanel .cm-lesson:hover{border-color:var(--accent)}
    #cmPanel .cm-lesson.active{border-color:var(--accent);background:rgba(124,92,255,.12)}
    #cmPanel .cm-lesson .t{flex:1;min-width:0}
    #cmPanel .cm-lesson .m{display:block;font-size:10px;color:var(--text-dim)}
    #cmPanel .cm-lesson .s{font-size:11px;color:var(--text-dim);font-variant-numeric:tabular-nums}
    .victory-card .cm-result{margin:10px 0 4px;padding:8px 10px;border-radius:10px;font-size:13px;text-align:left}
    .victory-card .cm-result.pass{background:rgba(54,224,127,.12);border:1px solid rgba(54,224,127,.35)}
    .victory-card .cm-result.fail{background:rgba(255,170,60,.10);border:1px solid rgba(255,170,60,.35)}
    .victory-card .cm-result .cm-head{font-weight:700;margin-bottom:2px}
    .victory-card .cm-result .cm-sub{font-size:12px;opacity:.8}`;
  document.head.appendChild(style);

  const tab = document.createElement('button');
  tab.className = 'tracks-tab';
  tab.id = 'tabLessons';
  tab.type = 'button';
  tab.textContent = '🎓 Lessons';
  tabsRow.appendChild(tab);

  const panel = document.createElement('div');
  panel.id = 'cmPanel';
  panel.style.display = 'none';
  panel.innerHTML =
    '<div class="cm-now">Song: <b id="cmSong">none loaded</b></div>' +
    '<div class="cm-row"><button class="btn primary" id="cmClaude" type="button">✨ Claude me</button>' +
    '<button class="btn" id="cmQuick" type="button" title="Plan made here, without Claude">Quick plan</button></div>' +
    '<div class="cm-status" id="cmStatus"></div><div id="cmSongs"></div>';
  panelRecentEl.insertAdjacentElement('afterend', panel);
  const $ = id => document.getElementById(id);

  const origTab = window.setTracksTab;
  window.setTracksTab = function (which) {
    const mine = which === 'lessons';
    origTab.call(this, mine ? 'builtin' : which);
    tab.classList.toggle('active', mine);
    panel.style.display = mine ? '' : 'none';
    if (mine) {
      document.querySelectorAll('#tabBuiltIn, #tabRecent').forEach(t => t.classList.remove('active'));
      const pb = document.getElementById('panelBuiltIn');
      if (pb) pb.style.display = 'none';
      renderPanel();
    }
  };
  const openLessonsTab = () => window.setTracksTab('lessons');
  tab.addEventListener('click', openLessonsTab);

  const status = (text, err) => { const el = $('cmStatus'); el.textContent = text || ''; el.classList.toggle('err', !!err); };

  let busy = false;
  async function planCurrent(useClaude) {
    if (busy) return;
    if (!current) { status('Load a song first (Built-in, Recent or a .mid file).', true); return; }
    busy = true;
    try {
      const bytes = new Uint8Array(current.midi.toArray());
      const fp = await sha256(bytes);
      const summary = analyse(current.midi, current.title);
      const db = load();
      const prev = db.songs[fp];
      let plan;
      if (useClaude) {
        status('Asking Claude for a lesson plan…');
        try { plan = normalisePlan(await claudePlan(summary, prev ? historyFor(prev) : []), summary); }
        catch (e) {
          status('Claude: ' + e.message + '. Quick plan made instead.', true);
          plan = quickPlan(summary);
        }
      } else {
        plan = quickPlan(summary);
      }
      db.songs[fp] = {
        title: current.title, b64: arrayBufferToBase64(bytes.buffer), summary, plan,
        progress: prev ? prev.progress : {}, madeAt: new Date().toISOString(), by: useClaude && !/Quick plan/.test(plan.coach) ? 'claude' : 'quick',
      };
      db.last = fp;
      if (save(db)) {
        if (!$('cmStatus').classList.contains('err')) status(plan.lessons.length + ' lessons for ' + current.title + ' (' + summary.key + ', form ' + summary.form + ').');
      }
      renderPanel();
    } catch (e) {
      console.error(e);
      status('Could not plan: ' + e.message, true);
    } finally { busy = false; }
  }
  $('cmClaude').addEventListener('click', () => planCurrent(true));
  $('cmQuick').addEventListener('click', () => planCurrent(false));

  const HAND = { lh: 'LH', rh: 'RH', both: 'both hands' };
  const KIND = { original: 'as written', melody: 'tune only', block_chords: 'block chords', melody_and_chords: 'tune + chords' };

  function download(name, data, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([data], { type }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function renderPanel() {
    const songEl = $('cmSong');
    if (!songEl) return;
    songEl.textContent = current ? current.title : 'none loaded';
    const list = $('cmSongs');
    const db = load();
    const entries = Object.entries(db.songs).sort((a, b) => (b[1].madeAt || '').localeCompare(a[1].madeAt || ''));
    list.innerHTML = '';
    if (!entries.length) {
      list.innerHTML = '<div class="recent-empty">No lessons yet. Load a song and press Claude me.</div>';
      return;
    }
    for (const [fp, song] of entries) {
      const box = document.createElement('div');
      box.className = 'cm-song';
      const head = document.createElement('div');
      head.className = 'cm-song-head';
      const name = document.createElement('span');
      name.textContent = (song.by === 'claude' ? '✨ ' : '') + song.title;
      name.title = song.summary.key + ' · ' + song.summary.bpm + ' bpm · ' + song.summary.bars + ' bars · form ' + song.summary.form;
      head.appendChild(name);
      const act = (label, title, fn) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'cm-act'; b.textContent = label; b.title = title;
        b.addEventListener('click', fn);
        head.appendChild(b);
      };
      act('📋', 'Download review (plan, summary and every run) as JSON', () => {
        const { b64, ...rest } = song;
        download(song.title.replace(/[^\w.-]+/g, '-') + '-review.json', JSON.stringify({ fingerprint: fp, ...rest }, null, 2), 'application/json');
      });
      if (lesson && lesson.fp === fp && lastDownload) {
        act('💾', 'Download the loaded lesson as .mid', () => download(lastDownload.name, lastDownload.bytes, 'audio/midi'));
      }
      act('🗑', 'Delete these lessons', () => {
        if (!confirm('Delete the lessons for ' + song.title + '?')) return;
        const d = load(); delete d.songs[fp]; save(d); renderPanel();
      });
      box.appendChild(head);
      if (song.plan.coach) {
        const c = document.createElement('div');
        c.className = 'cm-coach';
        c.textContent = song.plan.coach;
        box.appendChild(c);
      }
      const nextIdx = song.plan.lessons.findIndex(l => !(song.progress[l.id] && song.progress[l.id].passed));
      song.plan.lessons.forEach((l, i) => {
        const p = song.progress[l.id];
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'cm-lesson' + (lesson && lesson.fp === fp && lesson.id === l.id ? ' active' : '');
        const icon = p && p.passed ? '✅' : (i === nextIdx ? '▶️' : '○');
        b.innerHTML = '<span class="i"></span><span class="t"><span class="n"></span><span class="m"></span></span><span class="s"></span>';
        b.querySelector('.i').textContent = icon;
        b.querySelector('.n').textContent = l.title;
        b.querySelector('.m').textContent = 'bars ' + l.bars[0] + '–' + l.bars[1] + ' · ' + HAND[l.hand] + ' · ' + KIND[l.transform] + ' · ' + l.tempoPct + '%';
        b.querySelector('.s').textContent = p && p.attempts.length ? p.best + '%' : '';
        b.title = l.why || '';
        b.addEventListener('click', () => startLesson(fp, l.id));
        box.appendChild(b);
      });
      list.appendChild(box);
    }
  }

  // Tell the page whether Claude is set up (serve.ps1 has a key), without blocking anything.
  fetch('/api/claude-me/status').then(r => r.ok ? r.json() : null).then(s => {
    const btn = $('cmClaude');
    if (!s) { btn.title = 'Claude needs NeoKeys started from serve.ps1'; return; }
    if (!s.key) { btn.title = 'No ANTHROPIC_API_KEY where serve.ps1 runs: Quick plan works without one'; status('Claude isn\'t set up on this computer (no API key); Quick plan works.'); }
    else btn.title = 'Plan lessons with ' + s.model;
  }).catch(() => {});

  window.claudeMe = { analyse: (m, t) => analyse(m, t), quickPlan, normalisePlan, buildLessonMidi, startLesson,
                      get current() { return current; }, get lesson() { return lesson; } };
  renderPanel();
})();
