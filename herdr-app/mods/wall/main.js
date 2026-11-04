// Wall: a grid of every agent as a LIVE terminal tile (type straight into any of them).
// One copy of this mod runs in the `wall-bar` strip above the grid and keeps the rows after it in
// the layout's `wall-body` in step with the agent list (layout.set), only when that list changes.
// Each tile is a header (this mod, props.tile) over a real terminal block. Mux sub-agents
// (delegations, background jobs) have no terminal: their tile shows the live transcript
// instead (props.rec). Note: a terminal shown in a tile is sized to that tile for every viewer.
import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, terminals, theme, run, settings, readTextFile, appHome, layout, shared, props } from "herdr";
import { allMuxRecords, recordIcon, openTail } from "./mux.js";

const LINES = 60;
const tail = (s) => (s ?? "").replace(/\r/g, "").split("\n").map((l) => l.replace(/\s+$/, "")).slice(-LINES).join("\n");
const safe = (s) => String(s).replace(/[^A-Za-z0-9]/g, "_");
const colsFor = (n) => (n <= 1 ? 1 : n <= 4 ? 2 : n <= 9 ? 3 : 4);

// What the wall shows: agents with a status, live hc children with a status, then Mux sub-agent records.
function wanted() {
  const top = agents().map((a) => ({ kind: "term", address: a.address }));
  const seen = new Set(top.map((a) => a.address));
  const subs = terminals()
    .filter((k) => k.parent && k.state === "live" && k.status && !seen.has(k.address))
    .map((k) => ({ kind: "term", address: k.address }));
  // Records of terminals that are on the wall (an agent or a shown child), each after the others.
  const onWall = new Set([...top, ...subs].map((x) => x.address));
  const recs = allMuxRecords(terminals().filter((k) => onWall.has(k.address))).map((r) => ({ kind: "rec", address: r.key, rec: r }));
  return [...top, ...subs, ...recs];
}

function tileNode(w) {
  const id = safe(w.address);
  const header = { id: `wall-h-${id}`, type: "block", size: { px: 26 }, content: { mod: "wall", props: { tile: w.address } } };
  const body = w.kind === "term"
    ? { id: `wall-b-${id}`, type: "block", content: { terminal: w.address } }
    : { id: `wall-b-${id}`, type: "block", content: { mod: "wall", props: { rec: w.address } } };
  return { id: `wall-t-${id}`, type: "column", radius: 10, border: { width: 1, color: "border" }, children: [header, body] };
}

function gridChildren(list) {
  if (!list.length) return [{ id: "wall-empty", type: "block", content: { mod: "wall", props: { empty: true } } }];
  const cols = colsFor(list.length);
  const rows = [];
  for (let i = 0; i < list.length; i += cols) {
    const row = list.slice(i, i + cols).map(tileNode);
    // Keep the last row's tiles the same width as the others.
    for (let k = row.length; k < cols && list.length > cols; k++) row.push({ id: `wall-pad-${i}-${k}`, type: "block", content: { mod: "wall", props: { pad: true } } });
    rows.push({ id: `wall-row-${i / cols}`, type: "row", gap: 8, children: row });
  }
  return rows;
}

// The ids and types of a subtree: what matters for "is the grid already right".
const shape = (nodes) => (nodes ?? []).map((n) => [n.id, n.type, shape(n.children)]);

function findNode(n, id) {
  if (!n || typeof n !== "object") return null;
  if (n.id === id) return n;
  for (const c of n.children ?? []) {
    const f = findNode(c, id);
    if (f) return f;
  }
  return null;
}

export default class Wall extends View {
  init(_p, cx) {
    const p = props() ?? {};
    this.mode = p.tile ? "tile" : p.rec ? "rec" : p.empty ? "empty" : p.pad ? "pad" : "bar";
    if (this.mode === "rec") {
      this.text = "";
      // Only Mux sub-agent tiles poll (their transcript file); terminals are live already.
      const pull = (cx) => {
        if (shared("layout") !== "wall") return;
        const r = allMuxRecords(terminals()).find((x) => x.key === props().rec);
        if (!r) return;
        cx.spawn(async (cx) => {
          try {
            const txt = await readTextFile(`${appHome()}/mux/tails/${r.parent.replace(/[^A-Za-z0-9_.-]/g, "_")}/${r.rid}.md`);
            const next = tail(txt ?? "");
            if (next !== this.text) { this.text = next; cx.notify(); }
          } catch {}
        });
      };
      pull(cx);
      cx.timer.every(1500, pull);
    }
  }

