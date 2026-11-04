"""The looks: generated files are current, and they stay inside what Mux and Herdr accept."""
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
EXT = json.loads((REPO / "mux-extension" / "herdr-looks" / "extension.json").read_text(encoding="utf-8"))
PAL = json.loads((REPO / "looks" / "palettes.json").read_text(encoding="utf-8"))
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ROLES = {"step", "success", "warning", "error", "info", "muted", "accent", "prompt", "banner", "agent", "mdHeading",
         "mdCode", "mdLink", "mdQuote", "cardBg", "inputBg", "diffAddBg", "diffDelBg", "diffHunkBg", "codeBg",
         "inlineCodeBg", "border", "text"}


def test_generated_files_are_current():
    r = subprocess.run([sys.executable, str(REPO / "looks" / "build.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_one_theme_per_palette_and_valid_colours():
    names = [t["name"] for t in EXT["themes"]]
    assert names == [f"herdr-{n}" for n in PAL["looks"]]
    for t in EXT["themes"]:
        assert t["base"] in ("dark", "light")
        for k, v in t.items():
            if k not in ("name", "base"):
                assert k in ROLES, k
                assert HEX.match(v), (t["name"], k, v)


def test_regions_use_roles_not_hex():
    """Shape is shared by every look, so its colours must be theme roles (they follow /theme)."""
    for region, props in EXT["tui"]["regions"].items():
        for k, v in props.items():
            if k.endswith("Fg") or k.endswith("Bg"):
                assert v in ROLES, f"{region}.{k}={v}"


def test_limits():
    art = EXT["tui"]["regions"]["splash"]["art"]
    assert 1 <= len(art) <= 12 and all(len(line) <= 80 for line in art)
    assert 1 <= len(EXT["thinking"]["frames"]) <= 64
    assert 40 <= EXT["thinking"]["intervalMs"] <= 1000
    assert 1 <= len(EXT["splash"]) <= 200 and all(len(s) <= 80 for s in EXT["splash"])
    assert all(len(q) <= 80 for q in EXT["thinking"]["quips"])
    assert all(len(v) <= 40 for v in EXT["toolLabels"].values())


def test_layouts_pair_with_herdr_themes():
    for name, look in [("lead", "graphite"), ("swarm", "ink"), ("review", "paper"), ("zen", "moss")]:
        lay = json.loads((REPO / "herdr-app" / "layouts" / f"mux-{name}.json").read_text(encoding="utf-8"))
        assert lay["theme"] == look and PAL["looks"][look]["herdr"] == look

        def depth(o):
            return 1 + max((depth(v) for v in (o.values() if isinstance(o, dict) else o)), default=0) \
                if isinstance(o, (dict, list)) else 0
        assert depth({"layout": lay}) <= 16, name  # layout.set limit
