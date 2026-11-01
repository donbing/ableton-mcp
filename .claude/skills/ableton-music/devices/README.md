# Device notes

What the controls of some devices do, for sound design with `get_device_parameters` / `set_device_parameter`.
The Push tells you which parameters exist and their ranges; these pages say what they mean.

Only devices where Claude's own knowledge was wrong or vague are here. They were picked on 2026-10-27 by a
recall test: for every instrument and effect on the Push (Live 12.4.6 Intro), Claude wrote what it knew, then
checked it against the LevyBytes Live 12 manual skill. Pages for the rest were left out on purpose.

| File | What recall got wrong |
|---|---|
| `drift.md` | Osc 1 waveforms (Saturated, Rectangle), LFO shapes (Wander, Lin/Exp Env), Rate/Ratio/Time/Sync modes, Thickness belongs to Mono |
| `drum-sampler.md` | Envelope is Attack/Hold/Decay; filter types (12/24 LP, 24 HP, Peak); Velocity/Slide modulation targets |
| `auto-filter.md` | 10 filter types (DJ, Comb, Resampling, Notch+LP, Vowel); circuits are SVF/DFM/MS2/PRD |
| `auto-pan-tremolo.md` | Harmonic and Vintage tremolo, Invert, time modes, Dynamic Frequency Modulation |
| `auto-shift.md` | Mono/Poly (up to 8 voices) MIDI input, mod routing, LFO tab, vibrato ranges |
| `erosion.md` | Redesigned in 12.4 (Noise Blend, Filter Width, Stereo Width); recall was of Erosion Legacy |
| `lfo.md` | Up to 8 mappings, Modulate vs Remote Control, waveforms Bin/Stray/Glider |
| `expression-control.md` | 5 source tabs, 10 sources (Increment, Expression, Sustain...), Modulate vs Remote Control |
| `mpe-control.md` | Press/Slide/NotePB reshaping and conversion to non-MPE messages (the Push 3 pads send MPE) |

Recall was right for: Impulse, Simpler, Drum Rack, Beat Repeat, Channel EQ, Chorus-Ensemble, Compressor, Delay,
EQ Three, Gate, Grain Delay, Limiter, Looper, Phaser-Flanger, Redux, Reverb, Saturator, Utility, Arpeggiator,
CC Control, Chord, Note Length, Pitch, Random, Scale, Velocity. Rotating Rhythm Generator has no manual page.

This Live edition has no Meld, Roar, Wavetable or Operator.

Source: [LevyBytes/AI-SKILL-ableton-live](https://github.com/LevyBytes/AI-SKILL-ableton-live) (Apache-2.0, see
`LICENSE` and `NOTICE`), itself interpreted from Ableton's Live 12 manual. Section links were removed; the text is
otherwise unchanged. When a page and the Push disagree, the Push wins.
