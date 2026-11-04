"""Tests for herdr_live: control map, edited paths, footer flags, labels, tails."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import herdr_live as hl  # noqa: E402

FOOTER = ("  plan \u00b7 psub \u00b7 \u25cf 26:18 \u00b7 39m \u00b7 \u2501\u2501\u2501 225.8k/1000k (23%) \u00b7 218.8k cached"
          " \u00b7 calls 84 \u00b7 claude-opus-5-5 \u00b7 \u25d0 high        \u2502 side panel text sub \u00b7 giga")


@pytest.mark.parametrize("action,arg,line", [
    ("compact", None, "/compact"),
    ("compact", "keep the plan", "/compact keep the plan"),
    ("prune", "", "/prune"),
    ("prune", "all", "/prune"),
    ("prune", "Tools", "/prune tools"),
    ("effort", "medium", "/effort med"),
    ("effort", "xhigh", "/effort xhigh"),
    ("context", "200k", "/context 200k"),
    ("context", "max", "/context max"),
    ("context", "120000", "/context 120000"),
    ("plan", None, "/plan"),
    ("costall", None, "/cost all"),
    ("tag", "herdr work", "/tag herdr work"),
    ("theme", "ember", "/theme ember"),
])
def test_control_line(action, arg, line):
    assert hl.control_line(action, arg) == line


@pytest.mark.parametrize("action,arg", [
    ("prune", "everything"), ("effort", "ludicrous"), ("context", "5k"), ("context", "lots"),
    ("tag", ""), ("tag", "a\nb"), ("theme", "../x"), ("set", "x"), ("exit", None), ("compact", "x\ry"),
])
def test_control_line_refuses(action, arg):
    with pytest.raises(ValueError):
        hl.control_line(action, arg)


def test_every_simple_command_is_on_the_mux_allowlist():
    allowed = {"/compact", "/prune", "/handoff", "/tokens", "/context", "/cost", "/diff", "/status", "/help",
               "/retry", "/undo", "/redo", "/effort", "/max", "/tag", "/theme", "/verbose", "/subagentview",
               "/daemonview", "/plan", "/ultra", "/giga", "/tools", "/skills", "/sessions", "/model", "/limits",
               "/doctor", "/review", "/clear", "/shortcuts"}
    for line in hl.SIMPLE.values():
        assert line.split(" ")[0] in allowed, line


def test_edited_path():
    assert hl.edited_path("Filesystem_edit_file", {"path": "C:/a/b.py"}) == "C:/a/b.py"
    assert hl.edited_path("write_file", '{"file_path": "/x/y.md"}') == "/x/y.md"
    assert hl.edited_path("Filesystem_read_text_file", {"path": "C:/a"}) == "C:/a"  # reads are followed too
    assert hl.edited_path("Filesystem_list_directory", {"path": "C:/a"}) is None
    assert hl.edited_path("repl_shell_exec", {"code": "open('x','w')"}) is None
    assert hl.edited_path("edit_file", "not json") is None


def test_footer_flags_reads_mode_and_effort_and_ignores_side_panel():
    f = hl.footer_flags("transcript line\n" + FOOTER + "\n\u256d\u2500\u2500\u256e")
    assert f == {"plan": True, "ultra": False, "giga": False, "sub": "psub", "effort": "high"}
    assert hl.footer_flags("no footer here") == {k: "" for k in hl.FLAG_KEYS}  # unknown, never stale


def test_live_labels_and_diff():
    lv = hl.Live()
    lv.update_info({"agent": "CodeAgent", "model": "opus", "inSession": True, "sessionId": "s1",
                    "context": {"tokens": 225800, "window": 1000000, "percent": 22.6}})
    first = lv.diff()
    assert first["mux.agent"] == "CodeAgent" and first["mux.pct"] == "22.6" and first["mux.window"] == "1000k"
    assert lv.diff() == {}
    lv.on_event({"event": "effort_changed", "data": {"from": "high", "to": "max"}})
    lv.on_event({"event": "compaction", "data": {"phase": "start"}})
    assert lv.diff() == {"mux.effort": "max", "mux.compacting": "1"}
    lv.on_event({"event": "tool_call", "tool": "Filesystem_edit_file", "args": '{"path": "C:/r/main.py"}'})
    d = lv.diff()
    assert d["mux.file"] == "C:/r/main.py" and d["mux.fileat"]
    assert lv.on_event({"event": "command_executed", "data": {"command": "/plan"}}) is True
    assert lv.on_event({"event": "command_executed", "data": {"command": "/cost"}}) is False
    lv.update_flags({"plan": False, "ultra": True, "sub": "", "effort": "low"})
    assert lv.diff() == {"mux.plan": "0", "mux.ultra": "1", "mux.effort": "low"}
    lv.on_event({"event": "session_end"})
    assert lv.diff()["mux.pct"] == ""


def test_tails_roll_and_flush():
    with tempfile.TemporaryDirectory() as d:
        t = hl.Tails(d, max_chars=200, every=0)
        t.start("dd1", "WebAgent", "find docs")
        t.on_event({"event": "text_chunk", "text": "hello "}, "dd1")
        t.on_event({"event": "tool_call", "tool": "fetch"}, "dd1")
        t.end("dd1", "success")
        [path] = t.flush()
        body = open(path, encoding="utf-8").read()
        assert body.startswith("# WebAgent") and "`> fetch`" in body and "**success**" in body
        for _ in range(50):
            t.add("dd1", "0123456789\n")
        t.flush()
        assert len(open(path, encoding="utf-8").read()) <= 200
        t.clear()
        assert not os.listdir(d)


def test_tail_rid():
    assert hl.tail_rid({"flowId": "d7"}, {"d7": "dd7"}) == "dd7"
    assert hl.tail_rid({}, {"d7": "dd7"}) is None
