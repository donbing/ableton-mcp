# Drum Sampler

### 30.4.1 Sample Controls Section

Drum Sampler’s Sample Controls Section.

Within the Sample Controls section, you can edit the sample's envelope, pitch, and volume, and also exchange whatever sample is loaded.

You load a sample into Drum Sampler by double-clicking a file in the browser, or by dragging and dropping it onto the waveform display.

The Sample Start slider fixes where playback of the sample starts, expressed as a percentage of the sample's length. Holding Shift as you drag the slider nudges the start position in fine steps, and at the same time the display zooms into the waveform.

The Sample Length slider determines the duration of the played region, again expressed as a percentage of the sample's overall length.

With the Sample Gain slider you tune the sample's loudness, ranging from -70 to 24 dB.

Tweaking the Sample Start, Sample Length, and Sample Gain controls likewise refreshes the waveform shown in the display.

The Attack, Hold, and Decay controls let you shape the sample's envelope.

Attack establishes how long it takes to move from the envelope's starting level up to its peak.

Hold establishes how long the envelope's amplitude stays at the peak after the attack time elapses in Trigger mode. Setting the Hold time to inf (i.e., infinite) lets the sample play across its full length. Keep in mind this parameter is greyed out whenever the device's Envelope Mode is switched to Gate.

Decay establishes how long it takes to fall from the peak back down to zero once the Hold time passes in Trigger mode, or as soon as the note releases in Gate mode.

The Transpose slider fixes the global transposition figure, spanning -48 to 48 semitones, and the Detune slider fixes the global detune figure, spanning -50 to 50 cents.

Drum Sampler provides two envelope modes, Trigger and Gate. Under Trigger mode, the sample keeps sounding for the length of the configured Hold time once a note releases. Under Gate mode, the sample tapers off following the configured Decay time after a note releases.

Moving the cursor over the waveform display surfaces extra controls for handling the sample that is loaded.

The Similar Sample Swapping and Hot-Swap Controls.

