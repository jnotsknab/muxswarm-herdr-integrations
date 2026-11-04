"""herdr_live.py - live Mux state for Herdr layouts, and the control map the muxbar mod uses.

Pure logic (no I/O except Tails.flush), so it is unit-tested without Mux or Herdr:
  * Live: folds Mux events + session/info into `mux.*` hc labels on this Mux's terminal,
    which every Herdr mod sees through terminals()[i].labels.
  * control_line: one muxbar action -> one Mux slash command (only commands Mux lets an
    extension run with command/run).
  * edited_path / code_paths / changed_since: which file a tool call touched (for the follow pane):
    file tools by their path argument; REPL and shell calls by a quoted or bare path in the code or
    command that was created or changed while the call ran.
  * Tails: a rolling markdown tail per sub-agent record, written for the tail overlay.
  * footer_flags: plan/ultra/giga/sub mode and effort read from Mux's TUI footer, because
    session/info does not report them.
Stdlib only.
"""
import json
import os
import re
import subprocess
import threading
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
READ_VERBS = ("read_text_file", "read_file", "read_media_file", "view_file", "open_file")
CODE_VERBS = ("repl", "python", "shell", "execute_command", "run_command", "exec_command", "bash", "powershell")
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


def _args_dict(args):
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    return args if isinstance(args, dict) else None


def edited_path(tool, args):
    """The file a file tool call names directly (edit, write, patch, create or read), else None.
    args: dict or JSON text. Read tools count too: the follow pane shows what the agent looks at."""
    t = (tool or "").lower()
    if not (any(v in t for v in EDIT_VERBS + READ_VERBS) or t.endswith("_patch") or t in ("edit", "write", "patch", "read")):
        return None
    a = _args_dict(args)
    if a is None:
        return None
    for k in PATH_KEYS:
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# Paths quoted in REPL code or a shell command: "C:\\x\\y.md", 'docs/a.txt', /tmp/x.log ... Only strings
# that look like a file (an extension, or a separator). A path built in code (os.path.join) is not seen.
_QUOTED = re.compile(r"""r?(["'])((?:[A-Za-z]:)?[^"'\n]{1,260}?\.[A-Za-z0-9]{1,8})\1""")
_BARE = re.compile(r"""(?:^|[\s>|=(])((?:[A-Za-z]:[\\/]|[~./\\])[^\s"'<>|;&()]{1,260}?\.[A-Za-z0-9]{1,8})(?=$|[\s"'<>|;&)])""")


def code_paths(tool, args):
    """Candidate files named in a REPL / shell call's code or command, in order, de-duplicated."""
    t = (tool or "").lower()
    if not any(v in t for v in CODE_VERBS):
        return []
    a = _args_dict(args)
    if a is None:
        return []
    text = "\n".join(str(a.get(k)) for k in ("code", "command", "cmd", "script", "input") if a.get(k))
    out = []
    for m in _QUOTED.finditer(text):
        out.append(m.group(2))
    for m in _BARE.finditer(text):
        out.append(m.group(1))
    seen, uniq = set(), []
    for p in out:
        p = p.replace("\\\\", "\\").strip()
        if p.startswith(("http:", "https:")) or p.lower() in seen:
            continue
        seen.add(p.lower())
        uniq.append(p)
    return uniq[:40]


def changed_since(paths, since, cwd=None):
    """The candidate that was created or modified at/after `since` (epoch s), newest first, else None."""
    best = None
    for p in paths:
        full = os.path.expanduser(p)
        if not os.path.isabs(full) and cwd:
            full = os.path.join(cwd, full)
        try:
            st = os.stat(full)
        except OSError:
            continue
        if not os.path.isfile(full) or st.st_mtime < since - 1.0:
            continue
        if best is None or st.st_mtime > best[0]:
            best = (st.st_mtime, os.path.normpath(full))
    return best[1] if best else None


# `225.8k/1000k (23%)` or, early in a session, `0/1000k (0%)`.
_FOOTER = re.compile(r"\d+(?:\.\d+)?k?/\d+(?:\.\d+)?k \(\d+%\)")
_BOX_TOP = re.compile(r"^\s*\u256d")  # the input box's top border: the footer sits right above it
_EFFORT = re.compile(r"(?:^|[\s\u00b7])(low|med|medium|high|xhigh|max)(?=\s*(?:\u00b7|$))")
FLAG_KEYS = ("plan", "ultra", "giga", "sub", "effort")


