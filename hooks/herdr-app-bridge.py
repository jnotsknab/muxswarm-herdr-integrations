"""herdr_status.py - Mux-Swarm events -> Herdr app agent status (OSC 7501).

Used two ways:
  * by the `herdr` Mux extension (main.py imports it; one long-lived process, state in memory);
  * as a plain Mux hook: `python herdr_status.py` reading one JSON event per line on stdin
    (one process per event, so state lives in a small locked file per terminal).

herdr-core takes a terminal's status only from OSC 7501 reports the program writes to its own
terminal. Mux starts hooks and extension processes without a console window, so their stdout never
reaches the pane. On Windows we attach to the nearest ancestor console that has a (pseudo) window,
which is Mux's ConPTY console, and write to CONOUT$. On POSIX we write to /dev/tty.

Inert unless HC_TERMINAL_ID is set (Mux runs inside a herdr-core terminal). Stdlib only.

Root record (the pane):   idle -> working (tool / delegating / compacting) -> done | error,
                          blocked (kind=question) while ask_user waits; cleared on session_end.
Child records (id=...):   one per running delegation or background job, cleared when it ends.
"""
import base64
import json
import os
import re
import sys
import tempfile
import time

APP = "mux-swarm"
STATE_DIR = os.path.join(tempfile.gettempdir(), "mux-herdr-app")
LOG = os.path.join(tempfile.gettempdir(), "mux-herdr-app-hook.log")
DEBUG = os.environ.get("MUX_HERDR_APP_DEBUG") == "1"


def log(msg, always=False):
    if not (always or DEBUG):
        return
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] pid={os.getpid()} {msg}\n")
    except OSError:
        pass


# --- escapes ---------------------------------------------------------------------------------
def _b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def osc7501(state, kind=None, msg=None, rid=None, title=None):
    fields = [f"state={state}"]
    if kind:
        fields.append(f"kind={kind}")
    if rid:
        fields.append(f"id={rid}")
    if state != "clear":
        fields.append(f"app={APP}")
    if title:
        fields.append(f"title={_b64(title)}")
    if msg:
        fields.append(f"msg={_b64(msg)}")
    return "\x1b]7501;" + ":".join(fields) + "\x1b\\"


def osc_title(title):
    # ASCII only: BEL and ESC would end the sequence early.
    safe = "".join(ch for ch in title if 32 <= ord(ch) < 127)
    return f"\x1b]2;{safe}\x07"


def one_line(s, n=80):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def rid_for(prefix, key):
    """A record id herdr accepts: short, no separators that 7501 uses."""
    return prefix + re.sub(r"[^A-Za-z0-9_.-]", "", str(key or ""))[:40]


_TS = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?")


def ticks(ts):
    """ISO timestamp -> sortable int (100 ns). Mux trims trailing zeros, so strings don't sort."""
    m = _TS.match(str(ts or ""))
    if not m:
        return 0
    y, mo, d, h, mi, s, frac = m.groups()
    return int(f"{y}{mo}{d}{h}{mi}{s}") * 10_000_000 + int((frac or "0")[:7].ljust(7, "0"))


