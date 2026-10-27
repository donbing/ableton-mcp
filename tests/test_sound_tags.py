"""Live 12 browser tags read from the libraries' XMP files (list_sound_tags, search_sounds_by_tags)."""
import json
import os

import pytest

import MCP_Server.server as server
from MCP_Server import sound_tags

XMP = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:ablFR="https://ns.ableton.com/xmp/fs-resources/1.0/">
   <ablFR:items><rdf:Bag>
    <rdf:li rdf:parseType="Resource">
     <ablFR:filePath>Racks/Instrument Racks/Piano &amp; Keys/Ac Piano Upright.adg</ablFR:filePath>
     <ablFR:keywords><rdf:Bag>
      <rdf:li>Character|Basic</rdf:li><rdf:li>Character|Soft</rdf:li>
      <rdf:li>Sounds|Piano &amp; Keys|Piano</rdf:li>
     </rdf:Bag></ablFR:keywords>
    </rdf:li>
    <rdf:li rdf:parseType="Resource">
     <ablFR:filePath>Racks/Instrument Racks/Piano &amp; Keys/Music Box.adg</ablFR:filePath>
     <ablFR:keywords><rdf:Bag>
      <rdf:li>Character|Basic</rdf:li><rdf:li>Sounds|Piano &amp; Keys|Misc Keys</rdf:li>
     </rdf:Bag></ablFR:keywords>
    </rdf:li>
    <rdf:li rdf:parseType="Resource">
     <ablFR:filePath>Samples/One Shots/Drums/Clap/Snap Soft.wav</ablFR:filePath>
     <ablFR:keywords><rdf:Bag><rdf:li>Character|Soft</rdf:li><rdf:li>Type|One Shot</rdf:li></rdf:Bag></ablFR:keywords>
    </rdf:li>
    <rdf:li rdf:parseType="Resource">
     <ablFR:filePath>Racks/Untagged.adg</ablFR:filePath>
     <ablFR:colors><rdf:Bag><rdf:li>1</rdf:li></rdf:Bag></ablFR:colors>
    </rdf:li>
   </rdf:Bag></ablFR:items>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


@pytest.fixture
def roots(tmp_path, monkeypatch):
    info = tmp_path / "Live 12 Core Library" / "Ableton Folder Info"
    info.mkdir(parents=True)
    (info / "pack.xmp").write_text(XMP, encoding="utf-8")
    (tmp_path / "Sets").mkdir()
    monkeypatch.setenv("ABLETON_LIBRARY_ROOTS", str(tmp_path))
    sound_tags._cache.clear()
    return [tmp_path]


def test_parses_tagged_items_and_skips_untagged(roots):
    items = sound_tags.load_items()
    assert [i["name"] for i in items] == ["Ac Piano Upright.adg", "Music Box.adg", "Snap Soft.wav"]
    assert items[0]["library"] == "Live 12 Core Library"
    assert items[0]["path"] == "Racks/Instrument Racks/Piano & Keys/Ac Piano Upright.adg"


def test_terms_match_whole_tags_parts_and_endings():
    assert sound_tags.tag_matches("soft", "Character|Soft")
    assert sound_tags.tag_matches("Character|Soft", "Character|Soft")
    assert sound_tags.tag_matches("piano & keys|piano", "Sounds|Piano & Keys|Piano")
    assert sound_tags.tag_matches("Sounds|Piano & Keys", "Sounds|Piano & Keys|Piano")
    assert not sound_tags.tag_matches("pian", "Sounds|Piano & Keys|Piano")


def test_same_folder_twice_is_read_once(roots, monkeypatch):
    monkeypatch.setenv("ABLETON_LIBRARY_ROOTS", str(roots[0]) + os.pathsep + str(roots[0] / "Sets" / ".."))
    assert len(sound_tags.load_items()) == 3


def test_search_needs_every_tag_and_filters_kind(roots):
    items = sound_tags.load_items()
    assert len(sound_tags.search(items, ["soft"], kind="all")) == 2
    page = sound_tags.search(items, ["soft"], kind="presets")
    assert [i["name"] for i in page] == ["Ac Piano Upright.adg"]
    assert sound_tags.search(items, ["soft", "misc keys"], kind="all") == []
    assert len(sound_tags.search(items, ["basic"], query="music", kind="all")) == 1


