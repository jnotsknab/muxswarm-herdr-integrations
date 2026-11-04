"""extension.json must pass Mux's own manifest rules, or Mux silently drops the offending tool."""
import json
import pathlib
import re

MANIFEST = json.loads((pathlib.Path(__file__).resolve().parents[1] / "extension.json").read_text(encoding="utf-8"))
MAX_TOOL_TIMEOUT, MAX_COMMAND_TIMEOUT = 600, 3600  # Mux ExtensionRegistry limits


def test_tool_timeouts_within_mux_limit():
    for t in MANIFEST["tools"]:
        assert 1 <= t.get("timeoutSeconds", 60) <= MAX_TOOL_TIMEOUT, t["name"]


def test_command_timeouts_within_mux_limit():
    for c in MANIFEST["commands"]:
        assert 1 <= c.get("timeoutSeconds", 60) <= MAX_COMMAND_TIMEOUT, c["name"]


def test_tool_names_valid():
    for t in MANIFEST["tools"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]{0,47}", t["name"]), t["name"]


def test_ask_waits_less_than_its_tool_timeout():
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    ask_max = int(re.search(r"^ASK_MAX_SECONDS = (\d+)", src, re.M).group(1))
    ask = next(t for t in MANIFEST["tools"] if t["name"] == "ask")
    assert ask_max + 30 < ask["timeoutSeconds"]
