# muxswarm-herdr-integrations

[Mux-Swarm](https://github.com/jnotsknab/mux-swarm) integrations for the [Herdr app](https://herdr.dev),
the native app built on herdr-core.

**Mux side** (`mux-extension/herdr`, a Mux extension):

- **Live status**: Herdr's sidebar and tabs show each Mux session as idle, working (with the current
  tool), needs you (`ask_user`), done (first line of the answer) or error. The pane is titled
  `mux: <agent>`. Every running delegation and background job is its own child record, so the Graph
  and Board layouts show sub-agents under the lead.
- **`/herdr`**: `ls`, `peek <t>` (the screen as plain text: TUI frames, scrollbars, input box and footer
  removed), `send <t> <text>`, `spawn <template|command> [task]`,
  `layout <name>`, `panel`. Works mid-turn.
- **Footer chip**: `herdr 4 · 1 working · 1 need you`.
- **Docked panel** (`/herdr panel`, TUI and web UI): every Herdr agent with status; select one to
  see its screen, then send it text, or spawn a helper from the input.
- **Agent tools**: `herdr_list`, `herdr_spawn`, `herdr_read`, `herdr_send`, `herdr_wait`,
  `herdr_stop`. A Mux agent can hand work to Claude Code, Codex or another Mux in its own Herdr pane,
  wait for it and read the result. `herdr_ask` asks an idle agent a question and returns its answer;
  `herdr_focus` brings an agent into view; `herdr_show` opens a file viewer, a terminal or a layout
  for the user; `herdr_screen` returns what the window shows (optionally a screenshot).
- **Live Mux state for layouts**: `mux.*` labels on Mux's terminal (agent, model, context use,
  effort, plan/ultra/giga, compacting, sub-agent count, last edited file), a loopback control
  endpoint (port + token are labels too) and a rolling transcript per sub-agent, which the
  `muxbar`, `mux-follow` and `agents-mux` mods use.

Or `hooks/`: the status part alone, as a plain Mux hook.

**Herdr side** (`herdr-app/`): the Mux icon on its rows and tabs and Mux-Swarm in the `+` menu,
plus layouts: Graph (live node graph of machines, spaces, tabs, agents and sub-agents), Board
(kanban by status), Wall (every agent as a live, typeable terminal tile; Mux sub-agents as transcript tiles), Zen (one agent and a status drawer),
Ops (remote machines: health and services). **hc templates** `mux-code` and `mux-review`.

Mods that make Mux feel native in Herdr (need the extension):

- **`muxbar`**: a control strip (Graph, Wall, Board; `ctrl-shift-m` toggles it): context gauge,
  effort and context-window sliders, Plan/Ultra/Giga toggles, Compact, Prune, Retry, Undo, Diff,
  Review, Cost, a More menu (prune kinds, handoff, tokens, cost by model, status, doctor, limits,
  view toggles, ...), an Ask Mux box, and a chip per running sub-agent. Mux queues these and runs
  them when the session is idle. `muxbar/ask.js` lets any other mod add an "Ask Mux" button.
- **`agents-mux`**: Herdr's Agents sidebar plus Mux sub-agents under their Mux, each with a role
  icon (code, web, memory, data, docs, review, ...).
- **Sub-agents everywhere**: Graph, Board, Wall and Zen show each delegation and background job
  with its role icon. Clicking one opens its live transcript (Wall tiles show it inline).
- **`mux-follow`**: a read-only code view that follows the file Mux is editing (Graph's side
  panel, `ctrl-shift-f`), with a Follow toggle. `herdr_show` opens it for any file.

Agents: follow [AGENTS.md](AGENTS.md). People: the steps below.

## Requirements

Herdr app with herdr-core (`hc` and `herdr-app` on PATH), Mux-Swarm 0.16+ (extensions; the hook works
on older builds), Python 3.8+ (stdlib only). Tested with herdr-app 0.1.12, hc 0.1.17 and Mux-Swarm
0.16.0-nightly on Windows 11 and Linux.

