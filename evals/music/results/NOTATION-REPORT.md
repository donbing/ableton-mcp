# Music eval report

## Against baseline

| category | baseline (claude-opus-5-5) | baseline (claude-opus-5-5) | better / worse items | sign test p |
|---|---|---|---|---|
| progression_midi | 100% | 100% | 0 / 0 | 1.00 |
| melody | 100% | 100% | 0 / 0 | 1.00 |
| drums | 100% | 100% | 0 / 0 | 1.00 |
| **all** | 100% | 100% | 0 / 0 | 1.00 |

## baseline · claude-opus-5-5

16 items × 3 samples, $1.71

| category | pass | 95% CI | items always right | always wrong | flaky | unreadable | reply tokens (median) | answer block chars (median) |
|---|---|---|---|---|---|---|---|---|
| progression_midi | 100% | 82%–100% | 6 | 0 | 0 | 0 | 877 | 1025 |
| melody | 100% | 76%–100% | 4 | 0 | 0 | 0 | 919 | 1176 |
| drums | 100% | 82%–100% | 6 | 0 | 0 | 0 | 1581 | 2481 |
| **all** | 100% | 93%–100% | 16 | 0 | 0 | 0 | 1051 | 1401 |

## baseline · claude-opus-5-5 · notes as notation

16 items × 3 samples, $1.68

| category | pass | 95% CI | items always right | always wrong | flaky | unreadable | reply tokens (median) | answer block chars (median) |
|---|---|---|---|---|---|---|---|---|
| progression_midi | 100% | 82%–100% | 6 | 0 | 0 | 0 | 992 | 176 |
| melody | 100% | 76%–100% | 4 | 0 | 0 | 0 | 608 | 350 |
| drums | 100% | 82%–100% | 6 | 0 | 0 | 0 | 455 | 393 |
| **all** | 100% | 93%–100% | 16 | 0 | 0 | 0 | 578 | 347 |

## Notes as JSON vs as notation: what a tool call would carry

Opus 5.5, the 16 note-writing items × 3 samples each way, all graded by the same code. Median size of the answer block, with the JSON minified so it isn't penalised for pretty-printing:

| category | JSON (minified) | notation | notation without Claude's comments | saving |
|---|---|---|---|---|
| progression_midi | 895 | 176 | 83 | 80% |
| melody | 1004 | 340 | 293 | 66% |
| drums | 2079 | 382 | 154 | 82% |
| **all** | 1228 | 339 | 159 | 72% |

Accuracy: 48/48 both ways. The notation run first scored 47/48. In one drum answer Claude wrote the pitch before the position (`36 1.3,2.3 1/16`), copying the order of step lines. A position can't be mistaken for anything else, so the parser now accepts it anywhere on an event line, and the saved replies were regraded (`run.py --regrade`).

Reply tokens (prose included) fall less, and progressions rose: Claude explained its voicings at length. That's Claude's choice of commentary, not the cost of the notes. In a tool call, only the block is sent.
