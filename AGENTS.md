# AGENTS.md: installing muxswarm-herdr-integrations into a user's setup

You are an agent asked to add these integrations to an existing Mux-Swarm + Herdr app install.
Follow the steps in order. **Never overwrite a file the user already has without asking.**
Back up everything you change. Report what you did and how to undo it at the end.

## What this repo contains

| Path | Installs to | Purpose |
|---|---|---|
| `hooks/herdr-app-bridge.py` | `<MUX_HOME>/Hooks/` | Mux hook that reports agent status to Herdr (OSC 7501) |
| `hooks/swarm-hooks.json` | merged into `<MUX_HOME>/Configs/Swarm.json` `hooks[]` | 9 hook entries, one per lifecycle event |
| `herdr-app/programs.json` + `herdr-app/mux/` | `<HERDR_APP>/` | Mux icon/name in Herdr, Mux in the `+` agent menu |
| `herdr-app/mods/*` | `<HERDR_APP>/mods/` | graph, board, wall, zen-dock, ops panels |
| `herdr-app/layouts/*` | `<HERDR_APP>/layouts/` | Graph, Board, Wall, Zen, Ops layouts (+ preview SVGs) |
| `herdr-app/keys.snippet.json` | merged into `<HERDR_APP>/keys.json` | optional layout shortcuts |
| `hc-templates/*.md` | herdr-core templates dir | `hc run --bg mux-code "<task>"` style helpers |

## 0. Discover paths and preconditions

1. **Herdr app home** (`<HERDR_APP>`): `~/.config/herdr-app` (all platforms), or `$HERDR_APP_HOME`.
   Read `<HERDR_APP>/AGENTS.md` first: it is Herdr's own guide and is authoritative for layouts and mods.
2. **herdr-core templates dir**: `%APPDATA%\herdr-core\templates` on Windows,
   `~/.config/herdr-core/templates` on Linux/macOS (`$XDG_CONFIG_HOME` overrides). `hc templates` lists them.
3. **Mux home** (`<MUX_HOME>`): the folder holding the Mux binary and `Configs/`
   (Windows default `%LOCALAPPDATA%\Mux-Swarm`). Confirm `Configs/Swarm.json` exists there. Ask the
   user if unsure: scoped instances started with `--swarmcfg` use a different Swarm.json.
4. **Python 3.8+** on PATH (stdlib only). Note the exact command (`python3`, `python`, or a full path).
5. Record versions: `herdr-app --version`, `hc --version`, and the Mux binary's `--version`.

## 1. The status hook (core piece)

1. Copy `hooks/herdr-app-bridge.py` to `<MUX_HOME>/Hooks/herdr-app-bridge.py` (create `Hooks/`).
2. Back up `Configs/Swarm.json` (e.g. `Swarm.json.bak-<date>`).
3. Merge the 9 entries from `hooks/swarm-hooks.json` into Swarm.json's top-level `hooks` array:
   - replace `python3` with the user's Python command and `<MUX_HOME>` with the absolute path
     (escape backslashes in JSON on Windows);
   - **append**; do not replace existing hooks; skip any entry whose `id` already exists;
   - keep the file's encoding, BOM and line endings; confirm it still parses as JSON.
4. If the user has an older `herdr-bridge*` hook (for the Herdr TUI), ask before removing it: it
   targets the old TUI, not the app.
5. The hook does nothing unless Mux runs inside a Herdr terminal (`HC_TERMINAL_ID` set), so it is
   safe for headless, serve and daemon processes.

## 2. Herdr app pieces (optional, each independent)

For every file under `herdr-app/`:
- Destination missing: copy it. Identical: skip. Different: **ask** (show a diff) before replacing.
- `programs.json`: if the user already has one, merge the `programs.mux-swarm` entry into it.
- `keys.snippet.json`: merge section by section into `keys.json`; skip keys that are already bound
  and report the conflict. Never remove the user's bindings.

Then:
- `herdr-app check <HERDR_APP>/mods/<name>` for each copied mod; all must pass.
- `herdr-app status`: `errors` is empty and no `*.error` file appeared next to a layout or `keys.json`.
- Ops: an optional `mods/ops/ops.json` pins services per machine (copy `ops.example.json`).

## 3. hc templates (optional)

Copy `hc-templates/*.md` into the templates dir. They run `mux-swarm`; change `command:` if the
binary has another name or is not on PATH. herdr-core runs template commands through `sh`, so on
Windows `sh` must be on PATH (Git for Windows: `C:\Program Files\Git\bin`). Ask before changing
PATH. Verify with `hc templates`.

## 4. Verify

1. The user restarts Mux (or `/qc` then `/resume`) **inside a Herdr pane** and accepts the
   "enable hooks" prompt (or runs `/hooks on`).
2. `hc ls --json` shows that terminal's `agent` as `mux-swarm`; `hc get <address> --json` shows
   `status.state` = `idle` and title `mux: <agent>`.
3. One message: status goes `working` then `done`. In plan mode an `ask_user` prompt shows
   `blocked` (kind `question`) and the Herdr sidebar lists it under "Needs you".
4. Debugging: set `MUX_HERDR_APP_DEBUG=1` and read `<tmp>/mux-herdr-app-hook.log`.

Do not test by having a helper `hc send` into the user's own live Mux pane: the text is typed into
their session.

## 5. Undo

- Restore the Swarm.json backup (or delete the `herdr-app-*` entries) and delete
  `<MUX_HOME>/Hooks/herdr-app-bridge.py`; restart Mux.
- Delete the copied mods, layouts, `programs.json` entry, key bindings and template files.

## Rules

- Do not modify Mux source or Herdr's shipped mods and layouts (use `mod.clone` / `layout.clone`).
- This repo needs no secrets; never add any.
- Leave the user's existing hooks, keys, layouts and themes untouched unless they say otherwise.
