"""Live 12's browser tags (Character|Soft, Sounds|Pad, Type|One Shot...), read from disk.

Live keeps them in XMP files under each library's "Ableton Folder Info" folder, one
<rdf:li> per file with an ablFR:filePath and an ablFR:keywords bag. Live's Python API
does not expose them, so the MCP server reads the files itself; it runs where Live's
libraries are (on a Push 3 standalone, /data/Music/Ableton).
"""
import os
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
ABL = "{https://ns.ableton.com/xmp/fs-resources/1.0/}"
FOLDER_INFO = "Ableton Folder Info"

KINDS = {
    "presets": {".adg", ".adv", ".amxd"},
    "samples": {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"},
    "clips": {".alc", ".als"},
}

# Library folder -> the browser root that lists its items (for the uri lookup).
BROWSER_CATEGORIES = [
    ("Racks/Instrument Racks/", "sounds"),
    ("Racks/Drum Racks/", "drums"),
    ("Racks/Audio Effect Racks/", "audio_effects"),
    ("Racks/MIDI Effect Racks/", "midi_effects"),
    ("Devices/Instruments/", "instruments"),
    ("Devices/Audio Effects/", "audio_effects"),
    ("Devices/MIDI Effects/", "midi_effects"),
    ("Samples/", "samples"),
    ("MIDI Clips/", "clips"),
]

_cache: Dict[str, Tuple[float, List[dict]]] = {}


def default_roots() -> List[Path]:
    env = os.environ.get("ABLETON_LIBRARY_ROOTS")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p]
    home = Path.home()
    return [Path("/data/Music/Ableton"), home / "Music" / "Ableton", home / "Documents" / "Ableton"]


def browser_category(item: dict) -> str:
    """The browser root to look the item up in: "sounds" for an instrument rack, etc."""
    if item["library"] == "User Library":
        return "user_library"
    return next((cat for prefix, cat in BROWSER_CATEGORIES if item["path"].startswith(prefix)), "all")


def device_folder(item: dict) -> Optional[str]:
    """The device a device preset belongs to: Devices/Instruments/Drift/Pad/x.adv -> "Drift"."""
    parts = item["path"].split("/")
    if item["library"] != "User Library" and len(parts) > 3 and parts[0] == "Devices":
        return parts[2]
    return None


def find_xmp_files(roots: Iterable[Path], max_depth: int = 3) -> List[Path]:
    """Every XMP under an "Ableton Folder Info" folder, at most max_depth folders below a root.
    Roots that are the same folder (on a Push, ~ is /data) are walked once."""
    found, seen = [], set()
    for root in roots:
        if not root.is_dir() or root.resolve() in seen:
            continue
        seen.add(root.resolve())
        base = len(root.parts)
        for dirpath, dirnames, _ in os.walk(root):
            here = Path(dirpath)
            if here.name == FOLDER_INFO:
                found += sorted(here.rglob("*.xmp"))
                dirnames[:] = []
            elif len(here.parts) - base >= max_depth:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
    return found


def parse_xmp(path: Path) -> List[dict]:
    """Items with at least one keyword: name, path (relative to the library), library, tags."""
    path = Path(path)
    mtime = path.stat().st_mtime
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    library_root = next(p for p in path.parents if p.name == FOLDER_INFO).parent
    items = []
    for li in ET.parse(path).getroot().iter(RDF + "li"):
        rel = li.findtext(ABL + "filePath")
        keywords = li.find(ABL + "keywords")
        if not rel or keywords is None:
            continue
        tags = [t.text for t in keywords.iter(RDF + "li") if t.text]
        if tags:
            items.append({"name": rel.rsplit("/", 1)[-1], "path": rel,
                          "library": library_root.name, "tags": tags})
    _cache[str(path)] = (mtime, items)
    return items


def load_items(roots: Optional[Iterable[Path]] = None) -> List[dict]:
    items = []
    for xmp in find_xmp_files(roots if roots is not None else default_roots()):
        try:
            items += parse_xmp(xmp)
        except (ET.ParseError, OSError, StopIteration):
            continue
    return items


def tag_matches(term: str, tag: str) -> bool:
    """'soft' matches Character|Soft; the full tag, its start (Sounds|Strings) or end match too."""
    term, tag = term.strip().lower(), tag.lower()
    return (term == tag or term in tag.split("|") or tag.endswith("|" + term)
            or tag.startswith(term + "|"))


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    return next((k for k, exts in KINDS.items() if ext in exts), "other")


def search(items: List[dict], tags: List[str], query: str = "", kind: str = "all") -> List[dict]:
    """Copies of the items carrying every tag term and every query word (in the path)."""
    words = query.lower().split()
    hits = [it for it in items
            if (kind == "all" or kind_of(it["name"]) == kind)
            and all(any(tag_matches(t, tag) for tag in it["tags"]) for t in tags)
            and all(w in it["path"].lower() for w in words)]
    hits.sort(key=lambda it: (it["library"], it["path"].lower()))
    return [dict(it) for it in hits]


def vocabulary(items: List[dict], prefix: str = "") -> Dict[str, int]:
    """Tag -> how many items carry it, optionally only tags under a prefix ("Character")."""
    counts = Counter(tag for it in items for tag in set(it["tags"]))
    p = prefix.strip().lower()
    return dict(sorted((t, c) for t, c in counts.items() if not p or t.lower().startswith(p)))
