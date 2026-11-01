# Drift

#### 30.3.2.1 Oscillator 1

Several hand-picked waveforms are available from the Osc 1 drop-down: Sine, Triangle, Shark Tooth, Saturated, Saw, Pulse, and Rectangle. Drift alone carries the Shark Tooth and Saturated waveforms; Shark Tooth draws on a vintage Moog analog shape of that name, while Saturated suits bass tones nicely.

Oscillator 1 is shifted by octaves with the Oct knob. Reach for the Shape knob to nudge the waveform’s harmonic makeup into something subtly altered, giving an outcome akin to pulse-width modulation. Because each waveform’s timbre differs, every one reacts in its own way to the Shape control. While you adjust it, the outcome shows up in the Waveform Display down at the foot of the Oscillator section. The waveform visibly morphs as you alter the Shape value.

Just past the Shape knob, the Oscillator 1 Shape Mod Source drop-down picks a modulation source to act on the Shape control, letting you reshape the waveform further:

- Env 1
- Env 2/Cyc - Either Envelope 2 or the Cycling Envelope serves as the modulator, whichever happens to be switched on.
- LFO
- Key - With the Shape Mod Amount on the positive side, taller note pitches yield greater modulation and lower ones yield less, and the relationship reverses once the amount goes negative.
- Velocity - Arriving velocity feeds the modulation; stronger note velocities yield greater modulation and weaker velocities yield less.
- Modwheel
- Pressure
- Slide

Modulation depth anywhere from -100% to 100% is dialed in using the Oscillator 1 Shape Mod Amount slider. Keep in mind that Shape Mod is able to add waveform modulation on its own at settings of 1% - 100%, even while the Shape control itself stays at 0%.

#### 30.3.2.2 Oscillator 2

Through the Osc 2 drop-down, you pick a waveform for the second oscillator from Sine, Triangle, Saturated, Saw, and Rectangle.

Oscillator 2 is shifted by octaves with the Oct knob, whereas the Detune control shifts it in semitones.

#### 30.3.2.3 Pitch Mod

A pair of modulation source slots, both acting on the pitch of the two oscillators, make up the Pitch Mod section. For a source, the Oscillator Pitch Mod Source drop-downs let you reach for any of Env 1, Env 2 / Cyc, LFO, Key, Velocity, Modwheel, Pressure, or Slide. How strongly each source drives the pitch, anywhere from -100% to 100%, is fixed by the Oscillator Mod Amount sliders.

Drive pitch with an LFO running in the Ratio time mode and you can produce FM tones.

#### 30.3.2.4 Waveform Display

Drift’s Waveform Display.

What the waveform display renders is the merged output of Osc 1, Osc 2, and, when switched on, the noise generator. Tweak the oscillators and you will watch the waveform shift in the display.

#### 30.3.2.5 Oscillator Mixer

Drift’s Oscillator Mixer.

Within Drift’s Oscillator Mixer, switches let you switch on Oscillator 1 and 2 along with a noise generator that mixes white noise into the combined waveform.

Each oscillator and the noise generator also gets its own gain, set with the Osc 1, Osc 2, and Noise controls. With filter processing engaged, pushing oscillator gain high can hit the filters’ ceiling, or “headroom,” where they cease behaving linearly and yield an intricate distortion reminiscent of analog gear.

Two saturation stages within the filter circuitry are responsible for that distortion — one ahead of the filter and one behind it. Raising oscillator gain past its -6.0 dB default kicks in the first saturation stage, and the second engages once gain climbs above 0.0 dB.

Flipping the arrow toggles beside the gain controls turns on filter processing for the oscillators and noise generator. Leave filter processing off and the oscillator and noise output skips the filter altogether.

Retrigger for the oscillators is toggled on or off by the R toggle. With Retrigger on, each oscillator’s phase snaps back to a shared starting point whenever a note sounds; leave it off and the oscillators run freely.

### 30.3.3 Filter Section

Drift’s Filter Section.

A major part of carving the oscillators’ timbres falls to filtering.