def footer_flags(screen):
    """Mode flags + effort from Mux's TUI footer: the line just above the input box.
    No such footer (classic renderer, another program, a modal): every flag is "" = unknown."""
    lines = (screen or "").splitlines()
    line = None
    for i in range(len(lines) - 1, 0, -1):
        if _BOX_TOP.match(lines[i]) and _FOOTER.search(lines[i - 1]):
            line = lines[i - 1]
            break
    if line is None:
        return {k: "" for k in FLAG_KEYS}
    line = re.split(r"[\u2502\u2503\u2551\u2588]", line)[0]  # cut off a side panel to its right
    words = [w.strip().lower() for w in line.split("\u00b7")]
    out = {"plan": "plan" in words, "ultra": "ultra" in words, "giga": "giga" in words,
           "sub": "psub" if "psub" in words else ("sub" if "sub" in words else ""), "effort": ""}
    m = _EFFORT.search(line.lower())
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
                  "file": "", "fileat": "", "port": "", "session": ""}
        self.sent = {}
        self.pending = []  # (started epoch s, candidate paths) for REPL / shell calls not seen writing yet
        self.cwd = None  # where relative paths in REPL / shell code resolve (the session's cwd)

    def update_info(self, info):
        if not isinstance(info, dict):
            return
        ctx = info.get("context") or {}
        self.cwd = info.get("cwd") or self.cwd
        self.s.update(agent=info.get("agent") or "", model=info.get("model") or "",
                      session=info.get("sessionId") or "",
                      pct=str(ctx.get("percent", "")) if info.get("inSession") else "",
                      tokens=_fmt_k(ctx.get("tokens")) if info.get("inSession") else "",
                      window=_fmt_k(ctx.get("window")) if info.get("inSession") else "")

    def update_flags(self, flags):
        """flags from footer_flags: True/False per mode, or "" when the footer was not readable."""
        for k in ("plan", "ultra", "giga"):
            if k in flags:
                self.s[k] = "" if flags[k] == "" else ("1" if flags[k] else "0")
        for k in ("sub", "effort"):
            if k in flags:
                self.s[k] = flags[k]

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
                self.touch(p)
            else:
                cands = code_paths(ev.get("tool"), ev.get("args"))
                if cands:  # REPL / shell: follow whichever named file it wrote, once it has run
                    self.pending.append((time.time(), cands))
                    del self.pending[:-8]
        elif name == "tool_result" and self.pending:
            self.resolve_pending(self.cwd)
        elif name == "command_executed":
            cmd = (data.get("command") or ev.get("summary") or "").split(" ")[0].lower()
            return cmd in ("/plan", "/ultra", "/giga", "/sub", "/psub", "/effort", "/max")
        elif name == "turn_complete":
            return True
        return False

    def touch(self, path):
        """Point the follow pane at `path`. fileat changes on every touch, so re-editing the file
        that is already shown still makes the pane reload it."""
        self.s["file"] = path
        self.s["fileat"] = str(int(time.time() * 1000))

    def resolve_pending(self, cwd=None):
        """After a REPL / shell call returns: follow the newest named file it created or changed.
        Also called on a timer, because a background job can write after its call returned."""
        keep = []
        for since, cands in self.pending:
            hit = changed_since(cands, since, cwd)
            if hit:
                self.touch(hit)
            elif time.time() - since < 120:
                keep.append((since, cands))
        self.pending = keep

    def labels(self):
        return {f"mux.{k}": v for k, v in self.s.items()}

    def diff(self):
        """Labels that changed since the last diff() (removed ones as empty strings)."""
        now = self.labels()
        out = {k: v for k, v in now.items() if self.sent.get(k) != v}
        self.sent = dict(now)
        return out


# --- control endpoint handoff ---------------------------------------------------------------
# The endpoint token lives in a file only this user can read (never a label or a command line):
# <app home>/mux/control/<terminal>.json = {"port", "token", "pid"}. Mods read it with readTextFile.
def _restrict(path):
    """Owner-only access: chmod 600 on POSIX, an ACL for this user alone on Windows."""
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    user = os.environ.get("USERNAME")
    if user:
        subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"], capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def write_control_file(folder, terminal, port, token):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "".join(c if c.isalnum() or c in "-_." else "_" for c in terminal) + ".json")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        pass
    _restrict(tmp)  # locked down before the secret goes in
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": token, "pid": os.getpid()}, f)
    os.replace(tmp, path)
    return path


def remove_control_file(path):
    try:
        os.remove(path)
    except OSError:
        pass


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
        self.gen = 0  # bumped by clear(), so an in-flight flush never writes a cleared tail back
        self.lock = threading.RLock()

    def add(self, rid, text):
        if not rid or not text:
            return
        with self.lock:
            self._add(rid, text)

    def _add(self, rid, text):
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
        with self.lock:
            self.buf[rid] = f"# {title}\n\n_{task}_\n\n"
            self.dirty.add(rid)

    def end(self, rid, status):
        self.add(rid, f"\n\n**{status or 'finished'}**\n")

    def flush(self, force=False):
        """Write changed tails. Takes the dirty set under the lock (so an add/end during the write
        stays dirty for the next flush) and writes outside it; a clear() during the write wins."""
        now = time.monotonic()
        with self.lock:
            if not self.dirty or (not force and now - self.last < self.every):
                return []
            self.last = now
            todo = {rid: self.buf.get(rid, "") for rid in self.dirty}
            self.dirty = set()
            gen = self.gen
        written = []
        os.makedirs(self.folder, exist_ok=True)
        for rid in sorted(todo):
            path = os.path.join(self.folder, rid + ".md")
            tmp = path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(todo[rid])
                with self.lock:
                    if self.gen != gen:  # cleared meanwhile: drop the rest
                        os.remove(tmp)
                        break
                    os.replace(tmp, path)
                written.append(path)
            except OSError:
                with self.lock:
                    if self.gen == gen:
                        self.dirty.add(rid)  # try again next flush (e.g. a reader held the file)
        return written

    def clear(self):
        with self.lock:
            self.gen += 1
            self.buf.clear()
            self.dirty.clear()
            if os.path.isdir(self.folder):
                for n in os.listdir(self.folder):
                    if n.endswith(".md"):
                        try:
                            os.remove(os.path.join(self.folder, n))
                        except OSError:
                            pass
