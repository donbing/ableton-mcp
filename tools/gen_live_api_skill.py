# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Generate the push3-live-api skill's reference files from a LiveAPI seed.

The seed is LiveAPI's per-module Markdown (probe/<version>/seed/*.md): headings
per class / member, each followed by a YAML block. This script turns it into
compact references an agent can read one module at a time, plus an index and a
diff against a baseline seed. Property types missing from a raw capture are
borrowed from the baseline (marked †).

Only files under references/ are written; SKILL.md stays hand-written.

    python tools/gen_live_api_skill.py \
        --seed ../LiveAPI/probe/12.4.6/seed \
        --baseline ../LiveAPI/probe/12.3.6/seed \
        --provenance .claude/skills/push3-live-api/provenance.json \
        --out .claude/skills/push3-live-api/references
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

HEADING = re.compile(r"^(#{2,5}) (.+?)\s*$")
FENCE_OPEN = "```yaml"
FENCE_CLOSE = "```"


# --- parsing -----------------------------------------------------------------


def parse_seed_file(path):
    """Return {"module": name, "classes": [...], "enums": [...], "functions": [...], "constants": [...]}.

    Each class is {"name", "info", "properties": [(name, info)], "methods": [(name, info)]}.
    """
    text = path.read_text(encoding="utf-8")
    module = path.stem
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if front:
        module = (yaml.safe_load(front.group(1)) or {}).get("module", module)
        text = text[front.end():]

    out = {"module": module, "classes": [], "enums": [], "functions": [], "constants": []}
    section = None  # "Classes", "Enums", ...
    current = None  # the class being filled
    member_section = None  # "Properties" / "Methods"
    pending = None  # (level, name) awaiting its YAML block

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEADING.match(line)
        if m:
            level, name = len(m.group(1)), m.group(2).strip("`")
            if level == 2:
                section, current, member_section, pending = name, None, None, None
            elif level == 3:
                pending, member_section = (3, name), None
            elif level == 4:
                member_section, pending = name, None
            else:
                pending = (5, name)
            i += 1
            continue
        if line.strip() == FENCE_OPEN and pending:
            block = []
            i += 1
            while i < len(lines) and lines[i].strip() != FENCE_CLOSE:
                block.append(lines[i])
                i += 1
            info = yaml.safe_load("\n".join(block)) or {}
            level, name = pending
            pending = None
            if level == 3:
                kind = info.get("kind")
                if kind == "class":
                    current = {"name": name, "info": info, "properties": [], "methods": []}
                    out["classes"].append(current)
                elif kind == "enum":
                    out["enums"].append((name, info))
                elif kind == "function":
                    out["functions"].append((name, info))
                elif kind == "constant":
                    out["constants"].append((name, info))
            elif current is not None and member_section in ("Properties", "Methods"):
                current[member_section.lower()].append((name, info))
        i += 1
    return out


def load_seed(seed_dir):
    return {m["module"]: m for m in (parse_seed_file(p) for p in sorted(Path(seed_dir).glob("*.md")))}


def class_path(module, cls):
    return cls["info"].get("path") or f"Live.{module}.{cls['name']}"


def member_keys(seed):
    """Flatten a seed to {key: summary} for diffing; key is a dotted path."""
    keys = {}
    for module, data in seed.items():
        for cls in data["classes"]:
            base = class_path(module, cls)
            keys[base] = "class"
            for name, info in cls["properties"]:
                keys[f"{base}.{name}"] = "property " + access(info)
            for name, info in cls["methods"]:
                keys[f"{base}.{name}()"] = "method " + str(info.get("signature", ""))
        for name, info in data["enums"]:
            keys[f"Live.{module}.{name}"] = "enum " + ", ".join(f"{k}={v}" for k, v in (info.get("members") or {}).items())
        for name, info in data["functions"]:
            keys[f"Live.{module}.{name}()"] = "function " + str(info.get("signature", ""))
        for name, info in data["constants"]:
            parent = info.get("parent")
            path = f"Live.{module}.{parent}.{name}" if parent else f"Live.{module}.{name}"
            keys[path] = f"constant {info.get('value')!r}"
    return keys


# --- rendering ---------------------------------------------------------------


def one_line(doc):
    text = " ".join(str(doc or "").split())
    # Live 12.4.15 gives undocumented getters Boost.Python's bare signature as a doc
    return "" if text.startswith("None( (") else text