Drift’s Filter section provides a low-pass filter switchable between two types, filter key tracking, a resonance control, a high-pass filter, and a pair of frequency modulation controls.

Cutoff for the low-pass filter is set by the Freq knob. The Type toggle moves between a couple of separate low–pass options: Type I (12 dB/octave) alongside Type II (24 dB/octave).

Type I relies on a DFM-1 filter that recirculates more of its own distortion, spanning a wide tonal range from gentle filter sweeps to warm drive.

Type II carries the Cytomic MS2 filter, built on a Sallen-Key topology with soft clipping to rein in resonance.

How strongly the pitch of arriving MIDI notes steers the low-pass filter’s frequency is set by the Key slider. At a value of 0.00, MIDI notes leave filter frequency untouched. At 1.00, low notes pull the filter frequency down and high notes push it up.

Resonance of the low-pass filter is set by the Res knob, and cutoff for the high-pass filter is set by the HP knob.

You may also click anywhere within the Filter section to reach and edit the envelope through the Envelopes section display via an X-Y controller. Drag the left filter dot side to side to fix the high-pass frequency. Drag the right filter dot side to side for the low-pass frequency or up and down for the resonance amount.

For the low-pass filter cutoff, up to two modulation sources are pickable through the Low-pass Modulation Source drop-downs inside the Freq Mod section. How strongly each source drives the frequency, anywhere from -100% to 100%, is fixed by the Low-pass Modulation Amount sliders.

### 30.3.4 Envelopes Section

Drift’s Envelopes Section.

In general, envelopes dictate the way a sound’s amplitude evolves from the instant a note begins until it stops.

A pair of standalone envelopes lives in Drift’s Envelopes section: one governing how amplitude changes and a second meant purely for modulation.

#### 30.3.4.1 Envelope 1

How the Oscillator section’s output amplitude (taking in both oscillators plus the Noise generator when active) starts and evolves once a note begins and then ends is governed by Envelope 1.

The Attack, Decay, Sustain, and Release controls can be set via their knobs or by reshaping the envelope right in the display.

_Attack_ fixes the span needed to climb from the starting value up to the peak value.

_Decay_ fixes the span needed to fall from the peak value down to the Sustain level.

_Sustain_ fixes the level held once the Decay stage closes; the envelope stays there until the note finishes.

_Release_ fixes the span needed to drop back to zero after the note ends.

Switching between Envelope 1 and Envelope 2 happens by clicking the matching section in the UI or by using the _1_ and _2_ toggles within the display. Whichever envelope is active appears in the display ready to edit.

#### 30.3.4.2 Envelope 2

Attack, Decay, Sustain, and Release controls belong to Envelope 2 as well; unlike Envelope 1 though, Envelope 2 is not tied to amplitude by default and can serve as a source for every modulation source slot inside Drift.

Flipping the switch to the left of the Attack control converts Envelope 2 from an ADSR envelope into a Cycling Envelope.

Cycling Envelope.

What the Cycling Envelope behaves like is an LFO modulation that relaunches with every arriving MIDI note.

The envelope’s midpoint is shifted by the Tilt knob, and at very low or very high settings it can also reshape the envelope’s slopes. How long the envelope sits at its peak is fixed by the Hold control.

Out of the box, the Cycling Envelope shows the Rate control, one of four available time modes alongside Ratio, Time, and Sync. Click the switches beside the control to choose another. According to the time mode, the cycle rate is set in Hz, ratio, milliseconds, or tempo-synced beat divisions.

### 30.3.5 LFO Section

Drift’s LFO Section.

Just like the Cycling Envelope, Drift’s LFO offers one of four distinct time modes: Rate, Ratio, Time, or Sync. Which mode is chosen sets the LFO’s cycle rate in Hz, ratio, milliseconds, or tempo-synced beat divisions.

Within the LFO display, nine waveforms are pickable from the drop-down:

