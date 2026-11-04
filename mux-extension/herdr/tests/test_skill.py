"""skills/herdr/SKILL.md stays loadable by Mux and in step with the extension's tools."""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = (REPO / "skills" / "herdr" / "SKILL.md").read_text(encoding="utf-8")
EXT = json.loads((REPO / "mux-extension" / "herdr" / "extension.json").read_text(encoding="utf-8"))


def frontmatter():
    lines = SKILL.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    out = {}
    for line in lines[1:end]:
        k, _, v = line.partition(":")
        out[k.strip().lower()] = v.strip()
    return out


def test_frontmatter_is_what_mux_parses():
    fm = frontmatter()
    assert fm["name"] == "herdr"
    assert 40 < len(fm["description"]) < 1024 and "\n" not in fm["description"]
    # Mux lists the skill only when this env var is set, i.e. only inside a Herdr terminal.
    assert fm["requires_env"] == "HC_TERMINAL_ID"


def test_every_tool_is_documented():
    for tool in EXT["tools"]:
        assert f"herdr_{tool['name']}" in SKILL, tool["name"]


def test_safety_rules_present():
    for phrase in ["HC_TERMINAL_ID", "Never close a pane", "--no-parent", "`done`", "control token"]:
        assert phrase in SKILL, phrase


def test_no_machine_specific_paths():
    for bad in ["C:\\Users", "/home/", "/Users/"]:
        assert bad not in SKILL
