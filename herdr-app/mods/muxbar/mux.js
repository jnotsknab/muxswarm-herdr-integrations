// Mux sub-agents for Herdr mods. Mods can't import from another mod's folder, so each mod that
// uses this keeps its own copy; keep the copies identical (muxbar/mux.js is the source; a repo test
// checks). Icons are referenced by path (mods/muxbar/icons), so they need the muxbar mod installed.
//
// The `herdr` Mux extension reports each running delegation / background job as an OSC 7501 child
// record on Mux's terminal (`terminals()[i].records`): id `d<flow>` or `j<job>`, title = agent name.
// It also writes a rolling transcript per record to <app home>/mux/tails/<terminal>/<id>.md.
import { svg } from "gpui-kit";
import { appHome, openOverlay } from "herdr";

/** Sub-agent records of one terminal as rows: { key, parent, rid, agent, msg, status }. */
export function muxRecords(t) {
  return Object.entries(t?.records ?? {}).map(([rid, r]) => ({
    key: `${t.address}/${rid}`,
    parent: t.address,
    rid,
    agent: r.title || rid,
    msg: r.msg ?? "",
    status: r.state === "error" ? "blocked" : r.state === "done" ? "idle" : r.state,
  }));
}

/** Every Mux sub-agent record across these terminals. */
export function allMuxRecords(terms) {
  return terms.filter((k) => k.state === "live").flatMap(muxRecords);
}

// One glyph per agent role (Mux agent names end in "Agent"). Self-drawn, theme-tinted.
const ROLE = [
  [/code|dev|impl/i, "code"], [/web|search|research|browse/i, "web"], [/memory|knowledge/i, "memory"],
  [/data|analy/i, "data"], [/doc/i, "docs"], [/review|risk|gate/i, "review"], [/pentest|security/i, "shield"],
  [/contact|mail|concierge|calendar/i, "mail"], [/bench|test/i, "bench"], [/trad/i, "chart"],
];
export function roleIcon(agent) {
  for (const [re, name] of ROLE) if (re.test(agent ?? "")) return `mods/muxbar/icons/${name}.svg`;
  return "mods/muxbar/icons/bot.svg";
}

export function recordIcon(agent, size, color) {
  return svg(roleIcon(agent)).size(size).flex_none().text_color(color);
}

/** Open the live transcript of one sub-agent record. */
export function openTail(rec) {
  const file = `${appHome()}/mux/tails/${rec.parent.replace(/[^A-Za-z0-9_.-]/g, "_")}/${rec.rid}.md`;
  openOverlay({ mod: "muxbar", kind: "window", key: `tail-${rec.key}`, width: 580, height: 500, props: { tail: { file, title: `${rec.agent} · ${rec.parent}` } } });
}