# Live 12.4.15 module-qualifies the types in its signatures (`Track.Track`, `(Song.View)arg1`).
QUALIFIER = re.compile(r"\b[A-Z]\w*\.(?=[A-Z]\w*)")


def same_signature(old, new):
    """Equal once module qualifiers are dropped, so 12.4.15's spelling is not a change."""
    return QUALIFIER.sub("", str(old)) == QUALIFIER.sub("", str(new))


def short_type(t):
    return str(t).replace("Live.", "") if t else ""


def access(info):
    flags = "rw" if info.get("settable") else "r"
    if info.get("listenable"):
        flags += ", listenable"
    return flags


def call_signature(name, info):
    args = ", ".join(
        f"{a.get('name')}: {short_type(a.get('type'))}" if a.get("type") else str(a.get("name"))
        for a in info.get("args") or []
    )
    ret = short_type((info.get("returns") or {}).get("type"))
    return f"{name}({args})" + (f" -> {ret}" if ret else "")


def new_tag(key, added):
    return " *(new)*" if key in added else ""


def borrow_types(seed, baseline, baseline_version):
    """Fill missing property types from the baseline seed, for properties present in both.

    A raw capture has no property probe, so it lacks types; the baseline's came from a probe. Each borrowed type is
    marked with type_from so the reference can say where it came from. Returns the number borrowed.
    """
    known = {}
    for module, data in baseline.items():
        for cls in data["classes"]:
            for name, info in cls["properties"]:
                # "None" only means the probed value was empty at the time (no groove, nothing appointed).
                if info.get("type") and info["type"] not in ("None", "NoneType"):
                    known[f"{class_path(module, cls)}.{name}"] = info["type"]
    count = 0
    for module, data in seed.items():
        for cls in data["classes"]:
            for name, info in cls["properties"]:
                key = f"{class_path(module, cls)}.{name}"
                if not info.get("type") and key in known:
                    info["type"], info["type_from"] = known[key], baseline_version
                    count += 1
    return count