## Manual setup

**1. Mux: the extension** (recommended)

Copy `mux-extension/herdr/` to `<MUX_HOME>/Extensions/herdr/` (`<MUX_HOME>` is your Mux install folder;
Windows default `%LOCALAPPDATA%\Mux-Swarm`). In `Configs/Config.json`:

```jsonc
"extensions": { "enabled": true, "trusted": ["herdr"] }   // keep your other entries
```

With a sandbox backend other than `host`, also add `"unsandboxed": ["herdr"]` (it runs `hc` and writes
to your terminal). For the agent tools, add `"herdr"` to an agent's `mcpServers` in Swarm.json.
Then `/refresh` (or restart Mux) inside a Herdr pane.

**1b. Mux: the hook instead** (status only): copy `hooks/herdr-app-bridge.py` to `<MUX_HOME>/Hooks/`
and add the entry from `hooks/swarm-hooks.json` to `hooks` in `Configs/Swarm.json`, with your Python
command and the absolute path. Do not install both.

**2. Herdr app pieces** (into `~/.config/herdr-app`)

| From | To |
|---|---|
| `herdr-app/programs.json` | `programs.json` (merge if you have one) |
| `herdr-app/mux/` | `mux/` |
| `herdr-app/mods/<name>/` | `mods/<name>/` |
| `herdr-app/layouts/*` | `layouts/` |

`ctrl-shift-l` cycles layouts. Optionally merge `herdr-app/keys.snippet.json` into `keys.json`
(`ctrl-alt-3`..`7` jump to a layout). Check a mod with `herdr-app check ~/.config/herdr-app/mods/graph`.
For Ops, copy `mods/ops/ops.example.json` to `mods/ops/ops.json` to pin services per machine.

**3. hc templates** (optional): copy `hc-templates/*.md` to `%APPDATA%\herdr-core\templates` (Windows)
or `~/.config/herdr-core/templates`. On Windows, `sh` must be on PATH (Git's `bin` folder).

```text
/herdr spawn mux-review review the diff on this branch
```

## How status works

herdr-core takes status only from [OSC 7501](https://herdr.dev/core/) reports that a program writes
to its own terminal. Mux starts hooks and extension processes without a console window, so on Windows
the code attaches to Mux's console (the first ancestor process that has one) and writes there; on
Linux and macOS it writes to `/dev/tty`. Outside a Herdr terminal it does nothing.

| Mux event | Herdr status |
|---|---|
| `session_start` | idle, title `mux: <lead>` |
| `user_input`, `agent_turn_start` | working |
| `tool_call` | working + tool name (`ask_user`: needs you) |
| `tool_result` after `ask_user` | working |
| `delegation` / `delegation_end` | child record per delegation (title = specialist) |
| `job_start` / `job_end` | child record per background job |
| `compaction` start | working, "compacting context" |
| `turn_complete` (lead) | done + first line of the answer; idle if interrupted; error if failed |
| `session_end` | cleared |

On Mux builds without `turn_complete`, the lead's `turn_end` marks the turn done.

**Launch Python with `-I -S`** (the shipped hook snippet and extension do). Without them every Python
start imports `site`, which runs every `.pth` file in site-packages; on Windows a pywin32 install or a
`.pth` pointing at a network share can make that take seconds. Mux starts these processes without
waiting on them, but many slow starts at once can stall its UI for several seconds. Both scripts are
stdlib only, so they do not need `site`.

Debug with `MUX_HERDR_APP_DEBUG=1` (log at `<tmp>/mux-herdr-app-hook.log`).
Tests: `python -m pytest hooks/tests mux-extension/herdr/tests -q`.

## License

Apache-2.0. The layouts reuse block structure and icons from Herdr's shipped layouts and mods
(Apache-2.0, [herdrdev/herdr-app](https://github.com/herdrdev/herdr-app)).
