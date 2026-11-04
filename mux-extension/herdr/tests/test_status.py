"""Unit tests for herdr_status.decide. Run: python -m pytest tests -q"""
import base64
import importlib.util
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("hs", os.path.join(HERE, "..", "herdr_status.py"))
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)

OSC = re.compile(r"\x1b\]7501;([^\x1b]*)\x1b\\")


def parse(out):
    recs = []
    for s in out:
        for body in OSC.findall(s):
            d = dict(f.split("=", 1) for f in body.split(":"))
            for k in ("msg", "title"):
                if k in d:
                    d[k] = base64.b64decode(d[k]).decode()
            recs.append(d)
    return recs


def run(events, st=None, new_mux=True):
    st = st or {}
    allout = []
    for i, ev in enumerate(events):
        ev.setdefault("timestamp", f"2026-11-04T01:00:{i:02d}.5+00:00")
        if ev["event"] == "session_start" and new_mux:
            ev.setdefault("data", {"model": "m", "resumed": False})
        st, out = hs.decide(st, ev)
        allout.extend(out)
    return st, allout


def roots(out):
    return [(r["state"], r.get("msg")) for r in parse(out) if "id" not in r]


def test_new_mux_done_on_turn_complete_not_turn_end():
    _, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "user_input", "agent": "A"},
        {"event": "turn_end", "agent": "A", "summary": "partial answer"},
        {"event": "tool_call", "agent": "A", "tool": "x"},
        {"event": "turn_end", "agent": "A", "summary": "Final answer"},
        {"event": "turn_complete", "agent": "A", "summary": "ok", "data": {"outcome": "ok"}},
    ])
    assert roots(out) == [("idle", "A ready"), ("working", "thinking"), ("working", "x"), ("done", "Final answer")]


def test_old_mux_done_on_turn_end():
    _, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "user_input", "agent": "A"},
        {"event": "turn_end", "agent": "A", "summary": "ok"},
    ], new_mux=False)
    assert roots(out)[-1] == ("done", "ok")


def test_interrupted_and_failed_turns():
    _, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "user_input", "agent": "A"},
        {"event": "turn_complete", "agent": "A", "data": {"outcome": "interrupted"}},
        {"event": "user_input", "agent": "A"},
        {"event": "turn_complete", "agent": "A", "data": {"outcome": "failed", "error": "HTTP 503"}},
    ])
    assert roots(out)[-3:] == [("idle", "interrupted"), ("working", "thinking"), ("error", "HTTP 503")]


def test_delegation_creates_and_clears_child_record():
    st, out = run([
        {"event": "session_start", "agent": "Orchestrator"},
        {"event": "delegation", "agent": "Orchestrator", "summary": "research X", "flowId": "f1", "data": {"to": "WebAgent"}},
        {"event": "tool_call", "agent": "WebAgent", "tool": "fetch", "flowId": "f1"},
        {"event": "delegation_end", "agent": "Orchestrator", "flowId": "f1", "data": {"status": "success"}},
    ])
    kids = [r for r in parse(out) if "id" in r]
    assert kids[0] == {"state": "working", "id": "df1", "app": "mux-swarm", "title": "WebAgent", "msg": "research X"}
    assert kids[1]["msg"] == "WebAgent: fetch" and kids[1]["title"] == "WebAgent"
    assert kids[2] == {"state": "clear", "id": "df1"}
    assert st["subs"] == {}
    assert roots(out)[-1] == ("working", "delegating to WebAgent")


def test_background_job_record():
    st, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "job_start", "agent": "A", "summary": "bg1", "data": {"id": "bg1", "agent": "CodeAgent"}},
        {"event": "job_end", "agent": "A", "data": {"id": "bg1", "status": "done"}},
    ])
    kids = [r for r in parse(out) if "id" in r]
    assert [k["state"] for k in kids] == ["working", "clear"] and kids[0]["id"] == "jbg1"


def test_session_start_and_end_clear_children():
    st, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "delegation", "agent": "A", "flowId": "f9", "data": {"to": "B"}},
        {"event": "session_end", "agent": "A"},
    ])
    assert "\x1b]7501;state=clear\x1b\\" in out


def test_ask_user_blocks_until_answer():
    _, out = run([
        {"event": "session_start", "agent": "A"},
        {"event": "user_input", "agent": "A"},
        {"event": "tool_call", "agent": "A", "tool": "ask_user"},
        {"event": "tool_call", "agent": "A", "tool": "other"},
        {"event": "tool_result", "agent": "A"},
    ])
    assert [s for s, _ in roots(out)] == ["idle", "working", "blocked", "working"]


def test_late_event_ignored_and_compaction():
    st, _ = run([{"event": "session_start", "agent": "A", "timestamp": "2026-11-04T01:00:05.1+00:00"}])
    st2, out = hs.decide(st, {"event": "user_input", "agent": "A", "timestamp": "2026-11-04T01:00:04.9+00:00"})
    assert out == []
    _, out = hs.decide(st, {"event": "compaction", "agent": "A", "summary": "start", "data": {"phase": "start"},
                            "timestamp": "2026-11-04T01:00:06+00:00"})
    assert roots(out) == [("working", "compacting context")]


def test_title_and_rid_sanitized():
    assert hs.osc_title("a\x07b\x1bc\u00e9") == "\x1b]2;abc\x07"
    assert hs.rid_for("d", "a:b/c d") == "dabcd"


# --- clean_screen -----------------------------------------------------------------------------
FIX = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


BOXY = "\u2500\u2501\u2502\u2503\u2551\u2588\u256d\u256e\u2570\u256f\u2554\u2557\u255a\u255d"


def test_clean_mux_transcript_has_no_frame_glyphs_or_chrome():
    out = hs.clean_screen(fixture("mux_history.txt"))
    assert not any(ch in out for ch in BOXY)
    assert "type a message" not in out and "[hc] incomplete" not in out and "k/1000k" not in out
    assert "> download and open the example app" in out
    assert "## ExampleAgent" in out
    assert "* ask_user" in out and "  -> User confirmed: yes" in out


def test_clean_drops_splash_art_keeps_text():
    out = hs.clean_screen(fixture("mux_screen.txt"))
    assert "\u2588" not in out and "\u255a" not in out
    assert "/help" in out


def test_clean_keeps_plain_shell_output():
    raw = fixture("shell_screen.txt")
    out = hs.clean_screen(raw)
    assert "poll" in out and "HTTP/1.1 200 OK" in out and "[hc]" not in out
    assert len([l for l in out.splitlines() if l.strip()]) == len([l for l in raw.splitlines() if l.strip() and "[hc]" not in l])


def test_clean_strips_escapes_controls_and_collapses_blanks():
    raw = "\x1b[1;31mred\x1b[0m text\x07\n\n\n\n\x1b]0;title\x07next   wide    gap\n\u2502 inner \u2502 cols \u2502\u2588"
    assert hs.clean_screen(raw) == "red text\n\nnext  wide  gap\ninner  cols"


def test_clean_max_lines_keeps_tail_without_leading_blank():
    raw = "a\n\nb\n\nc\nd"
    assert hs.clean_screen(raw, max_lines=3) == "c\nd"
