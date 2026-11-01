# LFO

### 32.2.3 LFO

The LFO Effect.

LFO is a modulator device that steers mapped parameters by way of low-frequency oscillation.

Within Live, any automatable parameter — device or mixer controls included — can be assigned to LFO. Do this by turning on the Map button and clicking the parameter you want to use as the mapping target.

Additional mapping buttons appear when you press the Show/Hide Multimap button at the display's top right; in all, up to eight parameters can be mapped.

You Can Map up to Eight Parameters.

To drop an assignment, click the Unmap button sitting to the right of the Map button.

LFO offers two ways to govern mapped parameters: Modulation and Remote Control. Modulation is the default, and the Mod toggle switches you over to Remote Control.

While Modulation is on, you can still tweak parameter values manually after mapping them. The Modulation Polarity toggle alternates between Bipolar and Unipolar modes. Bipolar mode modulates in both directions around a centered base value, whereas Unipolar mode pushes in just one direction away from the base value. Modulation depth is fixed by the Modulation Amount slider, which sets the range measured against the base value.

Once Remote Control is on, the mapped values are set entirely by LFO and can't be edited by hand. The Min and Max sliders scale the modulation range.

The Waveform drop-down menu lets you pick from nine shapes: Sine, Up, Down, Triangle, Square, Random, Bin, Stray, and Glider.

Bending or skewing the LFO waveform is done with the Shape control, and the Steps slider can divide the waveform into as many as 24 steps. Because of how their values arise, some waveforms can't be shaped or stepped — so the Shape control grays out for Random, Bin, Stray, or Glider, and the Steps control grays out for Random, Bin, or Square.

Randomness is sprinkled onto the LFO output by the Jitter slider, while the Smooth control rounds off abrupt changes in the output, including the ones jitter introduces.

The LFO rate is fixed by the Rate control. The Time Mode toggles flip between frequencies in Hertz and tempo-synced beat divisions, and when Hz is active the ×10 button multiplies the frequency value.

For every mapped parameter, the modulation amount is governed by Depth. At 0% nothing is modulated, and at 100% the LFO output reaches its full strength.

The Offset control repositions the center point of the LFO output. At 0% the output sits centered. Positive values raise the output, negative values lower it. A horizontal line in the display marks the center, serving as a handy visual cue while you adjust Offset.

You Can Shift the Center Point of the LFO Output Using Offset.

Where the LFO sits within its cycle is set by the Phase slider, running from 0% (cycle start) to 100% (cycle end).

To lock the LFO output at its present value, turn on the Hold toggle. Turning Hold off resumes the LFO from the value that was held.

Press the R (Retrigger) button to restart the LFO from the spot set by the Phase control.
