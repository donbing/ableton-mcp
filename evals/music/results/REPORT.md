# Music eval report

## Against baseline

| category | baseline (claude-opus-5-5) | reference-docs (claude-opus-5-5) | baseline (claude-haiku-5-5) | better / worse items | sign test p |
|---|---|---|---|---|---|
| chord_spelling | 100% | 100% | 92% | 0 / 0; 0 / 2 | 1.00; 0.50 |
| scales_modes | 100% | 100% | 92% | 0 / 0; 0 / 3 | 1.00; 0.25 |
| roman_numerals | 100% | 100% | 94% | 0 / 0; 0 / 2 | 1.00; 0.50 |
| intervals | 100% | 100% | 100% | 0 / 0; 0 / 0 | 1.00; 1.00 |
| live_conventions | 100% | 100% | 100% | 0 / 0; 0 / 0 | 1.00; 1.00 |
| chord_id | 100% | 100% | 94% | 0 / 0; 0 / 2 | 1.00; 0.50 |
| progression_midi | 100% | 100% | 100% | 0 / 0; 0 / 0 | 1.00; 1.00 |
| voice_leading | 100% | 100% | 78% | 0 / 0; 0 / 2 | 1.00; 0.50 |
| melody | 100% | 100% | 100% | 0 / 0; 0 / 0 | 1.00; 1.00 |
| drums | 100% | 100% | 83% | 0 / 0; 0 / 1 | 1.00; 1.00 |
| **all** | 100% | 100% | 94% | 0 / 0; 0 / 12 | 1.00; 0.00 |

## baseline · claude-opus-5-5

95 items × 3 samples, $4.43

| category | pass | 95% CI | items always right | always wrong | flaky | unreadable |
|---|---|---|---|---|---|---|
| chord_spelling | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| scales_modes | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| roman_numerals | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| intervals | 100% | 88%–100% | 9 | 0 | 0 | 0 |
| live_conventions | 100% | 93%–100% | 16 | 0 | 0 | 0 |
| chord_id | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| progression_midi | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| voice_leading | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| melody | 100% | 76%–100% | 4 | 0 | 0 | 0 |
| drums | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| **all** | 100% | 99%–100% | 95 | 0 | 0 | 0 |

Of the right note-name answers, 100% were also spelled correctly (e.g. E# not F in F# harmonic minor).

## reference-docs · claude-opus-5-5

95 items × 3 samples, $5.37

| category | pass | 95% CI | items always right | always wrong | flaky | unreadable |
|---|---|---|---|---|---|---|
| chord_spelling | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| scales_modes | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| roman_numerals | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| intervals | 100% | 88%–100% | 9 | 0 | 0 | 0 |
| live_conventions | 100% | 93%–100% | 16 | 0 | 0 | 0 |
| chord_id | 100% | 90%–100% | 12 | 0 | 0 | 0 |
| progression_midi | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| voice_leading | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| melody | 100% | 76%–100% | 4 | 0 | 0 | 0 |
| drums | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| **all** | 100% | 99%–100% | 95 | 0 | 0 | 0 |

Of the right note-name answers, 100% were also spelled correctly (e.g. E# not F in F# harmonic minor).

## baseline · claude-haiku-5-5

95 items × 3 samples, $0.27

| category | pass | 95% CI | items always right | always wrong | flaky | unreadable |
|---|---|---|---|---|---|---|
| chord_spelling | 92% | 78%–97% | 10 | 0 | 2 | 0 |
| scales_modes | 92% | 78%–97% | 9 | 0 | 3 | 0 |
| roman_numerals | 94% | 82%–98% | 10 | 0 | 2 | 0 |
| intervals | 100% | 88%–100% | 9 | 0 | 0 | 0 |
| live_conventions | 100% | 93%–100% | 16 | 0 | 0 | 0 |
| chord_id | 94% | 82%–98% | 10 | 0 | 2 | 0 |
| progression_midi | 100% | 82%–100% | 6 | 0 | 0 | 0 |
| voice_leading | 78% | 55%–91% | 4 | 0 | 2 | 0 |
| melody | 100% | 76%–100% | 4 | 0 | 0 | 0 |
| drums | 83% | 61%–94% | 5 | 1 | 0 | 0 |
| **all** | 94% | 91%–96% | 83 | 1 | 11 | 0 |

Of the right note-name answers, 99% were also spelled correctly (e.g. E# not F in F# harmonic minor).

Most failed checks:

- chord_spelling · `pitch_classes` × 3
- scales_modes · `pitch_classes` × 3
- voice_leading · `no_parallel_5ths_8ves` × 3
- drums · `kick_every_beat` × 3
- drums · `dembow_snare` × 3
- chord_id · `pitch_classes` × 2
- roman_numerals · `chord_2_V/V` × 1
- roman_numerals · `chord_2_N6` × 1
- voice_leading · `chord_tones` × 1

<details><summary>Items failed at least once (12)</summary>

- `chord_id/Bm7b5`: want Bm7b5, got Bdim7
- `chord_id/C#dim7`: want C#dim7, got C#7
- `chord_spelling/C#dim7`: want ['C#', 'E', 'G', 'Bb'], got ['C#', 'E', 'G', 'Bbb']
- `chord_spelling/Ebmaj7#11`: want ['Eb', 'G', 'Bb', 'D', 'A'], got ['Eb', 'G', 'Bb', 'D', 'A#']
- `drums/dembow`: bar1 kick_every_beat [0.0, 1.5, 3.0]; bar1 dembow_snare [0.75, 1.0, 2.25, 3.0]
- `roman_numerals/Bb major I-N6-V7-I`: want [['Bb', 'D', 'F'], ['Eb', 'Cb', 'Gb'], ['F', 'A', 'C', 'Eb'], ['Bb', 'D', 'F']], got [['Bb', 'D', 'F'], ['F', 'Ab', 'Db'], ['F', 'A', 'C', 'Eb'], ['Bb', 'D', 'F']]
- `roman_numerals/D major I-V/V-V-I`: want [['D', 'F#', 'A'], ['E', 'G#', 'B'], ['A', 'C#', 'E'], ['D', 'F#', 'A']], got [['D', 'F#', 'A'], ['A', 'C#', 'E'], ['A', 'C#', 'E'], ['D', 'F#', 'A']]
- `scales_modes/Bb lydian`: want ['Bb', 'C', 'D', 'E', 'F', 'G', 'A'], got ['B', 'C', 'D', 'E', 'F', 'G', 'A']
- `scales_modes/C# major pentatonic`: want ['C#', 'D#', 'E#', 'G#', 'A#'], got ['C#', 'D#', 'E#', 'F#', 'G#']
- `scales_modes/Eb natural minor`: want ['Eb', 'F', 'Gb', 'Ab', 'Bb', 'Cb', 'Db'], got ['E', 'F', 'G', 'A', 'B', 'C', 'D']
- `voice_leading/E minor i-VI-iv-V-i`: tones [True, True, True, True, False] bass [True, True, True, True, True]
- `voice_leading/G major I-vi-IV-V-I`: soprano/bass 2->3

</details>
