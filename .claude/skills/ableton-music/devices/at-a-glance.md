# Devices at a glance

Every instrument and effect on the Push (Live 12.4.6 Intro) worth using for music: its modes, the controls that
matter, and what to reach for it for. Checked against the Live 12 manual on 2026-10-27. A device marked → has a
detailed page in this folder. Exact parameter names and ranges come from `get_device_parameters`.

## Instruments

- **Drift** → `drift.md`. Two oscillators plus noise, low-pass (Type I 12 dB / Type II 24 dB) and high-pass
  filters, Env 1 (amp), Env 2 (can cycle like an LFO), LFO, 3-slot mod matrix; voice modes Poly, Mono (4 stacked
  voices, Thickness), Stereo (Spread), Unison (Strength); Drift knob adds analog detune. Basses, pads, leads,
  plucks: the only synth on this Push.
- **Drum Sampler** → `drum-sampler.md`. One sample per pad; Attack/Hold/Decay, Trigger or Gate; one of nine
  playback effects (Stretch, Loop, Pitch Env, Punch, 8-Bit, FM, Ring Mod, Sub Osc, Noise Osc); filter 12/24 LP,
  24 HP or Peak. Default device on new Drum Rack pads; Pitch Env and Punch for kicks, Sub Osc for 808s.
- **Simpler**. One sample, three modes: Classic (looping, polyphonic), One-Shot (mono, Trigger/Gate, fades),
  Slicing (by Transient, Beat, Region or Manual; Mono, Poly or Thru playback). Filter LP/HP/BP/Notch/Morph with
  Clean, OSR, MS2, SMP or PRD circuits; amp, filter and pitch envelopes (amp can loop); per-voice LFO; Spread;
  Glide or Portamento. Chopping breaks and vocals, playing a sample chromatically. Slice to Drum Rack from Slicing.
- **Impulse**. Eight sample slots, each with Start, Transpose, Stretch (mode A lows, B highs), filter, Drive,
  Decay (Trigger/Gate), Pan, Volume; slot 8 can be choked by 7. Quick classic drum kits; Drum Rack does more.
- **Drum Rack**. Pads are chains (any instrument and effects per pad), choke groups, return chains inside the
  rack, macros. The container for every kit; pad notes start at 36 (C1).
- **Instrument Rack**. Chains split by key or velocity zone or a chain selector, macros with variations. Layering
  and splits.

## Audio effects

Tone and dynamics:
- **Channel EQ**. HP 80 Hz switch, Low shelf (100 Hz, ±15 dB), sweepable Mid (120 Hz to 7.5 kHz, ±12 dB), High
  shelf (cuts also sweep a low-pass from 20 down to 8 kHz). Fast, musical track EQ.
- **EQ Three**. Low/Mid/High from -inf to +6 dB with kill buttons, FreqLo/FreqHi crossovers, 24 or 48 dB slopes.
  DJ-style kills and blends.
- **Compressor**. Threshold, Ratio, Attack, Release (Auto), Knee, Makeup, Lookahead 0/1/10 ms, Peak/RMS/Expand,
  Lin/Log envelope, sidechain with EQ. Control dynamics; sidechain from the kick for pumping.
- **Gate**. Threshold, Return (hysteresis), Attack, Hold, Release, Floor, Flip, Lookahead, sidechain. Tighten
  drums, cut tails, rhythmic gating of pads from a drum track.
- **Limiter**. Ceiling or Maximize (Threshold), Release (Auto), Lookahead 1.5/3/6 ms, Standard/Soft Clip/True
  Peak, L/R or M/S link. Last device on the Main track.
- **Utility**. Gain (-inf to +35 dB), Width or Mid/Side, Mono, Bass Mono (50-500 Hz), phase flips, Channel Mode,
  Balance, Mute, DC. Level automation, mono low end, width. First in a chain for gain staging, last for volume
  automation that leaves the mixer fader free.

Filters and movement:
- **Auto Filter** → `auto-filter.md`. Ten filter types (incl. DJ, Comb, Vowel, Resampling), SVF/DFM/MS2/PRD
  circuits, Drive, LFO (Phase/Spin stereo), envelope follower, sidechain. Sweeps, builds, wah, DJ-style filtering.
- **Auto Pan-Tremolo** → `auto-pan-tremolo.md`. Panning or Tremolo mode, nine LFO shapes, Phase/Spin, Invert,
  Harmonic and Vintage tremolo. Auto-pan, tremolo, gating and ducking shapes.
- **LFO** → `lfo.md`. Modulates up to eight mapped parameters (Modulate or Remote Control). Movement on any
  parameter without automation.

