"""herdr_live.py - live Mux state for Herdr layouts, and the control map the muxbar mod uses.

Pure logic (no I/O except Tails.flush), so it is unit-tested without Mux or Herdr:
  * Live: folds Mux events + session/info into `mux.*` hc labels on this Mux's terminal,
    which every Herdr mod sees through terminals()[i].labels.
  * control_line: one muxbar action -> one Mux slash command (only commands Mux lets an
    extension run with command/run).
  * edited_path: the file an edit/write tool call touched (for the follow pane).
  * Tails: a rolling markdown tail per sub-agent record, written for the tail overlay.
  * footer_flags: plan/ultra/giga/sub mode and effort read from Mux's TUI footer, because
    session/info does not report them.
Stdlib only.
"""
import json
import os
import re
import time

EFFORTS = ["low", "med", "high", "xhigh", "max"]
PRUNE_KINDS = {"", "all", "dupes", "tools", "stale"}

# muxbar action -> slash command. None = takes no argument. All are on Mux's command/run allowlist.
SIMPLE = {
    "compact": "/compact", "plan": "/plan", "ultra": "/ultra", "giga": "/giga",
    "retry": "/retry", "undo": "/undo", "redo": "/redo", "handoff": "/handoff",
    "review": "/review", "diff": "/diff", "cost": "/cost", "costall": "/cost all",
    "tokens": "/tokens", "status": "/status", "doctor": "/doctor", "limits": "/limits",
    "model": "/model", "tools": "/tools", "skills": "/skills", "sessions": "/sessions",
    "verbose": "/verbose", "subagentview": "/subagentview", "daemonview": "/daemonview",
    "clear": "/clear", "help": "/help", "shortcuts": "/shortcuts", "max": "/max",
}
ARG_RE = re.compile(r"^[\w .,:;!?'\"()\[\]@#%+=/\\-]{1,300}$")
EDIT_VERBS = ("edit_file", "apply_patch", "str_replace", "write_file", "create_file", "apply_diff")
PATH_KEYS = ("path", "file_path", "filePath", "file", "filename", "target_file")


def control_line(action, arg=None):
    """One muxbar action -> the slash command line, or raise ValueError."""
    action = (action or "").strip().lower()
    arg = "" if arg is None else str(arg).strip()
    if "\n" in arg or "\r" in arg:
        raise ValueError("arguments are one line")
    if action in SIMPLE:
        if action == "compact" and arg:  # optional steering instruction
            if not ARG_RE.match(arg):
                raise ValueError("bad compact instruction")
            return f"/compact {arg}"
        return SIMPLE[action]
    if action == "prune":
        if arg.lower() not in PRUNE_KINDS:
            raise ValueError("prune: all, dupes, tools or stale")
        return "/prune" if arg.lower() in ("", "all") else f"/prune {arg.lower()}"
    if action == "effort":
        a = {"medium": "med", "m": "med", "l": "low", "h": "high"}.get(arg.lower(), arg.lower())
        if a not in EFFORTS:
            raise ValueError("effort: " + ", ".join(EFFORTS))
        return f"/effort {a}"
    if action == "context":
        a = arg.lower()
        if a != "max" and not re.fullmatch(r"\d{1,7}k?", a):
            raise ValueError("context: a token count (e.g. 200k) or max")
        if a != "max":
            n = int(a[:-1]) * 1000 if a.endswith("k") else int(a)
            if not 8000 <= n <= 10_000_000:
                raise ValueError("context: 8k to 10M tokens")
        return f"/context {a}"
    if action == "tag":
        if not arg or not ARG_RE.match(arg):
            raise ValueError("tag: some text")
        return f"/tag {arg}"
    if action == "theme":
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", arg):
            raise ValueError("theme: a theme name")
        return f"/theme {arg}"
    raise ValueError(f"unknown action {action!r}")


def edited_path(tool, args):
    """The file an edit/write tool call touches, else None. args: dict or JSON text."""
    t = (tool or "").lower()
    if not (any(v in t for v in EDIT_VERBS) or t.endswith("_patch") or t in ("edit", "write", "patch")):
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    if not isinstance(args, dict):
        return None
    for k in PATH_KEYS:
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


_FOOTER = re.compile(r"\d+(?:\.\d+)?k/\d+(?:\.\d+)?k \(\d+%\)")


def footer_flags(screen):
    """Mode flags + effort from Mux's TUI footer line (the one with `123k/1000k (12%)`).
    Returns {} when no footer is visible (classic renderer, another program)."""
    lines = [ln for ln in (screen or "").splitlines() if _FOOTER.search(ln)]
    if not lines:
        return {}
    # The footer is the last such line; cut off any side panel to its right.
    line = re.split(r"[\u2502\u2503\u2551\u2588]", lines[-1])[0]
    words = [w.strip().lower() for w in line.split("\u00b7")]
    out = {"plan": "plan" in words, "ultra": "ultra" in words, "giga": "giga" in words,
           "sub": "psub" if "psub" in words else ("sub" if "sub" in words else "")}
    m = re.search(r"\b(low|med|medium|high|xhigh|max)\s*$", line.strip().lower())
    if m:
        out["effort"] = "med" if m.group(1) == "medium" else m.group(1)
    return out


