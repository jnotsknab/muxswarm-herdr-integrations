"""Build the Mux x Herdr looks from looks/palettes.json (stdlib only, idempotent).

Writes:
  mux-extension/herdr-looks/extension.json   one Mux extension: a theme per look (herdr-<name>) + one
                                             shared shape, splash, thinking animation, tool labels and
                                             markdown style (all colours by theme role, so they follow
                                             whichever herdr-* theme is active)
  herdr-app/layouts/mux-<layout>.json        four layout + look combos (each sets its Herdr theme)

The Herdr side pairs with Herdr's built-in presets (graphite, ink, moss, paper), whose colours the
palettes were read from, so nothing needs installing in Herdr's themes/ folder.

    python looks/build.py           # write
    python looks/build.py --check   # exit 1 if any output is out of date (used by the tests)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALETTES = os.path.join(ROOT, "looks", "palettes.json")

# Herdr's spinner is a turning ring; this is its terminal twin.
RING = ["\u25dc", "\u25e0", "\u25dd", "\u25de", "\u25e1", "\u25df"]

# Compact mark for the splash: a rounded tile like Herdr's app icon, with the wordmark beside it.
ART = [
    "\u256d\u2500\u2500\u2500\u2500\u2500\u256e",
    "\u2502 \u25cf \u25cf \u2502  mux",
    "\u2502  \u25e1  \u2502  \u00b7 herdr",
    "\u2570\u2500\u2500\u2500\u2500\u2500\u256f",
]

QUIPS = ["working", "reading", "thinking it through", "checking", "putting it together", "looking closer"]

SPLASH = [
    "ctrl-alt-5 opens the Wall: every agent as a live terminal you can type into.",
    "ctrl-shift-m toggles the Mux strip: context, effort, compact, prune.",
    "/herdr ls lists every agent in Herdr; /herdr panel docks them here.",
    "Agents can ask each other: herdr_ask sends a question and returns the answer.",
    "herdr_show opens a file beside you; herdr_focus brings an agent into view.",
    "Sub-agents show up in Graph, Board and Wall with their own icon.",
    "Click a sub-agent anywhere in Herdr to read its live transcript.",
    "The follow pane (ctrl-shift-f in Graph) tracks the file Mux is editing.",
    "Switch looks from the looks strip: Herdr theme and Mux /theme together.",
]

TOOL_LABELS = {"read": "Reading", "write": "Writing", "edit": "Editing", "execute": "Running", "search": "Searching",
               "list": "Listing", "fetch": "Fetching", "create": "Creating", "delete": "Deleting", "move": "Moving",
               "spawn": "Starting", "ask": "Asking", "send": "Sending", "wait": "Waiting on", "show": "Showing",
               "focus": "Showing", "screen": "Looking at"}


def mux_theme(name, look):
    c = look["colors"]
    light = look["light"]
    return {
        "name": f"herdr-{name}",
        "base": "light" if light else "dark",
        "step": c["working"], "success": c["ansi2"], "warning": c["working"], "error": c["blocked"],
        "info": c["muted"], "muted": c["muted"] if light else c["dim"],
        "accent": c["accent"], "prompt": c["foreground"], "banner": c["accent"], "agent": c["ansi6"],
        "mdHeading": c["accent"], "mdCode": c["ansi3"], "mdLink": c["ansi4"], "mdQuote": c["muted"],
        "cardBg": c["cardBg"], "inputBg": c["inputBg"], "codeBg": c["codeBg"], "inlineCodeBg": c["inputBg"],
        "diffAddBg": c["diffAdd"], "diffDelBg": c["diffDel"], "diffHunkBg": c["diffHunk"], "border": c["border"],
    }


def regions():
    return {
        "notice": {"okMark": "\u2713", "warnMark": "!", "errorMark": "\u00d7", "ok": "success", "warn": "warning",
                   "error": "error", "info": "muted"},
        "header": {"template": "{agent}  \u00b7  {model}", "accent": "accent"},
        "userMessage": {"style": "bubble", "barFg": "border"},
        "agentHeader": {"mark": "\u25cf", "rule": "\u2508", "fg": "agent", "ruleFg": "border"},
        "answer": {"lead": "\u25cf", "leadFg": "accent"},
        "reasoning": {"fg": "muted", "italic": True},
        "toast": {"mark": "\u25cf", "markFg": "accent"},
        "divider": {"glyph": "\u2502", "fg": "border", "activeFg": "accent"},
        "scrollbar": {"thumb": "\u2503", "track": " ", "thumbFg": "border"},
        "toolCard": {"dot": "\u25cf", "ok": "\u2713", "error": "\u00d7", "result": "\u2570",
                     "railFg": "border", "pendingFg": "warning", "okFg": "success", "errorFg": "error", "labelFg": "text"},
        "diff": {"corner": "\u256d", "end": "\u2570", "line": "\u2500", "railFg": "border"},
        "delegation": {"arrow": "\u2192", "branch": "\u2570", "mark": "\u25cf", "fg": "agent"},
        "thinking": {"fg": "accent"},
        "compose": {"shape": "box", "border": "rounded", "padX": 1, "borderFg": "border", "gap": 0},
        "footer": {"position": "border", "style": "dot", "separatorFg": "border"},
        "input": {"prompt": "\u203a", "promptFg": "accent", "placeholder": "ask Mux\u2026", "placeholderFg": "muted"},
        "palette": {"selected": "\u203a", "selectedFg": "accent", "titleMark": "\u2502", "titleFg": "accent"},
        "modal": {"title": "\u25cf", "titleFg": "accent", "selected": "\u203a", "selectedFg": "accent",
                  "checked": "\u25c9", "checkedFg": "accent", "unchecked": "\u25cb"},
        "panel": {"frame": "rounded", "frameFg": "border", "header": "plain", "selectedStyle": "bar",
                  "bar": "\u2503", "tabActiveFg": "accent"},
        "block": {"rail": "\u2502", "railFg": "border", "titleFg": "accent"},
        "splash": {
            # One card: the mark + one message, then commands, then recent sessions. Version in the border only.
            "frame": "rounded", "borderFg": "border", "align": "center", "width": 70, "padY": 1,
            "layout": ["art | title message", "commands", "recent"],
            "art": ART, "artFg": "accent", "accentFg": "accent",
            "title": "mux \u00b7 herdr", "titleFg": "accent",
            "borderTitle": " mux {version} ", "headings": "rule", "headingFg": "muted",
            "bullet": "\u203a", "bulletFg": "accent", "recentCount": 3, "divider": "gap", "contentAlign": "left",
        },
    }


def mux_extension(looks):
    return {
        "name": "herdr-looks",
        "version": "0.1.0",
        "description": "Mux x Herdr looks: themes herdr-graphite / herdr-ink / herdr-moss / herdr-paper, each paired "
                       "with the Herdr theme of the same name; rounded box input with the status in its border, "
                       "Herdr-style splash and ring spinner. Switch with /theme herdr-<look> or the looks strip in Herdr.",
        "themes": [mux_theme(n, lk) for n, lk in looks.items()],
        "footer": {"template": "{mode} {context} || {model} {effort}"},
        "thinking": {"frames": RING, "intervalMs": 90, "quips": QUIPS, "quipIntervalMs": 2400, "shuffle": True,
                     "suffix": "\u2026"},
        "toolLabels": TOOL_LABELS,
        "splash": SPLASH,
        "markdown": {"tableBorder": "rounded", "bullet": "\u2022", "rule": "\u2500"},
        "tui": {"regions": regions()},
    }


# --- layouts -----------------------------------------------------------------------------------
def sidebar():
    return {"id": "sidebar", "type": "column", "size": {"px": 268}, "min": 44, "max": 480, "background": "chrome",
            "resizable": False, "children": [
                {"id": "brand", "type": "block", "size": {"px": 46}, "window_drag": True, "content": {"mod": "workspace-chrome"}},
                {"id": "sidebar-lists", "type": "column", "children": [
                    {"id": "spaces", "type": "block", "size": {"weight": 1}, "min": 90, "content": {"mod": "spaces"}},
                    {"id": "agents", "type": "block", "size": {"weight": 1}, "min": 90, "content": {"mod": "agents-mux"}}]},
                {"id": "sidebar-footer", "type": "block", "size": {"px": 69}, "content": {"mod": "workspace-chrome", "props": {"footer": True}}}]}


PANE = {"gap": 8, "radius": 10, "background": "background", "lone": True, "border": {"width": 1, "color": "border"},
        "focus": {"width": 1, "color": "accent"},
        "header": {"content": {"mod": "pane"}, "height": 30, "position": "top", "reveal": "always"}}


def strip(id_, mod, px, props=None):
    b = {"id": id_, "type": "block", "size": {"px": px}, "radius": 8, "border": {"width": 1, "color": "border"},
         "content": {"mod": mod}}
    if props:
        b["content"]["props"] = props
    return b


def looks_bar(look):
    return strip("looks", "looks", 30, {"look": look})


def layout(look, body):
    return {"id": "root", "type": "row", "titlebar": "none", "traffic_lights": [12, 16], "background": "canvas",
            "terminal_padding": [14, 12], "divider": {"width": 1, "color": "border"}, "theme": look,
            "children": body}


def layouts():
    tabs = {"id": "tabs", "type": "block", "size": {"px": 42}, "window_drag": True, "content": {"mod": "tabs"}}
    status = {"id": "status", "type": "block", "size": {"px": 28}, "content": {"mod": "workspace-status"}}
    main = {"id": "main", "type": "block", "content": {"tab": "active", "pane": PANE}}
    out = {}
    # lead: one Mux big, graph strip above, muxbar below
    out["lead"] = layout("graphite", [sidebar(), {"id": "work", "type": "column", "resizable": False, "children": [
        tabs,
        {"id": "work-body", "type": "column", "padding": 8, "gap": 8, "children": [
            {"id": "graph", "type": "block", "size": {"weight": 0.85}, "min": 260, "radius": 10,
             "border": {"width": 1, "color": "border"}, "content": {"mod": "graph"}},
            dict(main, size={"weight": 1.45}),
            strip("muxbar", "muxbar", 44), looks_bar("graphite")]},
        status]}])
    # swarm: the Wall (live tiles) + muxbar
    out["swarm"] = layout("ink", [sidebar(), {"id": "work", "type": "column", "resizable": False, "children": [
        tabs,
        {"id": "wall-body", "type": "column", "padding": 8, "gap": 8, "children": [
            {"id": "wall-bar", "type": "block", "size": {"px": 24}, "content": {"mod": "wall"}},
            {"id": "wall-empty", "type": "block", "content": {"mod": "wall", "props": {"empty": True}}}]},
        strip("muxbar", "muxbar", 44), looks_bar("ink"), status]}])
    # review: Mux + follow pane + changes side by side
    out["review"] = layout("paper", [sidebar(), {"id": "work", "type": "column", "resizable": False, "children": [
        tabs,
        {"id": "work-body", "type": "row", "padding": 8, "gap": 8, "children": [
            dict(main, size={"weight": 1.1}),
            {"id": "side", "type": "column", "gap": 8, "size": {"weight": 1}, "children": [
                {"id": "follow", "type": "block", "size": {"weight": 1.4}, "radius": 10,
                 "border": {"width": 1, "color": "border"}, "content": {"mod": "mux-follow"}},
                {"id": "changes", "type": "block", "size": {"weight": 1}, "radius": 10,
                 "border": {"width": 1, "color": "border"}, "content": {"mod": "changes"}}]}]},
        strip("muxbar", "muxbar", 44), looks_bar("paper"), status]}])
    # zen: one Mux, no chrome, floating dock
    zen = layout("moss", [{"id": "work", "type": "column", "padding": 10, "gap": 8, "children": [
        {"id": "main", "type": "block", "content": {"agent": "focused"}},
        looks_bar("moss")]}])
    zen["floating"] = [{"id": "dock", "content": {"mod": "zen-dock"}, "edge": "left", "align": "center", "peek": 26}]
    out["zen"] = zen
    return out


def outputs():
    src = json.load(open(PALETTES, encoding="utf-8"))
    files = {os.path.join("mux-extension", "herdr-looks", "extension.json"): mux_extension(src["looks"])}
    for name, tree in layouts().items():
        files[os.path.join("herdr-app", "layouts", f"mux-{name}.json")] = tree
    return {p: json.dumps(v, indent=2, ensure_ascii=False) + "\n" for p, v in files.items()}


def main():
    check = "--check" in sys.argv
    stale = []
    for rel, text in outputs().items():
        path = os.path.join(ROOT, rel)
        cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if cur == text:
            continue
        stale.append(rel)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    if check and stale:
        print("out of date (run python looks/build.py):\n  " + "\n  ".join(stale))
        sys.exit(1)
    print(("stale: " if check else "wrote: ") + (", ".join(stale) or "nothing"))


if __name__ == "__main__":
    main()
