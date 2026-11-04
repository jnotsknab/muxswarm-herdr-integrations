"""Unit tests for herdr-app-bridge.decide (pure mapping). Run: python -m pytest tests -q"""
import base64
import importlib.util
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bridge", os.path.join(HERE, "..", "herdr-app-bridge.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

OSC = re.compile(r"\x1b\]7501;([^\x1b]*)\x1b\\")


def parse(out):
    """escape strings -> list of dicts for the 7501 reports (msg decoded)."""
    recs = []
    for s in out:
        for body in OSC.findall(s):
            d = dict(f.split("=", 1) for f in body.split(":"))
            if "msg" in d:
                d["msg"] = base64.b64decode(d["msg"]).decode()
            recs.append(d)
    return recs


def run(events, st=None):
    st = st or {}
    allout = []
    for i, ev in enumerate(events):
        ev.setdefault("timestamp", f"2026-11-04T01:00:{i:02d}.5+00:00")
        st, out = bridge.decide(st, ev)
        allout.extend(out)
    return st, allout


def test_session_start_sets_idle_title_and_lead():
    st, out = run([{"event": "session_start", "agent": "CodeAgent"}])
    assert st["lead"] == "CodeAgent"
    assert "\x1b]2;mux: CodeAgent\x07" in out
    assert parse(out) == [{"state": "idle", "app": "mux-swarm", "msg": "CodeAgent ready"}]


def test_turn_flow_working_then_done_with_summary():
    _, out = run([
        {"event": "session_start", "agent": "CodeAgent"},
        {"event": "user_input", "agent": "CodeAgent", "text": "hi"},
        {"event": "tool_call", "agent": "CodeAgent", "tool": "Shell_run"},
        {"event": "turn_end", "agent": "CodeAgent", "summary": "All tests\npass."},
    ])
    states = [(r["state"], r.get("msg")) for r in parse(out)]
    assert states == [("idle", "CodeAgent ready"), ("working", "thinking"),
                      ("working", "Shell_run"), ("done", "All tests pass.")]


def test_ask_user_blocks_and_answer_resumes():
    _, out = run([
        {"event": "session_start", "agent": "CodeAgent"},
        {"event": "user_input", "agent": "CodeAgent"},
        {"event": "tool_call", "agent": "CodeAgent", "tool": "ask_user"},
        {"event": "tool_call", "agent": "CodeAgent", "tool": "other"},  # stays blocked
        {"event": "tool_result", "agent": "CodeAgent", "summary": "yes"},
    ])
    recs = parse(out)
    assert recs[2] == {"state": "blocked", "kind": "question", "app": "mux-swarm",
                       "msg": "asking you a question"}
    assert [r["state"] for r in recs] == ["idle", "working", "blocked", "working"]


def test_sub_agent_turn_end_does_not_mark_done():
    st, out = run([
        {"event": "session_start", "agent": "Orchestrator"},
        {"event": "user_input", "agent": "Orchestrator"},
        {"event": "turn_end", "agent": "WebAgent", "summary": "sub result"},
    ])
    assert [r["state"] for r in parse(out)] == ["idle", "working"]
    assert st["state"] == "working"


def test_sub_agent_tool_call_is_labelled():
    _, out = run([
        {"event": "session_start", "agent": "Orchestrator"},
        {"event": "tool_call", "agent": "WebAgent", "tool": "fetch"},
    ])
    assert parse(out)[-1]["msg"] == "WebAgent: fetch"


def test_late_older_event_is_ignored():
    st, _ = run([{"event": "session_start", "agent": "A", "timestamp": "2026-11-04T01:00:05.1+00:00"}])
    st2, out = bridge.decide(st, {"event": "user_input", "agent": "A",
                                  "timestamp": "2026-11-04T01:00:04.9+00:00"})
    assert out == [] and st2 == st


def test_timestamps_with_trimmed_fractions_compare_numerically():
    assert bridge.ticks("2026-11-04T01:00:00.12+00:00") > bridge.ticks("2026-11-04T01:00:00.1199999+00:00")
    assert bridge.ticks("2026-11-04T01:00:01+00:00") > bridge.ticks("2026-11-04T01:00:00.9999999+00:00")


def test_duplicate_reports_are_suppressed():
    _, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "tool_call", "agent": "A", "tool": "x"},
        {"event": "tool_call", "agent": "A", "tool": "x"},
    ])
    assert len(parse(out)) == 2


def test_session_end_clears():
    st, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "session_end", "agent": "A"},
    ])
    assert "\x1b]7501;state=clear\x1b\\" in out and "\x1b]2;\x07" in out
    assert "lead" not in st


def test_no_session_start_treats_every_agent_as_lead():
    _, out = run([{"event": "turn_end", "agent": "X", "summary": "ok"}])
    assert parse(out) == [{"state": "done", "app": "mux-swarm", "msg": "ok"}]


def test_title_strips_control_chars():
    assert bridge.osc_title("a\x07b\x1bc\u00e9") == "\x1b]2;abc\x07"
