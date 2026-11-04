"""The follow pane follows every way an agent touches a file (bug report 11-04)."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import herdr_live as hl  # noqa: E402


def call(live, tool, args):
    live.on_event({"event": "tool_call", "tool": tool, "args": json.dumps(args)})


def result(live):
    live.on_event({"event": "tool_result", "summary": "ok"})


def test_filesystem_read_is_followed():
    lv = hl.Live()
    call(lv, "Filesystem_read_text_file", {"path": "C:/r/notes.md"})
    assert lv.s["file"] == "C:/r/notes.md"


def test_same_file_edit_bumps_fileat():
    lv = hl.Live()
    call(lv, "Filesystem_write_file", {"path": "C:/r/a.md", "content": "x"})
    first = lv.s["fileat"]
    time.sleep(0.01)
    call(lv, "Filesystem_edit_file", {"path": "C:/r/a.md", "oldText": "x", "newText": "y"})
    assert lv.s["file"] == "C:/r/a.md" and lv.s["fileat"] != first  # the pane reloads on fileat


def test_repl_write_is_followed_after_it_runs():
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "viewer_follow_test.md")
        lv = hl.Live()
        call(lv, "repl_shell_exec", {"code": f'open(r"{target}", "w").write("hi")'})
        assert lv.s["file"] == ""  # not yet: the code has not run
        with open(target, "w") as f:
            f.write("hi")
        result(lv)
        assert os.path.normcase(lv.s["file"]) == os.path.normcase(os.path.normpath(target))


def test_second_repl_write_moves_the_pane():
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "one.md"), os.path.join(d, "two.md")
        lv = hl.Live()
        call(lv, "Filesystem_write_file", {"path": a})
        call(lv, "repl_shell_exec", {"code": f"open('{b}', 'w').write('x')"})
        open(b, "w").write("x")
        result(lv)
        assert os.path.normcase(lv.s["file"]) == os.path.normcase(os.path.normpath(b))


def test_repl_read_of_unchanged_file_does_not_move_the_pane():
    with tempfile.TemporaryDirectory() as d:
        old = os.path.join(d, "old.md")
        open(old, "w").write("x")
        os.utime(old, (time.time() - 60, time.time() - 60))
        lv = hl.Live()
        call(lv, "repl_shell_exec", {"code": f"print(open(r'{old}').read())"})
        result(lv)
        assert lv.s["file"] == ""


def test_shell_redirect_is_followed():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.log")
        lv = hl.Live()
        call(lv, "execute_command_async", {"command": f"echo hi > {out}"})
        open(out, "w").write("hi")
        result(lv)
        assert os.path.normcase(lv.s["file"]) == os.path.normcase(os.path.normpath(out))


def test_relative_path_resolves_against_session_cwd():
    with tempfile.TemporaryDirectory() as d:
        lv = hl.Live()
        lv.update_info({"cwd": d, "inSession": True, "context": {}})
        call(lv, "repl_shell_exec", {"code": "open('rel.txt', 'w').write('x')"})
        open(os.path.join(d, "rel.txt"), "w").write("x")
        result(lv)
        assert os.path.normcase(lv.s["file"]) == os.path.normcase(os.path.join(d, "rel.txt"))


def test_built_paths_are_not_guessed():
    assert hl.code_paths("repl_shell_exec", {"code": "p = os.path.join(base, name)\nopen(p, 'w')"}) == []
    assert hl.code_paths("Filesystem_write_file", {"code": "'a.md'"}) == []  # file tools use edited_path