def _fmt_k(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


class Live:
    """Mux state -> `mux.*` labels. Call update_* then labels(); diff() gives what changed."""

    def __init__(self):
        self.s = {"agent": "", "model": "", "pct": "", "tokens": "", "window": "", "effort": "",
                  "plan": "", "ultra": "", "giga": "", "sub": "", "compacting": "0", "kids": "0",
                  "file": "", "fileat": "", "port": "", "token": "", "session": ""}
        self.sent = {}

    def update_info(self, info):
        if not isinstance(info, dict):
            return
        ctx = info.get("context") or {}
        self.s.update(agent=info.get("agent") or "", model=info.get("model") or "",
                      session=info.get("sessionId") or "",
                      pct=str(ctx.get("percent", "")) if info.get("inSession") else "",
                      tokens=_fmt_k(ctx.get("tokens")) if info.get("inSession") else "",
                      window=_fmt_k(ctx.get("window")) if info.get("inSession") else "")

    def update_flags(self, flags):
        for k in ("plan", "ultra", "giga"):
            if k in flags:
                self.s[k] = "1" if flags[k] else "0"
        if "sub" in flags:
            self.s["sub"] = flags["sub"]
        if flags.get("effort"):
            self.s["effort"] = flags["effort"]

    def on_event(self, ev, kids=None):
        """Returns True when the screen footer should be re-read (a mode may have changed)."""
        name = ev.get("event") or ""
        data = ev.get("data") or {}
        if kids is not None:
            self.s["kids"] = str(kids)
        if name == "effort_changed":
            self.s["effort"] = str(data.get("to") or ev.get("summary") or "")
        elif name == "model_changed":
            if data.get("to") or ev.get("summary"):
                self.s["model"] = str(data.get("to") or ev.get("summary"))
        elif name == "compaction":
            self.s["compacting"] = "1" if (data.get("phase") or ev.get("summary")) == "start" else "0"
        elif name == "session_start":
            self.s["agent"] = ev.get("agent") or self.s["agent"]
            return True
        elif name == "session_end":
            self.s.update(pct="", tokens="", window="", compacting="0", kids="0", session="")
        elif name == "tool_call":
            p = edited_path(ev.get("tool"), ev.get("args"))
            if p:
                self.s["file"] = p
                self.s["fileat"] = str(int(time.time() * 1000))
        elif name == "command_executed":
            cmd = (data.get("command") or ev.get("summary") or "").split(" ")[0].lower()
            return cmd in ("/plan", "/ultra", "/giga", "/sub", "/psub", "/effort", "/max")
        elif name == "turn_complete":
            return True
        return False

    def labels(self):
        return {f"mux.{k}": v for k, v in self.s.items()}

    def diff(self):
        """Labels that changed since the last diff() (removed ones as empty strings)."""
        now = self.labels()
        out = {k: v for k, v in now.items() if self.sent.get(k) != v}
        self.sent = dict(now)
        return out


def tail_rid(ev, flows):
    """The status record a sub-agent event belongs to (flows: flowId -> rid), or None."""
    flow = ev.get("flowId")
    return flows.get(flow) if flow else None


class Tails:
    """Rolling markdown tail per record id; flush() writes changed ones at most every `every` s."""

    def __init__(self, folder, max_chars=16000, every=1.0):
        self.folder = folder
        self.max = max_chars
        self.every = every
        self.buf = {}
        self.dirty = set()
        self.last = 0.0

    def add(self, rid, text):
        if not rid or not text:
            return
        b = self.buf.get(rid, "") + text
        if len(b) > self.max:
            b = b[-self.max:]
            nl = b.find("\n")
            b = b[nl + 1:] if 0 <= nl < 400 else b
        self.buf[rid] = b
        self.dirty.add(rid)

    def on_event(self, ev, rid):
        name = ev.get("event")
        if name == "text_chunk":
            self.add(rid, ev.get("text") or "")
        elif name == "tool_call":
            self.add(rid, f"\n\n`> {ev.get('tool') or 'tool'}`\n\n")
        elif name == "turn_end":
            self.add(rid, "\n\n---\n\n")

    def start(self, rid, title, task):
        self.buf[rid] = f"# {title}\n\n_{task}_\n\n"
        self.dirty.add(rid)

    def end(self, rid, status):
        self.add(rid, f"\n\n**{status or 'finished'}**\n")

    def flush(self, force=False):
        now = time.monotonic()
        if not self.dirty or (not force and now - self.last < self.every):
            return []
        self.last = now
        written = []
        os.makedirs(self.folder, exist_ok=True)
        for rid in sorted(self.dirty):
            path = os.path.join(self.folder, rid + ".md")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.buf.get(rid, ""))
            os.replace(tmp, path)
            written.append(path)
        self.dirty.clear()
        return written

    def clear(self):
        self.buf.clear()
        self.dirty.clear()
        if os.path.isdir(self.folder):
            for n in os.listdir(self.folder):
                if n.endswith(".md"):
                    try:
                        os.remove(os.path.join(self.folder, n))
                    except OSError:
                        pass