def test_browser_category_follows_the_library_folder(roots):
    piano, _, snap = sound_tags.load_items()
    assert sound_tags.browser_category(piano) == "sounds"
    assert sound_tags.browser_category(snap) == "samples"
    assert sound_tags.browser_category(dict(piano, library="User Library")) == "user_library"


def test_vocabulary_counts_and_prefix(roots):
    vocab = sound_tags.vocabulary(sound_tags.load_items(), "character")
    assert vocab == {"Character|Basic": 2, "Character|Soft": 2}


class Browser:
    """Lists only the items in `listed`, like Live Intro hiding Suite-only presets."""
    def __init__(self, listed):
        self.listed, self.calls = listed, []

    def send_command(self, kind, params):
        assert kind == "search_browser_items"
        self.calls.append((params["category"], params["query"]))
        names = [n for n in self.listed if params["query"] in n]
        return {"results": [{"name": "Ac Piano Upright Bright.adg", "uri": "wrong"}]
                + [{"name": n, "uri": "query:" + n} for n in names]}


@pytest.fixture
def browser(monkeypatch):
    server._browser_uris.clear()
    b = Browser(["Music Box.adg"])
    monkeypatch.setattr(server, "get_ableton_connection", lambda: b)
    return b


def test_tool_resolves_uris_by_exact_name_and_drops_what_live_hides(roots, browser):
    reply = json.loads(server.search_sounds_by_tags(None, ["basic"]))
    assert reply["matching_tags"] == 2 and reply["not_in_browser"] == 1
    assert [(r["name"], r["uri"]) for r in reply["results"]] == [("Music Box.adg", "query:Music Box.adg")]
    assert browser.calls == [("sounds", "Ac Piano Upright"), ("sounds", "Music Box")]
    assert "uri" not in sound_tags.load_items()[1]            # the parsed items are not mutated
    server.search_sounds_by_tags(None, ["basic"])
    assert len(browser.calls) == 2                            # lookups are remembered


def test_presets_of_a_missing_device_are_not_searched(roots, browser, monkeypatch):
    items = [{"name": "Glow.adv", "path": "Devices/Instruments/Wavetable/Pad/Glow.adv",
              "library": "Live 12 Core Library", "tags": ["Sounds|Pad"]},
             {"name": "Warm.adv", "path": "Devices/Instruments/Drift/Pad/Warm.adv",
              "library": "Live 12 Core Library", "tags": ["Sounds|Pad"]}]
    monkeypatch.setattr(sound_tags, "load_items", lambda: [dict(i) for i in items])
    browser.listed = ["Drift", "Warm.adv"]
    reply = json.loads(server.search_sounds_by_tags(None, ["pad"]))
    assert [r["name"] for r in reply["results"]] == ["Warm.adv"]
    assert browser.calls == [("instruments", "Drift"), ("instruments", "Warm"), ("instruments", "Wavetable")]


def test_tool_can_return_unavailable_items(roots, browser):
    reply = json.loads(server.search_sounds_by_tags(None, ["basic"], available_only=False))
    assert [(r["name"], r["uri"]) for r in reply["results"]] == [
        ("Ac Piano Upright.adg", None), ("Music Box.adg", "query:Music Box.adg")]


def test_tool_without_live(roots, monkeypatch):
    server._browser_uris.clear()

    class Down:
        def send_command(self, *a):
            raise ConnectionError("Not connected to Ableton")
    monkeypatch.setattr(server, "get_ableton_connection", lambda: Down())
    assert "could not ask Live's browser" in server.search_sounds_by_tags(None, ["basic"])
    reply = json.loads(server.search_sounds_by_tags(None, ["basic"], available_only=False))
    assert reply["count"] == 2 and "browser_error" in reply


def test_tool_reports_missing_tag_files(tmp_path, monkeypatch):
    monkeypatch.setenv("ABLETON_LIBRARY_ROOTS", str(tmp_path))
    assert "no tag files found" in server.list_sound_tags(None)