# --- the mapping (pure) ----------------------------------------------------------------------
def decide(st, ev):
    """(state dict, event dict) -> (new state dict, list of escape strings to write)."""
    st = dict(st)
    st["subs"] = dict(st.get("subs") or {})
    out = []
    t = ticks(ev.get("timestamp"))
    if t and t < st.get("last", 0):
        return st, out  # an older event arriving late: never move status backwards
    if t:
        st["last"] = t

    name = ev.get("event") or ""
    agent = (ev.get("agent") or "").strip()
    data = ev.get("data") or {}
    flow = ev.get("flowId")
    lead = st.get("lead")
    is_lead = not lead or not agent or agent.lower() == lead.lower()
    blocked = st.get("state") == "blocked"

    def report(state, kind=None, msg=None):
        key = [state, kind, msg]
        if st.get("sent") == key:
            return
        st.update(state=state, sent=key)
        out.append(osc7501(state, kind, msg))

    def who(text):
        return text if is_lead else f"{agent}: {text}"

    def sub(rid, state, msg, title=None):
        st["subs"][rid] = title or st["subs"].get(rid) or ""
        out.append(osc7501(state, msg=msg, rid=rid, title=st["subs"][rid]))

    def unsub(rid):
        if st["subs"].pop(rid, None) is not None:
            out.append(osc7501("clear", rid=rid))

    if name == "session_start":
        for rid in list(st["subs"]):
            unsub(rid)
        # Mux that sends `data` on session_start also sends turn_complete (one per user turn);
        # older Mux only has turn_end, which then has to end the turn.
        st = {"last": st.get("last", 0), "lead": agent or "mux", "subs": {}, "tc": bool(ev.get("data"))}
        out.append(osc_title(f"mux: {st['lead']}"))
        report("idle", msg=f"{st['lead']} ready")
    elif name in ("user_input", "agent_turn_start"):
        if is_lead and (not blocked or name == "user_input"):
            report("working", msg="thinking")
    elif name == "tool_call":
        tool = ev.get("tool") or "tool"
        if tool == "ask_user":
            st["ask_agent"] = agent
            report("blocked", kind="question", msg=who("asking you a question"))
        elif flow and rid_for("d", flow) in st["subs"] and not is_lead:
            sub(rid_for("d", flow), "working", f"{agent}: {tool}")
        elif not blocked:
            report("working", msg=who(tool))
    elif name == "tool_result":
        if blocked and agent.lower() == (st.get("ask_agent") or "").lower():
            st.pop("ask_agent", None)
            report("working", msg=who("answered"))
    elif name == "tool_denied":
        if not blocked:
            report("working", msg=who(f"denied {data.get('tool') or ev.get('summary') or 'a tool'}"))
    elif name == "delegation":
        to = data.get("to") or "specialist"
        task = one_line(ev.get("summary"), 60)
        if flow:
            sub(rid_for("d", flow), "working", task, title=to)
        if not blocked:
            report("working", msg=f"delegating to {to}")
    elif name == "delegation_end":
        if flow:
            unsub(rid_for("d", flow))
    elif name == "job_start":
        jid = data.get("id") or ev.get("summary")
        if jid:
            sub(rid_for("j", jid), "working", f"background: {data.get('agent') or agent}", title=data.get("agent") or agent)
    elif name == "job_end":
        jid = data.get("id")
        if jid:
            unsub(rid_for("j", jid))
    elif name == "compaction":
        if (data.get("phase") or ev.get("summary")) == "start" and not blocked:
            report("working", msg="compacting context")
    elif name == "turn_end":
        if is_lead:
            st["answer"] = one_line(ev.get("summary"))
            if not st.get("tc"):  # older Mux without turn_complete: every lead turn_end ends it
                st.pop("ask_agent", None)
                report("done", msg=st["answer"] or "turn finished")
    elif name == "turn_complete":
        if is_lead:
            st["tc"] = True
            st.pop("ask_agent", None)
            outcome = data.get("outcome") or ev.get("summary") or "ok"
            if outcome == "ok":
                report("done", msg=st.pop("answer", None) or "turn finished")
            elif outcome == "interrupted":
                report("idle", msg="interrupted")
            else:
                report("error", msg=one_line(data.get("error") or f"turn {outcome}"))
    elif name == "task_complete":
        if is_lead and not st.get("tc"):
            report("done", msg=one_line(ev.get("summary")) or "task complete")
    elif name == "session_end":
        st = {"last": st.get("last", 0), "subs": {}}
        out.append(osc7501("clear"))
        out.append(osc_title(""))
    return st, out


