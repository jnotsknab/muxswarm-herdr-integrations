# AGENTS.md: installing muxswarm-herdr-integrations into a user's setup

You are an agent asked to add these integrations to an existing Mux-Swarm + Herdr app install.
Follow the steps in order. **Never overwrite a file the user already has without asking.**
Back up everything you change. Report what you did and how to undo it at the end.

## What this repo contains

| Path | Installs to | Purpose |
|---|---|---|
| `mux-extension/herdr/` | a folder in Mux `extensions.dirs` | **Recommended.** Status (with sub-agent records), `/herdr` command, footer chip, docked agents panel, `herdr_*` agent tools |
| `hooks/herdr-app-bridge.py` + `hooks/swarm-hooks.json` | `<MUX_HOME>/Hooks/` + Swarm.json `hooks[]` | Status only, as a plain hook. Use **either** this or the extension, not both |
| `herdr-app/programs.json` + `herdr-app/mux/` | `<HERDR_APP>/` | Mux icon/name in Herdr, Mux in the `+` agent menu |
| `herdr-app/mods/*` | `<HERDR_APP>/mods/` | graph, board, wall, zen-dock, ops panels |
| `herdr-app/layouts/*` | `<HERDR_APP>/layouts/` | Graph, Board, Wall, Zen, Ops layouts (+ preview SVGs) |
| `herdr-app/keys.snippet.json` | merged into `<HERDR_APP>/keys.json` | optional layout shortcuts |
| `hc-templates/*.md` | herdr-core templates dir | `mux-code` / `mux-review` helpers for `hc run` and `herdr_spawn` |

## 0. Discover paths and preconditions

1. **Herdr app home** (`<HERDR_APP>`): `~/.config/herdr-app` (all platforms), or `$HERDR_APP_HOME`.
   Read `<HERDR_APP>/AGENTS.md` first: it is Herdr's own guide and is authoritative for layouts and mods.
2. **herdr-core templates dir**: `%APPDATA%\herdr-core\templates` on Windows,
   `~/.config/herdr-core/templates` on Linux/macOS (`$XDG_CONFIG_HOME` overrides). `hc templates` lists them.
3. **Mux home** (`<MUX_HOME>`): the folder holding the Mux binary and `Configs/`
   (Windows default `%LOCALAPPDATA%\Mux-Swarm`). Confirm `Configs/Config.json` and `Configs/Swarm.json`
   exist there. Ask the user if unsure: scoped instances (`--cfg` / `--swarmcfg`) use other files.
4. **Python 3.8+** on PATH (stdlib only). Note the exact command (`python3`, `python`, or a full path).
5. `hc` and `herdr-app` on PATH (the extension calls them). Record `herdr-app --version`,
   `hc --version` and the Mux binary's `--version`.
6. Read Mux's own `Context/DOCS.md` sections "Extensions" and "Event Hooks" if anything below
   does not match the installed version.

## 1a. The extension (recommended)

1. Copy `mux-extension/herdr/` to a folder the user keeps extensions in (e.g. `<MUX_HOME>/Extensions/herdr`,
   which Mux scans by default) and leave the repo copy alone. Skip `tests/`.
2. Back up `Configs/Config.json`. In its `extensions` block (create it if missing):
   - `"enabled": true`
   - add `"herdr"` to `"trusted"` (processes only start when trusted)
   - if the extension folder is not `<MUX_HOME>/Extensions/`, add its parent folder to `"dirs"`
   - if `sandbox.backend` is not `host`, add `"herdr"` to `"unsandboxed"`: it must reach `hc` and
     the user's terminal. Ask the user first and say why.
   Keep every existing entry; keep the file's encoding and line endings; confirm it parses.
3. The `process.command` is `python`. If the user's Python is named differently, edit
   `extension.json` in the installed copy.
4. Optional, for agent tools: add `"herdr"` to the `mcpServers` list of the agents that should get
   `herdr_list`, `herdr_spawn`, `herdr_read`, `herdr_send`, `herdr_wait`, `herdr_stop` in Swarm.json
   (back it up first), or a `toolPatterns` entry `herdr_*`.
5. If the old status hook (`herdr-app-*` / `herdr-app-status` entries) is installed, remove those
   entries from Swarm.json so status is not reported twice.

## 1b. The status hook (alternative, no extensions)

1. Copy `hooks/herdr-app-bridge.py` to `<MUX_HOME>/Hooks/herdr-app-bridge.py` (create `Hooks/`).
2. Back up `Configs/Swarm.json`. Append the entry from `hooks/swarm-hooks.json` to the top-level
   `hooks` array (skip it if an entry with that `id` exists), replacing `python3` with the user's
   Python and `<MUX_HOME>` with the absolute path (forward slashes are fine on Windows).
   Older Mux versions without `args` support: use `"command": "python3 -u <path>"` instead.
3. If an older `herdr-bridge*` hook (for the Herdr TUI) exists, ask before removing it.

Both report nothing unless Mux runs inside a Herdr terminal (`HC_TERMINAL_ID` set), so they are
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

1. The user restarts Mux (or `/qc` then `/resume`; extensions also reload with `/refresh`) **inside a
   Herdr pane** and accepts the "enable hooks" prompt if one appears.
2. Extension: `/extensions` lists `herdr` as running; `/herdr` prints the Herdr terminals; the footer
   shows `herdr N`; `/herdr panel` docks the agents panel.
3. `hc get <address> --json` for that pane shows `status.state` = `idle` and title `mux: <agent>`.
   One message: `working` then `done`. In plan mode an `ask_user` prompt shows `blocked`
   (kind `question`). With `/sub`, a delegation shows a child record under `records` while it runs.
4. Debugging: set `MUX_HERDR_APP_DEBUG=1` and read `<tmp>/mux-herdr-app-hook.log`; `/extensions`
   shows the extension's last stderr lines.

Do not test by sending text into the user's own live Mux pane (`hc send` types into their session).
Start a separate Mux in its own Herdr terminal for tests.

## 5. Undo

- Extension: remove `"herdr"` from `trusted` (and `dirs` / `unsandboxed` / agents' `mcpServers` if
  added), delete the copied folder, `/refresh`.
- Hook: restore the Swarm.json backup (or delete the entry) and `<MUX_HOME>/Hooks/herdr-app-bridge.py`.
- Herdr app: delete the copied mods, layouts, `programs.json` entry, key bindings and templates.

## Rules

- Do not modify Mux source or Herdr's shipped mods and layouts (use `mod.clone` / `layout.clone`).
- This repo needs no secrets; never add any.
- Leave the user's existing hooks, extensions, keys, layouts and themes untouched unless they say otherwise.