- Sine
- Triangle
- Saw Up
- Saw Down
- Square
- Sample & Hold
- Wander is a sample and hold carrying an S-shape that eases between a pair of values at the LFO’s rate.
- Linear Envelope is a single-shot decay envelope whose decay is linear.
- Exponential Envelope is a single-shot decay envelope whose decay is exponential.

Retrigger is toggled on or off with the R switch. When on, the LFO snaps back to the same point in its phase each time a note fires. When off, the LFO runs freely.

Overall LFO intensity is set by the LFO Amount knob. A source for the LFO is picked from the LFO Modulation Source drop-down, while how strongly that source acts on the LFO is fixed by the LFO Modulation Amount slider.

### 30.3.6 Mod Section

Drift’s Mod Section.

Nearly every parameter in Drift can be modulated; within the Mod section you may pick as many as three modulation sources and their destinations.

Available sources, picked through the Modulation Source choosers, are Env 1, Env 2 / Cyc, LFO, Key, Velocity, Modwheel, Pressure, or Slide.

The Modulation Destination choosers expose the following targets. Among the oscillator and noise options are Osc 1 Gain, Osc 1 Shape, Osc 2 Gain, Osc 2 Detune, and Noise Gain. On the filter and rate side you will find LP Frequency, LP Resonance, HP Frequency, LFO Rate, Cyc Env Rate, plus Main Volume.

How strongly the chosen destination responds to the source, anywhere from -100% to 100%, is fixed with the Modulation Amount sliders.

### 30.3.7 Global Section

Drift’s Global Section.

How the instrument behaves and performs overall is governed by Drift’s global controls.

Drift’s four Voice Modes are selectable through the Mode chooser:

_Poly_ assigns a single voice to each note and supplies as many as 32 voices of polyphony.

_Mono_ sounds a single note at any moment, yet that note draws on four voices to build a unison character governed by the Mono Thickness setting. With the Mono Thickness slider, you balance the relative loudness of the four voices tied to each individual note. Set Thickness to 0 and a note sounds through a lone voice. Push Mono Thickness upward and the remaining three voices grow louder until each note carries them audibly. Whenever a fresh note arrives, it cuts off the prior note that is still sounding, assuming you continue to hold it.

_Stereo_ assigns two voices to each note and spreads them toward the left and right channels. The Stereo Spread slider controls the degree of panning spread distributed among the separate voices. Raise the amount and the voices separate further, which yields a broadening result.

_Unison_ gently detunes each note's four voices, treating them as independent of one other. With the Unison Strength slider, you set the extent of pitch deviation spread among the separate voices. Crank it up and each voice receives a greater degree of variation.

To cap how many voices may sound at once, choose a value from the Voices drop-down menu. Some Voice Modes draw on a larger voice count than the notes you actually trigger, so the resulting polyphony shifts based on whichever Voice Mode is active. As an illustration, with the Voices amount set to 32 voices:

- Poly mode applies 1 voice per note, giving a ceiling of 32-note polyphony.
- Stereo mode applies 2 voices per note, giving a ceiling of 16-note polyphony.
- Unison mode applies 4 voices per note, giving a ceiling of 8-note polyphony.

The Drift slider introduces a touch of variation into every voice, touching assorted facets of how that voice sounds, including pitch and filter cutoff. In Drift, each voice gets its own randomization applied to the oscillators and to filter frequency; turning the Drift control up or down scales that individual randomization. Push the amount higher and the spread between the oscillators and the filter grows wider, pulling the sound further out of tune.

With the Voice Mode set to Mono, you may switch on the Legato toggle so that starting a new voice shifts its pitch while leaving its envelopes untouched. The Glide slider governs how long overlapping notes take to glide their pitch toward the next arriving pitch whenever notes play legato.

The Volume knob fixes the instrument's overall loudness, whereas the Vel > Vol slider controls the degree to which volume responds to incoming MIDI note velocity.

With the Transpose slider you shift the global pitch by semitones across a span of -48 to 48 st. Turn on the Note PB toggle to activate per-note pitch bend. Turning Note PB off allows an MPE controller to work without pitch shifting according to finger placement. The PB Range slider establishes the global pitch bend span measured in semitones.
