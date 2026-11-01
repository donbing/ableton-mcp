# Expression Control

### 32.3.2 Expression Control

The Expression Control Effect.

Expression Control is a modulator device that governs mapped parameters from a choice of MIDI and MPE sources.

It provides five Mod Source tabs, and each one can be pointed at a particular MIDI or MPE source. From the MIDI Input Source drop-down menu you pick whichever expression parameter you need; the ten on offer are Velocity, Modwheel, Pitchbend, Pressure, Keytrack, Expression, Random, Increment, Slide, and Sustain.

Within Live, any automatable parameter — device or mixer controls among them — can be assigned to the chosen modulation source. To do this, switch on the Map button and click a parameter to set it as the mapping target.

Which controls appear in the Output Range section is dictated by the Modulation toggle at the device's top right. That toggle decides how Expression Control produces its modulation values and offers two modes: Modulate or Remote Control.

Pick Modulate and you can still nudge a mapped parameter's base value with the cursor. In this mode, whatever Expression Control sets or automates blends with the value you dial in as you adjust that parameter. Pick Remote Control instead and Expression Control alone determines the modulated values, leaving the base parameter values beyond reach.

The Modulation toggle additionally influences the polarity behavior of Expression Control. Choosing Modulate reveals a Modulation Polarity toggle within the Output Range section, where you pick either bipolar or unipolar operation. With Bipolar mode active, the modulation pivots around whichever base parameter value is currently being modulated. With Unipolar mode active, the modulation gets summed onto that base parameter value instead. The Output Range Max slider determines the modulation output produced once the incoming signal hits its peak amplitude. Selecting Remote Control instead turns the Output Range section into a place where you define both a floor and a ceiling for the modulation output, controlled through the Output Range Min and Output Range Max sliders.

Use the Curve Type buttons sitting underneath the Curve Display to pick either a linear or an S-shaped curve. Whichever curve type you pick governs the set of controls offered within the Curve section.

With a linear curve chosen (it carries two breakpoints), the Curve A dial reshapes the whole modulation curve at once. Pick an S-shaped curve (which has three breakpoints) and the Curve A dial then governs the upper part of the curve while the Curve B dial governs the lower part. Enabling the Curve Link button means the upper and lower portions move in opposite directions through the single Curve A dial alone.

The Curve Display gives you a visual look at the modulation curve the device is currently producing. You define the curve's lowest and highest values through the Min/Max sliders. With an S-shaped curve active, the X-Y sliders let you position the middle breakpoint both horizontally and vertically. You can equally reshape the breakpoints and overall curve by dragging the rendered curve right inside the display.

Picking Increment as the modulation source from any MIDI Input Source drop-down menu switches on the Increment Steps slider. That setting governs the number of note triggers required to traverse the device's full modulation range, accepting any value from 1 to 32 steps. Halting transport clears the counter, meaning the very first note after transport resumes emits whatever minimum modulation value you configured.

Picking Random as the modulation source from any MIDI Input Source drop-down menu switches on the Random Amount slider. Use this slider to dial in how much random spread is applied around the target modulation value at every note trigger.

Through the Smoothing Type toggle you decide whether smoothing across modulation values follows a linear or a logarithmic path.

The Smoothing Rise and Fall sliders govern how long, between 0 and 1000 milliseconds, rising and falling modulation values take before they arrive at the latest value.
