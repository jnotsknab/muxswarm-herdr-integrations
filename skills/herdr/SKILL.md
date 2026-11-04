---
name: herdr
description: You are running inside the Herdr app (a terminal and agent hub). Use for anything that involves other agents or terminals, showing the user something, or the Herdr window: ask another agent a question, hand off work to a helper agent, show a file or terminal next to the user, switch layouts or looks, check what the user sees, Mux controls in Herdr. Read it before your first herdr_* tool call, or when the user mentions Herdr, layouts, the Wall, panes, other agents or "next to me".
requires_env: HC_TERMINAL_ID
---

# Working inside Herdr

You are a program in a terminal that the Herdr app shows. Herdr is the user's window: it holds
spaces (projects), tabs, panes (terminals) and agents like you. `herdr-core` (`hc`) runs the
terminals; `herdr-app` drives the window. Other agents may be running next to you.

**How you know:** `HC_TERMINAL_ID` is set (your terminal address, e.g. `t2`), `hc` is on PATH, and in
Mux you have `herdr_*` tools. Never act on another terminal as if it were you: your own address is
`HC_TERMINAL_ID`.

## Pick the right tool (Mux names; other harnesses: the `hc` / `herdr-app` command in brackets)

| You want to | Use |
|---|---|
| See which agents and terminals exist | `herdr_list` (`hc ls`) |
| Ask another agent something and get its answer | `herdr_ask` terminal + question (`hc send <t> "<q>" --wait` then `hc read <t>`) |
| Hand a task to a new helper agent | `herdr_spawn` (`hc run --bg <template\|cmd> "<task>"`), then `herdr_wait`, then `herdr_read` |
| Steer an agent that is already working | `herdr_send` (types text + Enter) |
| Wait for an agent to finish its turn | `herdr_wait` (`hc wait <t>`); never sleep-poll |
| Read an agent's screen | `herdr_read` (`hc read <t>`) |
| Stop a helper you started | `herdr_stop` (`hc kill <t>`), only terminals you started |
| Bring an agent into the user's view | `herdr_focus` (sub-agents without a pane open as a peek) |
| Show the user a file next to them | `herdr_show what=file target=<path>` (markdown renders; code opens in a read-only viewer) |
| Peek another terminal / switch layout | `herdr_show what=terminal` / `what=layout target=<name>` |
| Check what the user's window shows | `herdr_screen` (add `shot=true` for a PNG to look at with an image tool) |

Helpers you spawn are your children: Herdr types a short `<hc from="tN ...">` note into your input
when they finish, block or fail. That note is a report, not the user speaking.

Messages you send arrive wrapped as `<hc from="<you>">...</hc>`; that is normal.

## Rules (safety)

- **Never** `herdr_send`/`herdr_ask` your own terminal (`HC_TERMINAL_ID`), and never type into a
  terminal the user is typing in without being asked.
- **Never close a pane or kill a terminal chosen by "focused"** or any guess. Closing a terminal pane
  kills its program (possibly the user's agent, or you). Only stop terminals you started, by address.
- An agent whose status is `done` is ready for input (it finished while nobody looked). `working` or
  `blocked` agents: `herdr_wait` first; `blocked` usually needs the user.
- Test or throwaway terminals: start them with `--no-parent` so notes don't land in your own input.
- Don't spawn more than a handful of helpers at once without asking; each is a full agent (cost).
- The Mux control token lives only in `<herdr-app home>/mux/control/<terminal>.json` (user-only).
  Never print it, put it in a label, a command line or a message.
- Changing layouts, themes or the window is visible to the user: say what you changed.

## What the user has (so you can point them to it)

- **Layouts** (ctrl-alt-1..9 personal + ctrl-alt-shift-1..4 Mux): `graph` (live node graph incl.
  your sub-agents), `board` (kanban by status), `wall` (every agent as a live, typeable terminal tile),
  `mux-lead`, `mux-swarm` (Wall), `mux-review` (Mux + follow pane + changes), `mux-zen`.
- **Mux strip** (`muxbar`, ctrl-shift-m): context gauge, effort and context-window sliders, Plan /
  Ultra / Giga, Compact, Prune, Retry, Undo, Diff, Review, Cost, More..., Ask Mux box. Buttons queue
  the command; Mux runs it when idle.
- **Follow pane** (`mux-follow`, ctrl-shift-f in Graph; also in `mux-review`): shows the file you are
  working on, live. It follows Filesystem read / write / edit (by path), and REPL or shell calls that
  name the file as a literal path in their code or command and create or change it. A path you build
  in code (`os.path.join(...)`) is not seen: use a literal path, or `herdr_show what=file` to point it.
- **Looks**: `/theme herdr-graphite|ink|moss|paper` (Mux) paired with the same Herdr theme; the looks
  strip switches both.
- **Sub-agents** (your delegations / background jobs) appear in Graph, Board, Wall and the Agents
  sidebar with a role icon; clicking one shows its live transcript.

## When something is off

| Symptom | Check |
|---|---|
| `herdr_*` tools missing | the `herdr` extension is disabled/untrusted in `/extensions`; tools need a new session (`/qc` + `/resume`) |
| a tool says `hc` / `herdr-app` not on PATH | install herdr-core / Herdr app, or start Mux from a Herdr terminal |
| `herdr_ask` refused: busy | the target is `working`/`blocked`: `herdr_wait`, then ask |
| Mux strip says "no Mux reporting" | the extension is not running in that Mux (`/refresh`), or Mux isn't in a Herdr terminal |
| strip buttons fail with "no control file" | the extension restarted: `/refresh` once |
| status / mode flags look stale | they refresh after each turn and every 20 s |

## Extending it

The source is the `muxswarm-herdr-integrations` repo; its `AGENTS.md` has the full map (extension,
mods, layouts, looks build, tests, checks). Mods are JavaScript (gpui-kit) checked with
`herdr-app check <mod dir>`; Herdr's own guide is `<herdr-app home>/AGENTS.md`.