Space and time:
- **Delay**. Two delay lines in Sync (16ths) or Time, Link, Ping Pong, Feedback, band-pass filter, LFO on time and
  filter, Repitch/Fade/Jump when the time changes, Freeze. Echoes, slapback, dub throws.
- **Grain Delay**. Delay chopped into grains: Frequency, Pitch, Random Pitch, Spray, Feedback, X-Y pad.
  Shimmer, pitch clouds, glitch textures.
- **Reverb**. Input filter, early reflections (Spin, Shape), diffusion (Size, Decay, Hi/Lo shelves, Density,
  Scale, Chorus), Predelay, Freeze, Stereo, Reflect/Diffuse levels. Rooms to huge washes; put it on a return.
- **Chorus-Ensemble**. Chorus (2 lines), Ensemble (3 lines, lusher) or Vibrato; Rate, Amount, Feedback, Width,
  Warmth, high-pass. Widening, thickening, string-machine shimmer.
- **Phaser-Flanger**. Phaser, Flanger or Doubler; two LFOs, envelope follower, Feedback, Safe Bass, Warmth.
  Sweeping movement, jet flanges, fake double-tracking; a bar or two on drums makes a fill before a drop.

Character and destruction:
- **Saturator**. Curves Analog Clip, Soft Sine, Bass Shaper, Medium/Hard Curve, Sinoid Fold, Digital Clip,
  Waveshaper; Drive, Color filters, Post Clip, Dry/Wet. Warmth to heavy distortion; Bass Shaper for 808s.
- **Redux**. Downsampling (Rate, Jitter, pre/post filters) and bit reduction (Bits, Shape, DC Shift). Lo-fi,
  8-bit grit, aliasing.
- **Erosion** → `erosion.md`. Short delay modulated by sine and noise (Noise Blend, Filter Width, Stereo Width).
  Digital hiss and air, subtle degradation. (Rebuilt in 12.4.)
- **Beat Repeat**. Interval, Offset, Grid, Variation, Chance, Gate, Pitch and Pitch Decay, filter, Mix/Insert/Gate.
  Stutters, fills, glitch repeats.

Performance and pitch:
- **Looper**. Record/Overdub/Play/Clear, Undo, x2 and /2, Speed, Reverse, Feedback, tempo and song control.
  Live looping a part.
- **Auto Shift** → `auto-shift.md`. Pitch correction to a scale or to MIDI notes (harmonies), formant shift,
  vibrato, LFO. Tuning vocals, robotic retune, vocal harmonies.

## MIDI effects

Put these before the instrument; most can follow the clip's scale (Use Current Scale).

- **Arpeggiator**. Styles (Up, Down, Converge, Diverge, Play Order, Chord Trigger, Random variants), Rate, Gate,
  Steps and Distance (transpose per pass, in scale), Pattern Offset, Retrigger, Repeats, velocity decay, Groove,
  Hold. Arps from held chords.
- **Chord**. Up to six added notes (±36 st) with per-note velocity or chance, Strum (to 400 ms), Tension,
  Crescendo. One finger chords, strums.
- **Scale**. Remaps every note to a scale (Base and scale, or the clip's), Transpose, Lowest/Range. Keep anything
  in key.
- **Pitch**. Transpose ±128 st (or scale degrees), Step Up/Down, Lowest/Range with Block, Fold or Limit.
- **Random**. Chance, Choices, Interval, Mode Random or Alt (round-robin), Sign Add/Sub/Bi. Melodic variation,
  in scale.
- **Velocity**. Out Hi/Low, Lowest/Range, Drive, Compand, Random, Clip/Gate/Fixed. Even out or humanize dynamics.
- **Note Length**. Trigger from Note On or Note Off, Length, Gate, Latch. Staccato, legato, note-off tricks.
- **CC Control**. Mod Wheel, Pitch Bend, Pressure, a switch (Custom A) and 12 named CC knobs. Hardware control.
- **Expression Control** → `expression-control.md`. Maps velocity, modwheel, pressure, slide, keytrack, random,
  and more onto parameters with curves.
- **MPE Control** → `mpe-control.md`. Reshapes the Push pads' pressure, slide and per-note pitch, or converts them
  for non-MPE instruments.
- **Rotating Rhythm Generator**. Euclidean-style rhythm generator (not in the manual; check its parameters on the
  Push before relying on it).

## MIDI Tools

Intro has only **Quantize**. The Live 12 generators and transformations (Rhythm, Seed, Stacks, Arpeggiate,
Strum and the rest) are not in this edition: write notes with the MCP tools instead.

Not covered: CV utilities, External Instrument, Tuner, MIDI Monitor and the empty racks. This list matches
Ableton's Live 12 edition comparison for Intro (9 instruments, 28 audio effects, 12 MIDI effects, 1 MIDI tool,
2 modulators: LFO and Expression Control).