def render_module(module, data, added, header):
    out = [f"# Live.{module}", "", header, ""]
    borrowed = {
        p["type_from"] for c in data["classes"] for _, p in c["properties"] if p.get("type_from")
    }
    if borrowed:
        out += [f"Types marked † come from the Live {', '.join(sorted(borrowed))} property probe, not this capture.", ""]
    for cls in data["classes"]:
        info = cls["info"]
        path = class_path(module, cls)
        out.append(f"## {short_type(path)}{new_tag(path, added)}")
        out.append("")
        if info.get("raw_doc"):
            out += [one_line(info["raw_doc"]), ""]
        facts = []
        bases = [short_type(a) for a in info.get("ancestors") or [] if a != "Boost.Python.instance"]
        if bases:
            facts.append("Base: " + ", ".join(bases) + ".")
        if info.get("constructable") is False:
            facts.append("Not constructable from Python.")
        if info.get("iterable"):
            facts.append("Iterable.")
        if facts:
            out += [" ".join(facts), ""]
        if cls["properties"]:
            out += ["Properties (r = read-only, rw = settable):", ""]
            for name, p in cls["properties"]:
                typ = f" `{short_type(p['type'])}`" if p.get("type") else ""
                if p.get("type_from"):
                    typ += "†"
                doc = one_line(p.get("raw_doc"))
                out.append(f"- `{name}`{typ} ({access(p)}){new_tag(f'{path}.{name}', added)}" + (f": {doc}" if doc else ""))
            out.append("")
        if cls["methods"]:
            out += ["Methods:", ""]
            for name, m in cls["methods"]:
                doc = one_line(m.get("raw_doc"))
                out.append(f"- `{call_signature(name, m)}`{new_tag(f'{path}.{name}()', added)}" + (f": {doc}" if doc else ""))
            out.append("")
    if data["functions"]:
        out += ["## Functions", ""]
        for name, f in data["functions"]:
            doc = one_line(f.get("raw_doc"))
            out.append(f"- `{call_signature(name, f)}`{new_tag(f'Live.{module}.{name}()', added)}" + (f": {doc}" if doc else ""))
        out.append("")
    if data["enums"]:
        out += ["## Enums", ""]
        for name, e in data["enums"]:
            members = ", ".join(f"{k}={v}" for k, v in (e.get("members") or {}).items())
            out.append(f"- `{name}`{new_tag(f'Live.{module}.{name}', added)}: {members}")
        out.append("")
    if data["constants"]:
        out += ["## Constants", ""]
        for name, c in data["constants"]:
            parent = f"{c['parent']}." if c.get("parent") else ""
            out.append(f"- `{parent}{name}` = {c.get('value')!r}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def provenance_header(prov):
    parts = [f"Live {prov['live_version']}"]
    for key in ("edition", "platform"):
        if prov.get(key):
            parts.append(str(prov[key]))
    line = "Generated from a " + str(prov.get("capture", "")).strip() + " capture: " + ", ".join(parts)
    if prov.get("captured"):
        line += f", captured {prov['captured']}"
    return f"> {line}. Do not edit; regenerate with `tools/gen_live_api_skill.py`."


def render_index(seed, prov, header):
    out = [f"# Live {prov['live_version']} API: module index", "", header, ""]
    if prov.get("capture") == "raw":
        out += [
            "This is a raw capture without a property probe, so it has no property types of its own. Types marked †",
            "are borrowed from the older version's probe for properties present in both; properties with no type",
            "are new or were not probed. Check the value at runtime before relying on a type.",
            "",
        ]
    out += ["| Module | Classes | Members |", "|---|---|---|"]
    for module, data in seed.items():
        names = ", ".join(short_type(class_path(module, c)).split(".", 1)[-1] for c in data["classes"])
        count = sum(len(c["properties"]) + len(c["methods"]) for c in data["classes"]) + len(data["functions"])
        out.append(f"| [{module}]({module}.md) | {names or '-'} | {count} |")
    return "\n".join(out) + "\n"


def render_changes(added, removed, changed, prov, baseline_version, header):
    out = [f"# Changes from Live {baseline_version} to {prov['live_version']}", "", header, ""]
    out += [f"## Added ({len(added)})", ""] + [f"- `{k}`" for k in sorted(added)] + [""]
    out += [f"## Changed ({len(changed)})", ""]
    for k in sorted(changed):
        old, new = changed[k]
        out.append(f"- `{k}`: was `{old}`, now `{new}`")
    out += ["", f"## Missing from this capture ({len(removed)})", ""]
    if prov.get("capture") == "raw":
        out += [
            "A raw capture skips the property probe, so some of these are gaps in the capture rather than API",
            "removals. Treat each one as unverified until a full probe confirms it.",
            "",
        ]
    out += [f"- `{k}`" for k in sorted(removed)]
    return "\n".join(out).rstrip() + "\n"


# --- main --------------------------------------------------------------------


def generate(seed_dir, out_dir, provenance, baseline_dir=None):
    seed = load_seed(seed_dir)
    if not seed:
        raise SystemExit(f"no seed files in {seed_dir}")
    header = provenance_header(provenance)

    added, removed, changed = set(), set(), {}
    baseline_version, borrowed = None, 0
    if baseline_dir:
        baseline_version = Path(baseline_dir).parent.name
        baseline = load_seed(baseline_dir)
        old, new = member_keys(baseline), member_keys(seed)
        added = set(new) - set(old)
        removed = set(old) - set(new)
        changed = {k: (old[k], new[k]) for k in set(old) & set(new) if not same_signature(old[k], new[k])}
        borrowed = borrow_types(seed, baseline, baseline_version)

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for module, data in seed.items():
        (out_dir / f"{module}.md").write_text(render_module(module, data, added, header), encoding="utf-8")
    (out_dir / "INDEX.md").write_text(render_index(seed, provenance, header), encoding="utf-8")
    if baseline_dir:
        (out_dir / "CHANGES.md").write_text(
            render_changes(added, removed, changed, provenance, baseline_version, header), encoding="utf-8"
        )
    return {
        "modules": len(seed), "added": len(added), "removed": len(removed), "changed": len(changed),
        "borrowed_types": borrowed,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", required=True, help="LiveAPI probe/<version>/seed directory")
    ap.add_argument("--baseline", help="older seed directory to diff against and borrow property types from")
    ap.add_argument("--provenance", required=True, help="JSON file describing the capture")
    ap.add_argument("--out", required=True, help="references directory to (re)write")
    args = ap.parse_args(argv)
    prov = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
    stats = generate(args.seed, args.out, prov, args.baseline)
    print(json.dumps(stats))


if __name__ == "__main__":
    sys.exit(main())
