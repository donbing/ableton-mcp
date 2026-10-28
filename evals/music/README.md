# Music evals

Does Claude need music skills to drive Live well, or does it already know this? These evals answer that with evidence: about 95 musical tasks, each one graded by code, run several times, with the score per category and its confidence interval.

## How it works

- **Graded by code, never by a model.** An item either has an exact answer key (chord spellings, Roman numerals, scales, intervals, Live's note numbering and timing) or musical rules that code can check (chord tones in each bar, bass on the root, no parallel fifths, kick on every beat). A skill can't win by sounding confident.
- **Answer keys are computed, then checked twice.** `theory.py` derives every key. `tests/test_music_evals.py` checks the keys against music21 and against answers worked out by hand. It also checks that each grader passes a right answer and fails a wrong one. Two items music21 read differently (a 13th chord's 11th, and bVI in a minor key) were dropped as ambiguous.
- **Answers use the note format Live's tools take** (`pitch`, `start_time` in beats, `duration`, `velocity`). So a pass means the notes would land correctly in a clip.
- **Repeated samples.** Each item runs `--samples` times. The report separates items that are always right, always wrong and *flaky*. A skill helps differently with each kind.
- **Isolated calls.** Each call goes through the `claude` CLI with no tools, no MCP servers, no settings and an empty working directory. The only things that reach the model are the item and the condition.

## Categories

| category | what it tests | graded on |
|---|---|---|
| chord_spelling | notes of Bb7#9, Ab7b9, Dm(maj7)… | pitch classes (spelling reported separately) |
| scales_modes | phrygian dominant, locrian, melodic minor… | pitch classes (spelling reported) |
| roman_numerals | progressions with secondary dominants, borrowed chords, the Neapolitan | each chord's notes |
| intervals | spelling an interval above or below a note | the note |
| live_conventions | Live's C3 = MIDI 60, Drum Rack pads, beat positions, odd meters, General MIDI drum numbers | the number |
| chord_id | naming a chord from MIDI numbers | notes and root |
| progression_midi | a progression written as clip notes, as block chords or arpeggios | chord tones per bar, bass, rhythm, no overhang |
| voice_leading | four-part (SATB) realisations | chord tones, ranges, spacing, crossing, parallel fifths and octaves |
| melody | a 4-bar line over chords | scale, chord tones on beats 1 and 3, range, no gaps, ends on the tonic |
| drums | house, rock, trap, drum & bass, dembow, one-drop | each genre's defining hits, in every bar |

## Running

```sh
uv run --with music21 --with pytest pytest tests/test_music_evals.py   # keys and graders
python3 -m evals.music.run --condition baseline --samples 3            # ~285 calls
python3 -m evals.music.run --condition reference-docs --samples 3
python3 -m evals.music.run --model claude-haiku-5-5 --samples 3
python3 -m evals.music.report evals/music/results/<a> evals/music/results/<b> --out report.md
```

`--category` (repeatable) and `--limit` give quicker runs. `--answer-format notation` has the note-writing items (progressions, melodies, drums) answered in `add_notes_to_clip`'s text notation instead of JSON, graded the same way, to compare accuracy and tokens; the report gives the median answer tokens (output minus thinking). Each run writes its own folder under `results/`: `meta.json` (including the exact system prompt) and `results.jsonl` (every reply, its checks and its cost).

## Testing a skill

Add `conditions/<name>.md` containing what the skill would teach, run with `--condition <name>`, and compare against baseline with `report.py`. The comparison counts the items that got better and worse, with a sign test, so a difference within the noise reads as one.

The rule we use: **a skill is worth adding for a category when baseline misses there consistently (always-wrong items, not just flaky ones), and when the skill's condition fixes those items without breaking others.** If baseline is already near 100%, a skill for that category only costs context.

`conditions/reference-docs.md` is the off-the-shelf comparison: the seven theory references from [tubone24/midi-mcp-server](https://github.com/tubone24/midi-mcp-server), used unchanged under its MIT licence. Note that it describes durations in its own string format ("d4", "T8"), not Live's beats. That is a realistic hazard of borrowing reference material.

`conditions/glincker-groove-builder.md` is a drum skill from [glincker/ableton-skills](https://github.com/glincker/ableton-skills) (MIT), used unchanged. Its trap template is labelled "half-time feel" but puts the snare on beats 2 and 4. Opus ignored that and put the snare on beat 3 in all three trials, so the drums score didn't change. Run it on a smaller model before assuming the same holds there.

## Related work (surveyed 2026-10)

**Benchmarks.** These test music knowledge in the abstract, not in a DAW:
- [MusicTheoryBench](https://ar5iv.labs.arxiv.org/html/2406.15885) (from ChatMusician; 367 items designed by people, with knowledge and reasoning splits). It's on Hugging Face (`m-a-p/MusicTheoryBench`) and would make a good harder tier. This environment's network policy blocks huggingface.co.
- [ZIQI-Eval](https://aclanthology.org/2024.findings-acl.194.pdf) (14k mostly factual questions), [ABC-Eval](https://arxiv.org/html/2509.23350) (ABC notation), [CMI-Bench](https://arxiv.org/pdf/2506.12285), [CSyMR](https://arxiv.org/pdf/2601.11556) (score reasoning, where tool-grounded agents win), [LilyBench](https://arxiv.org/html/2606.08722) (LilyPond generation) and [Libretto](https://arxiv.org/pdf/2606.22708) (musical structure for agents).

**Evals of driving Live.** [Producer Pal](https://github.com/adamjmurray/producer-pal) (GPL-3.0, so we can read it but not copy its code) has the most mature suite: about 100 scenarios against a real Live set, deterministic checks, and a log of findings. Its strong-model runs pass 87-91%, so the failures are in tool use, not theory. Lessons worth taking from it:
- Grade the end state, not the route the model took.
- A run that never reached the model is a discard, not a failure.
- Record the commit with every result.
- A skill's only example gets copied line for line, even when the user asked for something else.
- Check that each skill fragment actually reaches the model, before running the full suite.

**Skills.** Most of these are written for other servers' tool names and would need adapting:
- [PerIPan/music-workflow-skills](https://github.com/PerIPan/music-workflow-skills) (MIT) targets the upstream AbletonMCP. 8 of the tool names its main skill uses still exist here; about a dozen don't.
- [glincker/ableton-skills](https://github.com/glincker/ableton-skills) (MIT, 12 workflow skills for mixing, sidechain, mastering prep and arrangement).
- [Korben00/ableton-producer-skills](https://github.com/Korben00/ableton-producer-skills) (MIT, 14, built on the Extension SDK).
- [valentijnh/livebridge-ableton-mcp](https://github.com/valentijnh/livebridge-ableton-mcp) (MIT, one 268-line skill).
- [LevyBytes/AI-SKILL-ableton-live](https://github.com/LevyBytes/AI-SKILL-ableton-live) (Apache-2.0, reference material).
- [bitwize-music-studio/claude-ai-music-skills](https://github.com/bitwize-music-studio/claude-ai-music-skills) (CC0, 53 skills, mostly songwriting and Suno).

## Credits

The topics follow the references in [tubone24/midi-mcp-server](https://github.com/tubone24/midi-mcp-server) and the code-checked approach of [voho/midi-composer-mcp](https://github.com/voho/midi-composer-mcp) and [kennethreitz/pytheory-skill](https://github.com/kennethreitz/pytheory-skill), all MIT-licensed. No code was copied from them. The answer keys are our own and are checked against [music21](https://github.com/cuthbertLab/music21).