  // The bar copy: rebuild the tiles when they differ from what the layout holds. Everything in
  // `wall-body` after this bar is ours, and Herdr prunes a finished terminal's block on its own
  // (which can collapse a tile or a row), so rebuild from `wall-body` and heal whatever is there.
  sync(cx) {
    if (shared("layout") !== "wall" || this.pending) return;
    const tree = layout();
    const body = findNode(tree, "wall-body");
    if (!body) return;
    // Flat (bar, then rows): layout.set refuses arguments nested deeper than 16 levels.
    const want = [{ id: "wall-bar", type: "block", size: { px: 24 }, content: { mod: "wall" } }, ...gridChildren(wanted())];
    if (JSON.stringify(shape(body.children)) === JSON.stringify(shape(want))) return;
    body.children = want;
    this.pending = true;
    cx.spawn(async (cx) => {
      try {
        const r = await run("layout.set", { layout: tree });
        this.err = r && r.error ? String(r.error) : null;
      } catch (e) {
        this.err = String(e?.message ?? e);
      } finally {
        this.pending = false;
        cx.notify();
      }
    });
  }

  bar(t, cx) {
    this.sync(cx);
    const w = wanted();
    const live = w.filter((x) => x.kind === "term").length;
    const recs = w.length - live;
    return h_flex().id("wall-bar").size_full().px(4).gap(10).items_center().text_size(11.5)
      .child(div().font_semibold().text_color(t.foreground).child("Wall"))
      .child(div().text_color(t.dim).child(`${live} live terminal${live === 1 ? "" : "s"}${recs ? ` · ${recs} sub-agent${recs === 1 ? "" : "s"}` : ""}`))
      .child(div().flex_1())
      .when(Boolean(this.err), (el) => el.child(div().text_color(t.blocked).truncate().child(`layout: ${this.err}`)))
      .child(div().text_color(t.dim).child("click a tile to type in it · right-click to peek"));
  }

  header(t) {
    const addr = props().tile;
    const rec = allMuxRecords(terminals()).find((r) => r.key === addr);
    const k = rec ? null : terminals().find((x) => x.address === addr);
    const status = rec ? rec.status : k?.status === "error" ? "blocked" : k?.status;
    const title = rec ? rec.agent : (k?.name || k?.title || k?.program?.name || addr).replace(/^mux: /, "");
    const sub = rec ? `under ${rec.parent}` : addr;
    const p = k?.program;
    const color = t[status] ?? t.border;
    const blocked = status === "blocked";
    return h_flex().id(`wh-${safe(addr)}`).size_full().px(10).gap(8).items_center()
      .bg(blocked ? t.blocked + "33" : t.chrome).border_b(1).border_color(blocked ? t.blocked : t.border).cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .on_click(() => (rec ? openTail(rec) : run("pane.focus", { terminal: addr })))
      .on_mouse_down("right", (_e, cx) => {
        cx.stop_propagation();
        if (rec) openTail(rec);
        else run("terminal.peek", { terminal: addr });
      })
      .when(Boolean(rec), (el) => el.child(recordIcon(title, 13, t.accent)))
      .when(!rec && Boolean(p?.icon), (el) => el.child(p.tint ? svg(p.icon).size(13).text_color(p.color ?? t.foreground) : image(p.icon).w(14).h(14)))
      .child(div().flex_1().min_w(0).text_size(12).font_medium().text_color(t.foreground).whitespace_nowrap().overflow_hidden().text_ellipsis().child(title))
      .when(blocked, (el) => el.child(div().text_size(10.5).font_semibold().text_color(t.blocked).child("needs you")))
      .child(div().text_size(10.5).text_color(t.dim).child(sub))
      .child(status === "working"
        ? svg("mods/workspace-chrome/spinner.svg").size(12).text_color(color).spin(900)
        : div().size(8).rounded(4).bg(color).when(blocked, (el) => el.loop("opacity", { from: 0.3, to: 1, period: 1100 })));
  }

  recBody(t) {
    const key = props().rec;
    const r = allMuxRecords(terminals()).find((x) => x.key === key);
    return v_flex().id(`wr-${safe(key)}`).size_full().p(8).justify_end().overflow_hidden().bg(t.background).cursor_pointer()
      .on_click(() => r && openTail(r))
      .font_family(settings()?.font_family ?? "JetBrains Mono").text_size(10.5).line_height(1.3).text_color(t.terminal_foreground ?? t.foreground)
      .child(this.text || "\u2026");
  }

  render(cx) {
    const t = theme();
    if (this.mode === "tile") return this.header(t);
    if (this.mode === "rec") return this.recBody(t);
    if (this.mode === "pad") return div().size_full();
    if (this.mode === "empty") return div().size_full().p(20).text_size(13).text_color(t.dim).child("No agents reporting status yet.");
    return this.bar(t, cx);
  }
}
