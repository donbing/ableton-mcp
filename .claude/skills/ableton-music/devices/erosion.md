# Erosion

### 28.17 Erosion

The Erosion Effect.

Erosion applies digital degradation to the input signal by modulating a brief delay with a mix of a sine wave and filtered noise. The outcome can range from noisy artifacts all the way to distortions reminiscent of downsampling.

During playback the input signal’s frequency spectrum appears in the display, accompanied by a visual depiction of the modulation. That display doubles as an X-Y controller you can use to set the Freq and Amount controls. Drag horizontally along the X-axis to alter the sine wave frequency and the noise filter’s center frequency. Drag vertically along the Y-axis to govern the modulation amount. Holding Alt (Win) / Option (Mac) instead lets you set the filter width of the noise modulation on the Y-axis. Note that the filter width does nothing when only sinusoidal modulation is in use.

Noise Blend sets how the sinusoidal and noise modulation carriers get mixed. At 0%, the input signal is modulated by a sine wave alone, whereas at 100%, only noise does the modulating. The sine wave and noise icons under the display shift in brightness as you change the blend, signaling which modulation carrier dominates. Within the display, the sinusoidal modulation appears as a solid vertical line while the noise modulation appears as horizontal dotted lines.

The Filter Width control sets the bandwidth of the noise filter. Smaller values yield a tighter frequency range, whereas larger values stretch it over a broader slice of the spectrum. Note that with Noise Blend at 0%, the Filter Width control is grayed out, since it does nothing to the sinusoidal modulation.

The Stereo Width control lets you shift the modulation source from mono (0.0%) toward stereo (100%). Larger values introduce a gentle stereo widening to the modulation.

Any Sets built before 12.4 containing Erosion will open the older form of the device, which now goes by Erosion Legacy.
