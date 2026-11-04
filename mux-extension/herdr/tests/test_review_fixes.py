"""Regression tests for the demo-review findings: token never in labels, tail flush race, footer flags."""
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import herdr_live as hl  # noqa: E402

INPUT_BOX = ("\u256d" + "\u2500" * 20 + "\u256e\n\u2502 \u203a  steer the agent while it works \u2502\n\u2570" + "\u2500" * 20 + "\u256f")


def footer(core, tail=""):
    return f"  {core} \u00b7 \u2501\u2501 0/1000k (0%) \u00b7 claude-opus-5-5 \u00b7 \u25d0 high{tail}"


# --- 1. the control token is never a label -------------------------------------------------
def test_token_is_not_a_label():
    lv = hl.Live()
    lv.s["port"] = "4242"
    assert "token" not in lv.s
    assert "mux.token" not in lv.labels()  # (mux.tokens is the context token count)
    assert "mux.port" in lv.diff()


def test_control_file_is_written_and_removed():
    with tempfile.TemporaryDirectory() as d:
        path = hl.write_control_file(d, "t2q", 4242, "s3cret")
        data = json.load(open(path, encoding="utf-8"))
        assert data["port"] == 4242 and data["token"] == "s3cret" and data["pid"] == os.getpid()
        assert os.path.basename(path) == "t2q.json"
        assert not [n for n in os.listdir(d) if n.endswith(".tmp")]
        hl.remove_control_file(path)
        assert not os.path.exists(path)
        hl.remove_control_file(path)  # twice is fine


# --- 2. Tails.flush never loses an update made while it writes ------------------------------
def test_end_during_flush_is_not_lost():
    with tempfile.TemporaryDirectory() as d:
        t = hl.Tails(d, every=0)
        t.start("dd1", "WebAgent", "task")
        real_replace = os.replace
        fired = []

        def replace_then_end(src, dst):
            real_replace(src, dst)
            if not fired:  # the event thread appends the final status mid-flush
                fired.append(1)
                t.end("dd1", "success")

        hl.os.replace = replace_then_end
        try:
            t.flush()
        finally:
            hl.os.replace = real_replace
        t.flush()
        assert "**success**" in open(os.path.join(d, "dd1.md"), encoding="utf-8").read()


def test_clear_during_flush_does_not_resurrect_files():
    with tempfile.TemporaryDirectory() as d:
        t = hl.Tails(d, every=0)
        t.start("dd1", "WebAgent", "task")
        t.start("dd2", "CodeAgent", "task")  # still to be written when the clear lands
        real_replace = os.replace
        cleared = []

        def replace_then_clear(src, dst):
            real_replace(src, dst)
            if not cleared:
                cleared.append(1)
                t.clear()

        hl.os.replace = replace_then_clear
        try:
            t.flush()
        finally:
            hl.os.replace = real_replace
        t.flush()
        assert not [n for n in os.listdir(d) if n.endswith(".md")]


def test_flush_is_safe_from_two_threads():
    with tempfile.TemporaryDirectory() as d:
        t = hl.Tails(d, every=0)
        for i in range(20):
            t.start(f"dd{i}", "A", "t")

        def spam():
            for i in range(200):
                t.add(f"dd{i % 20}", "x")
        th = threading.Thread(target=spam)
        th.start()
        for _ in range(50):
            t.flush()
        th.join()
        t.flush()
        for i in range(20):
            assert open(os.path.join(d, f"dd{i}.md"), encoding="utf-8").read() == t.buf[f"dd{i}"]


# --- 3. footer flags ------------------------------------------------------------------------
def test_footer_under_1k_tokens_is_read():
    f = hl.footer_flags("hello\n" + footer("plan \u00b7 psub") + "\n" + INPUT_BOX)
    assert f["plan"] is True and f["sub"] == "psub" and f["effort"] == "high"


def test_effort_read_with_chips_after_it():
    f = hl.footer_flags(footer("ultra", tail=" \u00b7 herdr 1 \u00b7 1 working \u00b7 5h 57% 7d 18%") + "\n" + INPUT_BOX)
    assert f["ultra"] is True and f["effort"] == "high"


def test_footer_lookalike_in_output_does_not_win():
    screen = "\n".join([
        footer("plan"),                              # the real footer...
        INPUT_BOX,                                   # ...right above the input box
        "agent output quoting: giga \u00b7 12k/200k (6%)",  # a look-alike printed later
    ])
    f = hl.footer_flags(screen)
    assert f["plan"] is True and f["giga"] is False


def test_no_footer_means_unknown_not_stale():
    lv = hl.Live()
    lv.update_flags({"plan": True, "ultra": False, "giga": False, "sub": "psub", "effort": "high"})
    lv.diff()
    lv.update_flags(hl.footer_flags("no footer on this screen"))
    d = lv.diff()
    assert d == {"mux.plan": "", "mux.ultra": "", "mux.giga": "", "mux.sub": "", "mux.effort": ""}


def test_real_footer_capture():
    real = ("  plan \u00b7 psub \u00b7 \u25cf 26:18 \u00b7 39m \u00b7 \u2501\u2501 225.8k/1000k (23%) \u00b7 218.8k cached"
            " \u00b7 calls 84 \u00b7 claude-opus-5-5 \u00b7 \u25d0 high \u00b7 \u21e7\u21b9 \u00b7 herdr 1 \u00b7 1 working \u00b7 5h 57% 7d 18%"
            "        \u2502 side panel sub \u00b7 giga 9k/9k (1%)")
    f = hl.footer_flags(real + "\n" + INPUT_BOX)
    assert f == {"plan": True, "ultra": False, "giga": False, "sub": "psub", "effort": "high"}