# --- the terminal ----------------------------------------------------------------------------
class Terminal:
    """Writes escape bytes to the terminal Mux is drawing in."""

    def __init__(self):
        self._w = None
        self._tried = False

    def write(self, data):
        if not self._tried:
            self._tried = True
            try:
                self._w = _open_posix() if os.name != "nt" else _open_windows()
            except Exception as e:  # never let terminal plumbing crash the caller
                log(f"terminal open failed: {e!r}", always=True)
        if self._w:
            try:
                self._w(data.encode("ascii", "replace"))
            except Exception as e:
                log(f"terminal write failed: {e!r}", always=True)


def _open_posix():
    try:
        tty = open("/dev/tty", "wb", buffering=0)
        return tty.write
    except OSError:
        log("no /dev/tty; status reports are off", always=True)
        return None


def _open_windows():
    import ctypes
    from ctypes import wintypes as W

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetConsoleWindow.restype = W.HWND
    k.AttachConsole.argtypes = [W.DWORD]
    k.CreateFileW.restype = W.HANDLE
    k.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    k.WriteFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
    k.CreateToolhelp32Snapshot.restype = W.HANDLE
    k.CloseHandle.argtypes = [W.HANDLE]

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", W.DWORD),
                    ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", W.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]
    k.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PE)]

    snap = k.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    parents = {}
    e = PE()
    e.dwSize = ctypes.sizeof(PE)
    ok = k.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        parents[e.th32ProcessID] = e.th32ParentProcessID
        ok = k.Process32NextW(snap, ctypes.byref(e))
    k.CloseHandle(snap)

    # Our console is the hidden one Mux created for us. Walk up to the first ancestor whose
    # console has a window: under herdr that is Mux's ConPTY pseudo-console.
    pid = os.getpid()
    for _ in range(8):
        pid = parents.get(pid, 0)
        if not pid:
            break
        k.FreeConsole()
        if k.AttachConsole(pid) and k.GetConsoleWindow():
            log(f"attached to console of pid {pid}")
            break
    else:
        pid = 0
    if not pid:
        log("no ancestor console with a window; status reports are off", always=True)
        return None
    k.SetConsoleCtrlHandler(None, True)  # ignore Ctrl+C on the borrowed console
    h = k.CreateFileW("CONOUT$", 0xC0000000, 0x3, None, 3, 0, None)
    if not h or h == W.HANDLE(-1).value:
        log("CONOUT$ open failed", always=True)
        return None

    def write(b):
        n = W.DWORD()
        k.WriteFile(h, b, len(b), ctypes.byref(n), None)

    return write


# --- hook mode: one process per event, state in a locked file ---------------------------------
def state_path():
    key = re.sub(r"[^A-Za-z0-9_.-]", "_",
                 f"{os.environ.get('HC_SCOPE', '')}_{os.environ.get('HC_TERMINAL_ID', '')}")
    return os.path.join(STATE_DIR, key + ".json")


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(path, st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, path)
    except OSError as e:
        log(f"state save failed: {e!r}", always=True)


class Lock:
    """Cross-process lock per terminal: async hooks run as concurrent processes."""

    def __init__(self, path):
        self.path = path + ".lock"
        self.f = None

    def __enter__(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            self.f = open(self.path, "a+b")
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
        except OSError as e:
            log(f"lock failed, continuing unlocked: {e!r}", always=True)
        return self

    def __exit__(self, *exc):
        if self.f:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self.f.close()


def hook_main():
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    inside = bool(os.environ.get("HC_TERMINAL_ID"))
    term = Terminal() if inside else None
    path = state_path() if inside else None
    for line in sys.stdin:  # always drain stdin so Mux's pipe never blocks
        line = line.strip()
        if not inside or not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        with Lock(path):
            st, out = decide(load_state(path), ev)
            if out:
                term.write("".join(out))
            save_state(path, st)


if __name__ == "__main__":
    try:
        hook_main()
    except Exception as e:
        log(f"fatal: {e!r}", always=True)
