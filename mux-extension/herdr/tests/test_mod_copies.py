"""Herdr mods can't import from another mod's folder, so shared helpers are copied into each mod
that uses them. The copies must stay identical to the source in mods/muxbar/."""
import pathlib

MODS = pathlib.Path(__file__).resolve().parents[3] / "herdr-app" / "mods"


def test_mux_js_copies_match_source():
    src = (MODS / "muxbar" / "mux.js").read_bytes()
    copies = [p for p in MODS.glob("*/mux.js") if p.parent.name != "muxbar"]
    assert copies, "no copies found"
    for p in copies:
        assert p.read_bytes() == src, f"{p.parent.name}/mux.js differs from muxbar/mux.js"


def test_ask_js_copies_match_source():
    src = (MODS / "muxbar" / "ask.js").read_bytes()
    for p in MODS.glob("*/ask.js"):
        assert p.read_bytes() == src, f"{p.parent.name}/ask.js differs from muxbar/ask.js"


def test_role_icons_exist():
    text = (MODS / "muxbar" / "mux.js").read_text(encoding="utf-8")
    import re
    names = set(re.findall(r'"(\w+)"\]', text)) | {"bot"}
    for n in names:
        assert (MODS / "muxbar" / "icons" / f"{n}.svg").is_file(), n
