# MPE Control

### 32.3.4 MPE Control

The MPE Control Effect.

MPE Control is a Max for Live MIDI effect for reshaping and transforming arriving MPE (MIDI Polyphonic Expression) signals, providing separate, tailored adjustments for every MPE data source. You normally pair it with a second device so you can refine how the MPE data influences mapped parameters. On top of that, MPE Control can turn MPE signals into global MIDI, which lets you drive non-MPE enabled instruments from an MPE controller.

Before digging into how the MPE Control effect reshapes arriving MPE data, it helps to consider what separates MPE from ordinary MIDI messages. With MPE, MIDI Control Change (or MIDI CC) messages travel on a per-note basis, so each note can be articulated on its own. Lacking MPE, the same messages travel globally, so every note responds to whatever MIDI CC is in play. To read more about MPE, see the [Editing MPE](https://www.ableton.com/en/live-manual/12/editing-mpe/#editing-mpe) chapter.

MPE already opens up far more musical expression than plain MIDI data, yet MPE Control lets you sculpt those MPE signals even further through curves, which makes still more expressive performances possible. Imagine you have the Expression Control device in use and routed its Slide MIDI input onto the Filter Freq knob inside Operator. Every bit of arriving MPE slide data then drives the filter frequency. From there MPE Control can refine that signal so that only the very highest slide values push toward a high cutoff frequency.

Inside MPE Control, arriving MPE signals get reshaped through two kinds of curves, both of which support smoothing for even rise and fall behavior. Three signal sources exist: Press (pressure), Slide, and also NotePB (per-note pitch bend), with each one adjustable on its own.

Whichever MPE source you select has its curve drawn in the front of the display, putting that curve and its associated controls within reach for editing. Out of the box every MPE source is switched on, yet you can turn each one off on its own by clicking the toggle beside its name.

Every MPE source offers two curve-setting choices at the lower left of the display: linear or S-shaped. A linear curve carries two breakpoints, whereas an S-shaped curve carries three.

Pick the linear setting and you can shape the curve through two methods. Either turn the Curve control knob or drag the curve straight inside the display. Beyond reshaping the curve, you can also set its floor and ceiling through the Min and Max sliders, or by hauling the breakpoints sitting at each end of the curve.

A single curve comes from the linear setting, producing a smooth ramp for whichever modulation source you chose, either "compressing" the data so staying in the lower value range is easier, or "expanding" it so reaching higher values takes less input.

Pick the S-shaped curve and a third breakpoint appears at the center of the curve's line, splitting the curve into two separate segments. Because that breakpoint moves freely, you have full say over where the two segments cross over, opening the door to far more extreme curves. By default the two segments stay linked. Flip the Curve Link button to detach the segments from one another, after which each can be compressed or expanded on its own through the two separate Curve dials.

Keep in mind that the breakpoint dividing the two segments can be moved either by clicking and dragging it directly, or through the X-Y controls along the bottom of the display. Those X-Y controls come alive only while the S-shaped curve is in use.

Click the triangular button at the lower right of the visualization to reveal the advanced settings panel.

MPE Control's Expanded View.

Each of the three modulation sources carries a Smooth toggle that turns on smoothing for whichever source is currently selected. You can dial in separate Rise and Fall values per curve through the matching controls, and further controls appear depending on which source you happen to be editing.

#### 32.3.4.1 Press

The Press source lets you reshape MPE pressure data, which, much like polyphonic aftertouch, travels on a per-note basis whenever pressure lands on a controller's key or pad once it has already been struck.

Press Advanced Settings.

Press carries a Default toggle, letting you assign a default MPE value for use with MIDI notes that arrive without MPE data. You may also route the MPE pressure data toward the Slide rather than the Press source through the Swap to Slide toggle. That comes in handy when, say, you'd rather adjust modulation along the vertical axis yet your controller offers only polyphonic aftertouch.

The Press to AT setting turns the MPE pressure data into monophonic aftertouch, so an MPE controller can modulate non-MPE instruments.

#### 32.3.4.2 Slide

The Slide source reshapes MPE slide data (sent as MIDI CC 74), which maps to where the finger sits vertically on the controller key or pad.

Slide Advanced Settings.

Slide likewise carries a Default toggle for non-MPE data, plus a Centered switch that helps when performing on pad-based MPE controllers. Turn Centered on and MPE slide data gets reshaped so that striking the pad's center yields a modulation value of zero, with that value climbing steadily as the finger travels away from center along the vertical axis.

Out of the box, Slide sits in Abs mode, treating MPE slide values as absolute. Flipping the mode to Rel (relative) makes the slide values begin at the middle of the range no matter where the finger rests on the key or pad. They can then change only by sweeping the finger further up and down while a note is held. Under Ons (onset) mode, MPE slide values refresh only at a Note On. Be aware that onset mode switches smoothing off automatically.

The Slide to Mod option turns MPE slide messages into Mod Wheel (CC1) messages, which lets an MPE controller modulate non-MPE enabled instruments.

#### 32.3.4.3 NotePB

The NotePB source reshapes the MPE per-note pitch bend data, which comes from horizontal motion across the controller's keys or pads. By its nature, pitch bend influences only the pitch or pitches being sounded.

NotePB Advanced Settings.

Within the NotePB advanced settings you can set the Pitch Range, handy when the hardware controller's pitch bend range and the instrument's do not line up. As an example, a 2x setting lets you map an MPE controller carrying a +/- 48 semitone pitch bend range onto an instrument whose range is +/- 24 semitones. Should the Note Pitch Bend MIDI CC be routed to something besides pitch, higher values let you span a wider modulation range from a smaller gesture.

Turn the NotePB to PB switch on and MPE per-note pitch bend messages get converted into standard MIDI messages, allowing MPE-enabled MIDI controllers to keep feeding MIDI information to instruments that cannot receive MPE messages.
