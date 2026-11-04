"""herdr: a Mux-Swarm extension for the Herdr app (herdr-core `hc`).

- Status: reports this Mux session to Herdr (OSC 7501), with a child record per running
  delegation or background job, so Herdr's sidebar, tabs, Graph and Board show them under the lead.
  Replaces the herdr-app-bridge hook (remove the hook entries if you install this).
- Footer chip `herdr.agents`: agents on this machine and how many need you.
- /herdr command: ls, panel, peek, send, spawn, layout, help.
- Docked panel: every Herdr agent with status; select one to peek, Send/Spawn from the input.
- Agent tools: herdr_list, herdr_spawn, herdr_read, herdr_send, herdr_wait, herdr_stop.

JSON-RPC 2.0 over stdin/stdout (see Mux DOCS.md "Extensions"). Stdlib only.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import herdr_status as hs  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ME = os.environ.get("HC_TERMINAL_ID")  # this Mux's terminal, when it runs inside Herdr
HC = shutil.which("hc")
HERDR_APP = shutil.which("herdr-app")
_out_lock = threading.Lock()
_next_id = [1000]
_pending = {}


# --- JSON-RPC plumbing -----------------------------------------------------------------------
def send(msg):
    line = json.dumps(msg)
    with _out_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def notify(method, params):
    send({"jsonrpc": "2.0", "method": method, "params": params})


def request(method, params, timeout=5.0):
    """Request to the Mux host; returns result or None. Safe from any thread except the reader."""
    _next_id[0] += 1
    rid = _next_id[0]
    ev = threading.Event()
    _pending[rid] = [ev, None]
    send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    ev.wait(timeout)
    return _pending.pop(rid, [None, None])[1]


def reply(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error:
        msg["error"] = {"code": 1, "message": error}
    else:
        msg["result"] = result if result is not None else {}
    send(msg)


# --- hc ----------------------------------------------------------------------------------------
def hc(*args, timeout=30, stdin=None):
    if not HC:
        raise RuntimeError("hc (herdr-core) is not on PATH")
    r = subprocess.run([HC, *args], input=stdin, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace",
                       stdin=None if stdin is not None else subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip()
        try:
            msg = json.loads(msg)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError(msg or f"hc exited {r.returncode}")
    return r.stdout


def hc_json(*args, timeout=30):
    return json.loads(hc(*args, "--json", timeout=timeout) or "null")


def agents():
    """Live terminals that report a status, plus their records."""
    rows = []
    data = hc_json("ls")
    for t in data.get("terminals", []):
        if t.get("state") != "live":
            continue
        rows.append(t)
    return rows, data.get("machines", [])


def status_word(t):
    s = t.get("status")
    return s.get("state") if isinstance(s, dict) else (s or "")


# --- status reporting (in-process, state in memory) --------------------------------------------
class Status:
    def __init__(self):
        self.st = {}
        self.term = hs.Terminal() if ME else None
        self.lock = threading.Lock()

    def on_event(self, ev):
        if not self.term:
            return
        with self.lock:
            self.st, out = hs.decide(self.st, ev)
            if out:
                self.term.write("".join(out))


STATUS = Status()


# --- footer chip + panel refresh loop -----------------------------------------------------------
class Live:
    def __init__(self):
        self.panel_open = False
        self.selected = None
        self.last_chip = None
        self.wake = threading.Event()

    def loop(self):
        while True:
            try:
                self.tick()
            except Exception as e:  # hc missing / core restarting: show it, keep going
                self.chip(f"herdr ? ({str(e)[:24]})")
            self.wake.wait(5 if self.panel_open else 15)
            self.wake.clear()

    def chip(self, text):
        if text != self.last_chip:
            self.last_chip = text
            notify("footer/set", {"id": "agents", "text": text})

    def tick(self):
        rows, machines = agents()
        reporting = [t for t in rows if t.get("status")]
        needs = sum(1 for t in reporting if status_word(t) in ("blocked", "error"))
        working = sum(1 for t in reporting if status_word(t) == "working")
        parts = [f"herdr {len(reporting)}"]
        if working:
            parts.append(f"{working} working")
        if needs:
            parts.append(f"{needs} need you")
        self.chip(" \u00b7 ".join(parts))
        if self.panel_open:
            request("ui/update", {"id": "herdr", "view": self.view(rows, machines)}, timeout=3)

    def view(self, rows=None, machines=None):
        if rows is None:
            rows, machines = agents()
        mark = {"working": "\u25cf", "blocked": "\u25b2", "error": "\u2716", "done": "\u2713", "idle": "\u00b7"}
        items = []
        for t in sorted(rows, key=lambda t: ({"blocked": 0, "error": 0, "working": 1, "done": 2}.get(status_word(t), 3), t["address"])):
            w = status_word(t) or "-"
            label = f"{mark.get(w, ' ')} {t.get('name') or t.get('agent') or t['address']}"
            if t["address"] == ME:
                label += " (this)"
            items.append({"value": t["address"], "label": label[:60],
                          "detail": f"{t['address']} \u00b7 {w} \u00b7 {t.get('where') or ''}"[:80]})
        sel = self.selected if any(i["value"] == self.selected for i in items) else None
        kids = [{"type": "text", "text": "Herdr agents", "bold": True},
                {"type": "list", "key": "agents", "items": items or [{"value": "-", "label": "(no terminals)"}],
                 **({"selected": sel} if sel else {})}]
        if sel:
            try:
                screen = hc("read", sel, "--lines", "60", timeout=10)
            except Exception as e:
                screen = f"(could not read: {e})"
            tail = hs.clean_screen(screen, max_lines=14)
            kids += [{"type": "text", "text": f"{sel} screen", "color": "muted"},
                     {"type": "code", "text": tail[-4000:] or "(empty)"}]
        kids += [{"type": "input", "key": "line", "placeholder": "send to selected  |  spawn <template|cmd> <task>"},
                 {"type": "box", "dir": "row", "gap": 2, "children": [
                     {"type": "button", "key": "send", "label": "Send", "hotkey": "s"},
                     {"type": "button", "key": "peek", "label": "Peek", "hotkey": "p"},
                     {"type": "button", "key": "refresh", "label": "Refresh", "hotkey": "r"}]},
                 {"type": "text", "text": f"{len([m for m in (machines or []) if m.get('state') == 'connected'])} remote machine(s) connected",
                  "color": "muted"}]
        return {"type": "box", "gap": 1, "children": kids}

    def open(self):
        self.panel_open = True
        r = request("ui/open", {"id": "herdr", "title": "Herdr", "view": self.view(), "placement": "auto", "columns": 56})
        self.wake.set()
        return r

    def close(self):
        self.panel_open = False
        r = request("ui/close", {"id": "herdr"})
        return bool((r or {}).get("closed"))


LIVE = Live()


# --- actions shared by commands, panel and tools ------------------------------------------------
def do_spawn(spec, task, name=None, cwd=None):
    """spec: an hc template name, or a command line. The helper reports back into this Mux."""
    templates = {t["name"] for t in (hc_json("templates").get("templates") or [])}
    args = ["run", "--bg", "--json"]
    if name:
        args += ["--name", name]
    if cwd:
        args += ["--cwd", cwd]
    if spec in templates:
        report = f" When done, report back with: hc send {ME} \"<result>\"" if ME else ""
        args += [spec, (task or "").strip() + report]
    else:
        args += ["--"] + spec.split() + ([task] if task else [])
    return json.loads(hc(*args, timeout=90))


def do_read(term, lines=0):
    return hc("read", term, "--lines", str(lines), timeout=15)


def do_send(term, text, force=False):
    args = ["send", term, text, "--json"] + (["--force"] if force else [])
    return json.loads(hc(*args, timeout=60) or "{}")


HELP = """/herdr                 agents in Herdr (this machine + remotes)
/herdr panel           docked live panel (select an agent to peek; send/spawn from its input)
/herdr panel close     close the panel
/herdr peek <t>        last screen of a terminal
/herdr send <t> <text> type text into a terminal and press Enter
/herdr spawn <template|command> [task]   start a helper in Herdr (templates report back here)
/herdr layout [name]   switch the Herdr app layout (no name: list them)"""


def cmd_ls():
    rows, machines = agents()
    if not rows:
        return "No Herdr terminals."
    out = []
    for t in rows:
        w = status_word(t) or "-"
        me = "  <- this Mux" if t["address"] == ME else ""
        out.append(f"{t['address']:<16} {w:<8} {(t.get('name') or t.get('agent') or '')[:28]:<28} {t.get('where') or ''}{me}")
    conn = [m["name"] for m in machines if m.get("state") == "connected"]
    if conn:
        out.append(f"machines: {', '.join(conn)}")
    return "\n".join(out)


def cmd_layout(name):
    if not HERDR_APP:
        return "herdr-app is not on PATH."
    if not name:
        home = os.environ.get("HERDR_APP_HOME") or os.path.join(os.path.expanduser("~"), ".config", "herdr-app")
        names = sorted(f[:-5] for f in os.listdir(os.path.join(home, "layouts")) if f.endswith(".json"))
        return "Layouts: " + ", ".join(names)
    r = subprocess.run([HERDR_APP, "do", "layout.switch", "--name", name], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return f"Herdr layout: {name}" if r.returncode == 0 else (r.stdout + r.stderr).strip()


def on_command(params):
    args = (params.get("args") or "").strip()
    sub, _, rest = args.partition(" ")
    rest = rest.strip()
    if sub in ("", "ls", "list"):
        return {"output": cmd_ls()}
    if sub == "panel":
        if rest in ("close", "off", "hide"):
            return {"output": "herdr panel closed" if LIVE.close() else "herdr panel is not open"}
        LIVE.open()
        return {}
    if sub == "peek":
        if not rest:
            return {"output": "usage: /herdr peek <terminal>"}
        return {"output": hs.clean_screen(do_read(rest, 120), max_lines=40) or "(empty screen)"}
    if sub == "send":
        term, _, text = rest.partition(" ")
        if not term or not text:
            return {"output": "usage: /herdr send <terminal> <text>"}
        if term == ME:
            return {"output": "That is this Mux; type it here instead."}
        r = do_send(term, text)
        return {"output": f"sent to {term} ({r.get('status', 'ok')})"}
    if sub == "spawn":
        spec, _, task = rest.partition(" ")
        if not spec:
            return {"output": "usage: /herdr spawn <template|command> [task]"}
        r = do_spawn(spec, task.strip())
        return {"output": f"started {r.get('address')} ({r.get('name') or spec}); it shows in Herdr"
                          + (" and reports back here" if ME else "")}
    if sub == "layout":
        return {"output": cmd_layout(rest)}
    return {"output": HELP}


def on_panel_event(p):
    key, typ, val = p.get("key"), p.get("type"), p.get("value")
    if typ == "close":
        LIVE.panel_open = False
        return
    if key == "agents" and typ == "select":
        LIVE.selected = val if val != "-" else None
    elif key == "line" and typ == "submit":
        line = (val or "").strip()
        try:
            if line.startswith("spawn "):
                spec, _, task = line[6:].strip().partition(" ")
                r = do_spawn(spec, task.strip())
                request("ui/toast", {"text": f"herdr: started {r.get('address')}"})
            elif LIVE.selected and LIVE.selected != ME and line:
                do_send(LIVE.selected, line)
                request("ui/toast", {"text": f"herdr: sent to {LIVE.selected}"})
            elif line:
                request("ui/toast", {"text": "herdr: select an agent first (not this Mux)"})
        except Exception as e:
            request("ui/toast", {"text": f"herdr: {str(e)[:120]}"})
    elif key == "peek" and LIVE.selected:
        pass  # the next refresh redraws the screen
    LIVE.wake.set()


def on_tool(p):
    name = p.get("name") or ""
    a = p.get("arguments") or {}
    if isinstance(a, str):
        a = json.loads(a or "{}")
    if name == "list":
        return cmd_ls()
    if name == "spawn":
        r = do_spawn(a["agent"], a.get("task", ""), a.get("name"), a.get("cwd"))
        return json.dumps({"address": r.get("address"), "name": r.get("name"),
                           "note": "Runs in its own Herdr pane. Use herdr_wait then herdr_read; templates also report back with hc send."})
    if name == "read":
        text = do_read(a["terminal"], int(a.get("lines", 60)))
        return (hs.clean_screen(text) if a.get("clean") else text)[-12000:]
    if name == "send":
        if a["terminal"] == ME:
            raise RuntimeError("that terminal is this Mux session")
        return json.dumps(do_send(a["terminal"], a["text"], bool(a.get("force"))))
    if name == "wait":
        secs = max(5, min(int(a.get("timeoutSeconds", 300)), 1800))
        return hc("wait", a["terminal"], "--json", "--timeout", str(secs), timeout=secs + 30)
    if name == "stop":
        return hc("kill", a["terminal"], "--json", timeout=30)
    raise RuntimeError(f"unknown tool {name}")


# --- main loop -----------------------------------------------------------------------------------
def handle(msg):
    rid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method is None and rid in _pending:  # a reply to our request
        _pending[rid][1] = msg.get("result")
        _pending[rid][0].set()
        return
    if method == "event":
        STATUS.on_event(params)
        if params.get("event") in ("turn_complete", "session_start", "session_end", "delegation", "delegation_end"):
            LIVE.wake.set()
        return
    if method == "ui/event":
        threading.Thread(target=on_panel_event, args=(params,), daemon=True).start()
        return
    if method == "command/run":
        def run_cmd():
            try:
                reply(rid, on_command(params))
            except Exception as e:
                reply(rid, error=str(e)[:500])
        threading.Thread(target=run_cmd, daemon=True).start()
        return
    if method == "tool/call":
        def run_tool():
            try:
                reply(rid, {"content": on_tool(params)})
            except Exception as e:
                reply(rid, error=str(e)[:500])
        threading.Thread(target=run_tool, daemon=True).start()
        return
    if rid is not None:
        reply(rid, {})


def main():
    threading.Thread(target=LIVE.loop, daemon=True).start()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            handle(msg)
        except Exception as e:
            hs.log(f"handle failed: {e!r}", always=True)


if __name__ == "__main__":
    main()
