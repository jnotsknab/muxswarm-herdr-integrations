# muxswarm-herdr-integrations

[Mux-Swarm](https://github.com/jnotsknab/mux-swarm) integrations for the [Herdr app](https://herdr.dev),
the native app built on herdr-core.

- **Status hook**: Mux reports idle, working, needs you and done to Herdr's sidebar and tabs, with
  the current tool or the first line of the answer, and titles the pane `mux: <agent>`.
- **Mux in Herdr**: the Mux icon on its rows and tabs, and Mux-Swarm in the `+` agent menu.
- **Layouts**: Graph (live node graph of machines, spaces, tabs, agents and sub-agents), Board
  (kanban by status), Wall (grid of every agent's screen), Zen (one agent plus a status drawer),
  Ops (remote machines: health and services).
- **hc templates**: `mux-code` and `mux-review`, so any agent can start a Mux helper that reports back.

Agents: follow [AGENTS.md](AGENTS.md). People: the steps below.

## Requirements

Herdr app with herdr-core (`hc`), Mux-Swarm with hooks, Python 3.8+ (stdlib only).
Tested with herdr-app 0.1.12, hc 0.1.17 and Mux-Swarm 0.16.0-nightly on Windows 11 and Linux.

## Manual setup

**1. Status hook**

Copy `hooks/herdr-app-bridge.py` to `<MUX_HOME>/Hooks/`. `<MUX_HOME>` is your Mux install folder
(Windows default `%LOCALAPPDATA%\Mux-Swarm`). Add the entries from `hooks/swarm-hooks.json` to the
`hooks` array in `<MUX_HOME>/Configs/Swarm.json`, replacing `python3` and `<MUX_HOME>` with your
Python command and the absolute path. Restart Mux in a Herdr pane and accept the hooks prompt.

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

**3. hc templates** (optional)

Copy `hc-templates/*.md` to `%APPDATA%\herdr-core\templates` (Windows) or
`~/.config/herdr-core/templates`. On Windows, `sh` must be on PATH (Git's `bin` folder).

```sh
hc run --bg --name review mux-review "Review src/x.cs. Report with hc send $HC_TERMINAL_ID"
```

## How the hook works

herdr-core takes status only from [OSC 7501](https://herdr.dev/core/) reports that a program writes
to its own terminal. Mux starts hooks without a console window, so on Windows the hook attaches to
Mux's console (the first ancestor process that has one) and writes there; on Linux and macOS it
writes to `/dev/tty`. It keeps a small per-terminal state file in the temp folder, orders events by
timestamp, and only marks `done` for the lead agent. Outside a Herdr terminal it does nothing.

| Mux event | Herdr status |
|---|---|
| `session_start` | idle, title `mux: <lead>` |
| `user_input`, `agent_turn_start` | working |
| `tool_call` | working + tool name (`ask_user`: needs you) |
| `tool_result` after `ask_user` | working |
| `delegation` | working, "delegating: ..." |
| `turn_end` / `task_complete` (lead) | done + first line of the answer |
| `session_end` | cleared |

Known limits: if two agents ask questions at the same time, the first answer moves the status back
to working; if the state file is lost mid-session, sub-agent turns can mark the pane done early.

Debug with `MUX_HERDR_APP_DEBUG=1` (log at `<tmp>/mux-herdr-app-hook.log`).
Tests: `python -m pytest hooks/tests -q`.

## License

Apache-2.0. The layouts reuse block structure and icons from Herdr's shipped layouts and mods
(Apache-2.0, [herdrdev/herdr-app](https://github.com/herdrdev/herdr-app)).