Click the Swap to Next Similar Sample button to step through samples that [sound similar](https://www.ableton.com/en/live-manual/12/live-concepts/#sound-similarity) to your original file. To move backward among the choices, click the Swap to Previous Similar Sample button. Alternatively, right-click the display and pick Show Similar Files, which opens a browser list of comparable samples.

While stepping through samples, you can jump back to the file you first loaded by right-clicking the waveform display and choosing _Return to Reference_. To mark the file presently loaded as a fresh reference for swapping, choose the _Save as Similarity Reference_ option.

The hot-swap button launches the Hot-Swap Browser, letting you switch the loaded sample for another. To swap Drum Sampler out for a different instrument, click the hot-swap button located in the device's title bar.

### 30.4.2 Playback Effects Section

Drum Sampler’s Playback Effects Section.

A sample's sound can be shaped further with any one of nine playback effects. The first four are Stretch, Loop, Pitch Env, and Punch; the rest comprise 8-Bit, FM, Ring Mod, Sub Osc, and Noise.

Every playback effect carries two parameters, controllable through their own knobs or through the X/Y pad. Drag up and down on the X/Y pad for the first parameter, then drag side to side for the second.

The Playback Effect On toggle switches this whole section on or off. Once it is on, pick an effect through the Playback Effect Type drop-down menu.

_Stretch_ alters the sample's duration while leaving pitch intact. The outcome is granular artifacts that lend a lo-fi quality to the sound. The Factor control determines how much time-stretching occurs, given as a multiple of the original playback speed. The Grain Size control determines, in milliseconds, the grain size used when time-stretching the sample.

_Loop_ repeats a segment of the sample. The Loop Offset control positions the loop start relative to where the sample starts. The Loop Length control sets, in milliseconds, how long the loop lasts.

_Pitch Env_ drives the sample's pitch over time through an envelope. The Pitch Envelope Amount control sets how much pitch modulation occurs, ranging from -100 to 100%. Positive figures push the pitch up, whereas negative figures pull it down. The Pitch Envelope Decay control sets how long the pitch takes to settle back to the base value established by the device's global pitch controls.

_Punch_ imposes ducking using a fixed attack alongside an envelope tailored to accentuate the sample's transient. The Punch Amount control sets how much ducking is imposed. The Punch Release control sets how long the gain reduction needs to climb back to zero following the initial trigger.

_8-Bit_ blends filtering with bit reduction and sample rate reduction to evoke how 8-bit CPU chips sound. Playback sample rate for the sample is governed by the 8-Bit Sample Rate control. How quickly the effect's built-in low-pass filter decays is governed by the 8-Bit Decay Time control.

_FM_ employs a sine wave to drive the sample's pitch. The Amount control sets how strong the frequency modulation is, and the FM Frequency control sets the frequency that modulates the sample's pitch.

_Ring Mod_ imposes ring modulation upon the sample. The Amount control sets how much modulation occurs. The Ring Mod Frequency control sets the frequency that modulates the sample's amplitude. Low figures yield a tremolo effect, whereas high figures yield artifacts characteristic of ring modulation.

_Sub Osc_ stacks a sub oscillator on top of the sample. The Sub Oscillator Amount knob sets that oscillator's level. For its envelope, the device's attack plus decay settings are reused. The oscillator's frequency, ranging across 30 to 120 Hz, is set by the Sub Oscillator Frequency.

_Noise Osc_ stacks a noise oscillator on top of the sample. The Noise Amount knob sets that oscillator's level. For its envelope, the device's attack plus decay settings are reused. The frequency that filters the oscillator is set by the Noise Color control.

Keep in mind that the time-based and frequency-related controls within the Stretch, Loop, FM, Ring Mod, Sub Osc, and Noise Osc effects respond to the device's global pitch controls together with the MIDI note triggered. Because of this, each effect's pitch tracks the sample's pitch as you trigger different notes or transpose the sample.

On top of that, the global decay time governs the modulation decay of the FM and Ring Mod effects. As an example, when decay times are short, modulation reaches only the sample's transient.

### 30.4.3 Filter Section

Drum Sampler’s Filter Section.

The Filter On toggle switches the filter on or off.

You can pick from four filter types. Two are low-pass varieties, namely a 12 dB low-pass filter and a 24 dB low-pass filter; the remaining pair is a 24 dB high-pass filter together with a peak filter.

Both the low-pass and high-pass filters carry their own Resonance and Filter Frequency controls. With the peak filter active, the Peak Filter Gain and Filter Frequency controls let you raise or lower a particular frequency range.

### 30.4.4 Global Section

Drum Sampler’s Global Section.

Within the Global Section, you can set the output volume, panning, velocity-to-volume ratio, and modulation parameters.

The Volume control sets the device's global output level, spanning -36 to 36 dB, and the Pan slider places the signal in the stereo field.

The Velocity to Volume slider governs how strongly incoming MIDI note velocity modulates the device's volume.

The Modulation Source toggle flips between a pair of modulation sources, Velocity or Slide (MPE). After that, pick a modulation target through the Modulation Destination drop-down menu.

The Filter target drives the filter cutoff frequency.

Each separate envelope stage can be modulated through the Attack, Hold, and Decay targets.

FX1 and FX2 modulate the two parameters belonging to whichever playback effect is currently chosen.

The Modulation Amount slider sets how much modulation reaches the target.

### 30.4.5 Context Menu Options for Drum Sampler

Beyond the standard device [context menu](https://www.ableton.com/en/live-manual/12/live-keyboard-shortcuts/#using-lives-context-menu) entries, a couple of choices belong specifically to Drum Sampler.

_Enable Per-Note Pitch Bend_: This lets Drum Sampler take in per-note pitch bend messages, and it is on by default.

_Envelope Follows Pitch_: This sizes the amplitude envelope according to the sample's pitch. With it on, the envelope keeps affecting the identical part of the sample even as the pitch gets transposed.

_Drum Sampler > Simpler_: This swaps Drum Sampler for Simpler while keeping the sample's start and length positions.

While working with [Drum Racks](https://www.ableton.com/en/live-manual/12/instrument-drum-and-effect-racks/#drum-racks), the _Save as Default Pad_ option on a pad's context menu makes Drum Sampler the default for incoming samples.

The Save as Default Pad Option.

As a result, whenever a sample drops onto an empty drum pad, a Drum Sampler instance loads on its own.
