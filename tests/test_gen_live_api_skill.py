"""Generator for the push3-live-api skill: seed Markdown in, reference files out."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gen_live_api_skill", ROOT / "tools" / "gen_live_api_skill.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

NEW_SEED = '''---
module: Clip
---

## Classes

### Clip

```yaml
kind: class
path: Live.Clip.Clip
ancestors:
- Live.LomObject.LomObject
- Boost.Python.instance
constructable: false
raw_doc: |-
  This class represents a Clip
  in Live.
```

#### Properties

##### color

```yaml
kind: property
settable: true
listenable: true
raw_doc: Get/set the color.
```

##### gain

```yaml
kind: property
settable: false
raw_doc: The gain.
```

#### Methods

##### fire

```yaml
kind: method
signature: 'fire( (Clip)arg1) -> None :'
args:
- name: force
  type: bool | None
returns:
  type: None
raw_doc: Fire the clip.
```

### WarpMarker

```yaml
kind: class
path: Live.Clip.WarpMarker
```

#### Methods

##### `__init__`

```yaml
kind: method
signature: '__init__( (object)arg1) -> None :'
```

## Enums

### LaunchMode

```yaml
kind: enum
members:
  trigger: 0
  gate: 1
```
'''

OLD_SEED = NEW_SEED.replace("##### gain", "##### old_gain").replace(
    "  gate: 1\n", ""
) + '''
### Removed

```yaml
kind: class
path: Live.Clip.Removed
```
'''

PROV = {"live_version": "12.4.6", "edition": "Intro", "platform": "Push 3", "capture": "raw", "captured": "2026-10-26"}


@pytest.fixture
def seeds(tmp_path):
    new = tmp_path / "12.4.6" / "seed"
    old = tmp_path / "12.3.6" / "seed"
    for d, text in ((new, NEW_SEED), (old, OLD_SEED)):
        d.mkdir(parents=True)
        (d / "Clip.md").write_text(text, encoding="utf-8")
    return new, old, tmp_path / "out"


def test_parse_groups_members_under_their_class(seeds):
    data = gen.parse_seed_file(seeds[0] / "Clip.md")
    assert data["module"] == "Clip"
    clip, warp = data["classes"]
    assert [n for n, _ in clip["properties"]] == ["color", "gain"]
    assert [n for n, _ in clip["methods"]] == ["fire"]
    assert [n for n, _ in warp["methods"]] == ["__init__"]
    assert data["enums"][0][1]["members"] == {"trigger": 0, "gate": 1}


def test_module_reference_shows_access_signature_and_enum(seeds):
    new, old, out = seeds
    gen.generate(new, out, PROV, old)
    text = (out / "Clip.md").read_text(encoding="utf-8")
    assert "This class represents a Clip in Live." in text
    assert "- `color` (rw, listenable): Get/set the color." in text
    assert "- `gain` (r) *(new)*: The gain." in text
    assert "- `fire(force: bool | None) -> None`: Fire the clip." in text
    assert "- `LaunchMode`: trigger=0, gate=1" in text
    assert "Live 12.4.6, Intro, Push 3" in text


def test_changes_lists_added_changed_and_missing(seeds):
    new, old, out = seeds
    stats = gen.generate(new, out, PROV, old)
    text = (out / "CHANGES.md").read_text(encoding="utf-8")
    assert "# Changes from Live 12.3.6 to 12.4.6" in text
    assert "- `Live.Clip.Clip.gain`" in text
    assert "`Live.Clip.LaunchMode`: was `enum trigger=0`, now `enum trigger=0, gate=1`" in text
    assert "- `Live.Clip.Clip.old_gain`" in text and "- `Live.Clip.Removed`" in text
    assert "unverified" in text  # raw capture caveat
    assert stats == {"modules": 1, "added": 1, "removed": 2, "changed": 1, "borrowed_types": 0}


def test_types_are_borrowed_from_baseline_for_shared_properties(seeds):
    new, old, out = seeds
    old_clip = old / "Clip.md"
    old_clip.write_text(
        old_clip.read_text(encoding="utf-8")
        .replace("settable: true\nlistenable: true", "type: int\nsettable: true\nlistenable: true")
        .replace("##### old_gain\n\n```yaml\n", "##### old_gain\n\n```yaml\ntype: float\n"),
        encoding="utf-8",
    )
    stats = gen.generate(new, out, PROV, old)
    text = (out / "Clip.md").read_text(encoding="utf-8")
    assert stats["borrowed_types"] == 1
    assert "- `color` `int`† (rw, listenable)" in text
    assert "- `gain` (r) *(new)*" in text  # new property: nothing to borrow
    assert "Types marked † come from the Live 12.3.6 property probe" in text


def test_capture_types_win_over_baseline(seeds):
    new, old, out = seeds
    for path, typ in ((new / "Clip.md", "bool"), (old / "Clip.md", "int")):
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "settable: true\nlistenable: true", f"type: {typ}\nsettable: true\nlistenable: true"
            ),
            encoding="utf-8",
        )
    gen.generate(new, out, PROV, old)
    text = (out / "Clip.md").read_text(encoding="utf-8")
    assert "- `color` `bool` (rw, listenable)" in text and "†" not in text


def test_generate_replaces_stale_files(seeds):
    new, _, out = seeds
    out.mkdir()
    (out / "Gone.md").write_text("stale", encoding="utf-8")
    gen.generate(new, out, PROV)
    assert sorted(p.name for p in out.iterdir()) == ["Clip.md", "INDEX.md"]
