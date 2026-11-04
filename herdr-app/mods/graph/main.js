// Graph: every machine, space, tab, terminal and sub-agent as a live node graph, left to right.
// Nodes are colored by agent status (working spins, needs-you pulses, done is green); edges are
// native bezier paths. Click a node to go there; right-click a terminal or sub-agent to peek.

import { View, div, svg, image, PathBuilder } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { machines, spaces, panes, terminals, focused, theme, run } from "herdr";
import { recordIcon, openTail } from "./mux.js";

const COL = 232; // column pitch
const NODE_W = 196;
const NODE_H = 46;
const ROW = 56; // row pitch for leaves
const PAD = 16;
const RANK = { blocked: 4, error: 4, done: 3, working: 2, idle: 1 };

const urgent = (list) => list.reduce((a, s) => ((RANK[s] ?? 0) > (RANK[a] ?? 0) ? s : a), null);
const one = (s, n = 64) => {
  const v = String(s ?? "").replace(/\s+/g, " ").trim();
  return v.length > n ? v.slice(0, n - 1) + "\u2026" : v;
};
const ago = (ms) => {
  if (!ms) return "";
  const m = Math.floor((Date.now() - ms) / 60000);
  return m < 1 ? "<1m" : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`;
};

// The world as a tree: machine > space > tab > terminal > sub-agents (hc children).
function buildTree() {
  const terms = terminals();
  const byAddr = new Map(terms.map((t) => [t.address, t]));
  const allPanes = panes();
  const kids = (addr, depth) =>
    terms
      .filter((k) => k.parent === addr && k.state === "live")
      .map((k) => ({
        kind: "sub",
        id: `k-${k.address}`,
        address: k.address,
        label: k.name || k.title || k.program?.name || k.address,
        sub: one(k.report?.msg) || k.status || k.address,
        status: k.status === "error" ? "blocked" : k.status,
        program: k.program,
        children: depth < 4 ? kids(k.address, depth + 1) : [],
      }));
  // A program's own sub-agents, reported as OSC 7501 child records (e.g. Mux delegations).
  const recs = (t) =>
    Object.entries(t?.records ?? {}).map(([rid, r]) => ({
      kind: "sub",
      id: `r-${t.address}-${rid}`,
      address: t.address,
      rec: { key: `${t.address}/${rid}`, parent: t.address, rid, agent: r.title || rid },
      label: r.title || rid,
      sub: one(r.msg) || r.state,
      status: r.state === "error" ? "blocked" : r.state,
      program: t.program,
      children: [],
    }));

  const sp = spaces();
  const roots = machines().map((m) => {
    const mine = sp.filter((s) => (s.machine ?? null) === (m.name ?? null));
    const node = {
      kind: "machine",
      id: `m-${m.name ?? "here"}`,
      label: m.name ?? "This computer",
      sub: m.layout === "ready" ? `${mine.length} space${mine.length === 1 ? "" : "s"}` : m.layout,
      offline: m.layout === "unavailable",
      children: mine.map((s) => ({
        kind: "space",
        id: `s-${s.id}`,
        space: s.id,
        label: s.name,
        sub: s.branch ? `\u2387 ${s.branch}` : s.folder || "~",
        status: s.status,
        active: s.active,
        children: s.tabs.map((tb) => ({
          kind: "tab",
          id: `t-${tb.id}`,
          tab: tb.id,
          label: tb.named ? tb.name : `Tab ${tb.name}`,
          sub: tb.working_since ? `working \u00b7 ${ago(tb.working_since)}` : `${tb.panes} pane${tb.panes === 1 ? "" : "s"}`,
          status: tb.status,
          active: s.active && tb.active,
          children: allPanes
            .filter((p) => p.tab === tb.id)
            .map((p) => {
              const t = p.terminal ? byAddr.get(p.terminal) : null;
              return {
                kind: "pane",
                id: `p-${p.pane}`,
                pane: p.pane,
                address: p.terminal,
                label: one(p.title, 40) || p.program?.name || p.mod || "pane",
                sub: one(t?.report?.msg) || p.status || (p.cwd ? p.cwd.split(/[\\/]/).pop() || p.cwd : p.program?.name ?? ""),
                status: p.status,
                program: p.program,
                children: p.terminal ? [...recs(t), ...kids(p.terminal, 0)] : [],
              };
            }),
        })),
      })),
    };
    node.status = urgent(mine.map((s) => s.status));
    if (!node.children.length && !node.offline) node.sub = "no spaces \u00b7 click +";
    return node;
  });
  const agentCount = terms.filter((t) => t.state === "live" && t.status).length;
  return {
    kind: "hub",
    id: "hub",
    label: "Herdr",
    sub: `${roots.length} machine${roots.length === 1 ? "" : "s"} \u00b7 ${agentCount} agent${agentCount === 1 ? "" : "s"}`,
    status: urgent(roots.map((r) => r.status)),
    children: roots,
  };
}

// Tidy left-to-right layout: leaves stack down, parents center on their children.
function place(roots) {
  // roots: the hub; machines hang off it.
  const nodes = [];
  const edges = [];
  let row = 0;
  const walk = (n, depth) => {
    n.x = PAD + depth * COL;
    if (n.children.length === 0) {
      n.y = PAD + row * ROW;
      row++;
    } else {
      n.children.forEach((c) => walk(c, depth + 1));
      const first = n.children[0].y;
      const last = n.children[n.children.length - 1].y;
      n.y = (first + last) / 2;
    }
    nodes.push(n);
    n.children.forEach((c) => edges.push({ from: n, to: c }));
  };
  walk(roots, 0);
  const depth = Math.max(0, ...nodes.map((n) => (n.x - PAD) / COL));
  return { nodes, edges, width: PAD * 2 + depth * COL + NODE_W, height: PAD * 2 + Math.max(1, row) * ROW };
}

export default class Graph extends View {
  init(_props, cx) {
    this.size = { width: 0, height: 0 };
    // Only for the "working · 3m" timers; everything else re-renders on live data.
    cx.timer.every(30000, (cx) => cx.notify());
  }

  // Native bezier edges, one path per color so status edges glow in their color.
  edges(t, edges, width, height) {
    const groups = new Map();
    for (const e of edges) {
      const s = e.to.status;
      const color = s === "working" || s === "blocked" || s === "done" ? t[s] : t.border;
      const dashed = e.to.kind === "sub";
      const key = `${color}|${dashed}`;
      if (!groups.has(key)) groups.set(key, { color, dashed, list: [] });
      groups.get(key).list.push(e);
    }
    return [...groups.values()].map((g) => {
      let b = PathBuilder.stroke(g.color === t.border ? 1.2 : 1.8);
      if (g.dashed) b = b.dash_array([4, 3]);
      for (const { from, to } of g.list) {
        const x1 = from.x + NODE_W;
        const y1 = from.y + NODE_H / 2;
        const x2 = to.x;
        const y2 = to.y + NODE_H / 2;
        const mid = (x2 - x1) / 2;
        b = b.move_to(x1, y1).cubic_bezier_to(x2, y2, x1 + mid, y1, x2 - mid, y2);
      }
      return window.paint_path(b.build(), g.color).absolute().top(0).left(0).w(width).h(height);
    });
  }

  badge(t, n) {
    const s = n.status;
    if (s === "working") return svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900);
    if (s === "blocked")
      return div().size(8).flex_none().rounded(4).bg(t.blocked).loop("opacity", { from: 0.3, to: 1, period: 1100 });
    if (s === "done") return svg("mods/workspace-chrome/check.svg").size(12).flex_none().text_color(t.done);
    if (s === "idle") return div().size(6).flex_none().rounded(3).bg(t.idle);
    return null;
  }

  icon(t, n) {
    const box = (el, bg) => div().size(26).flex_none().rounded(7).bg(bg).flex().items_center().justify_center().child(el);
    const p = n.program;
    if (n.kind === "hub") return box(image("mux/herdr.png").w(18).h(18), t.raised);
    if (n.rec) return box(recordIcon(n.rec.agent, 14, t[n.status] ?? t.muted), t.raised);
    if (p?.icon) {
      const glyph = p.tint ? svg(p.icon).size(15).text_color(p.color ?? t.foreground) : image(p.icon).w(p.tile ? 18 : 26).h(p.tile ? 18 : 26);
      return p.tile ? box(glyph, p.tile) : p.tint ? box(glyph, t.raised) : glyph.flex_none().rounded(7);
    }
    const name = { hub: "layers", machine: n.label === "This computer" ? "monitor" : "server", space: "folder", tab: "layers", pane: "terminal", sub: "square" }[n.kind];
    return box(svg(`mods/workspace-chrome/${name}.svg`).size(14).text_color(n.active ? t.accent : t.muted), t.raised);
  }

  go(n) {
    if (n.kind === "machine" && !n.children.length && !n.offline)
      run("space.new", { machine: n.label === "This computer" ? "" : n.label });
    else if (n.kind === "space") run("space.select", { id: n.space });
    else if (n.kind === "tab") run("tab.select", { id: n.tab });
    else if (n.kind === "pane") run("pane.focus", { pane: n.pane });
    else if (n.rec) openTail(n.rec);
    else if (n.kind === "sub") run("terminal.peek", { terminal: n.address });
  }

  node(t, n, focus) {
    const isFocus = n.kind === "pane" && n.pane === focus?.pane;
    const tone = n.status === "blocked" ? t.blocked : n.status === "working" ? t.working : null;
    const border = isFocus ? t.accent : tone ?? (n.active ? t.input : t.border);
    const badge = this.badge(t, n);
    return h_flex()
      .id(n.id)
      .absolute()
      .left(n.x)
      .top(n.y)
      .transition("top", { duration: 220, easing: "ease-out" })
      .w(NODE_W)
      .h(NODE_H)
      .px(9)
      .gap(8)
      .items_center()
      .rounded(10)
      .bg(isFocus ? t.selected : t.surface)
      .border(isFocus || tone ? 1.5 : 1)
      .border_color(border)
      .when(Boolean(n.offline), (el) => el.opacity(0.5))
      .hover((s) => s.bg(t.hover))
      .on_click(() => this.go(n))
      .when(Boolean(n.address), (el) =>
        el.on_mouse_down("right", (_e, cx) => {
          cx.stop_propagation();
          run("terminal.peek", { terminal: n.address });
        }),
      )
      .tooltip(n.kind === "pane" || n.kind === "sub" ? `${n.label} \u00b7 click: go \u00b7 right-click: peek` : n.label)
      .child(this.icon(t, n))
      .child(
        v_flex()
          .flex_1()
          .min_w(0)
          .gap(1)
          .child(div().text_size(12.5).font_medium().text_color(t.foreground).whitespace_nowrap().overflow_hidden().text_ellipsis().child(n.label))
          .child(
            div()
              .text_size(11)
              .text_color(n.status === "blocked" ? t.blocked : t.muted)
              .whitespace_nowrap()
              .overflow_hidden()
              .text_ellipsis()
              .child(n.status === "blocked" && n.kind !== "pane" && n.kind !== "sub" ? "needs you" : n.sub || ""),
          ),
      )
      .when(Boolean(badge), (el) => el.child(badge));
  }

  legend(t, nodes) {
    const count = (s) => nodes.filter((n) => (n.kind === "pane" || n.kind === "sub") && n.status === s).length;
    const chip = (label, color, n) =>
      h_flex().gap(5).items_center().child(div().size(7).rounded(4).bg(color)).child(div().text_color(n ? t.foreground : t.dim).child(`${n} ${label}`));
    return h_flex()
      .h(30)
      .flex_none()
      .px(14)
      .gap(16)
      .items_center()
      .border_b(1)
      .border_color(t.border)
      .text_size(11.5)
      .child(div().font_medium().text_color(t.muted).child("Graph"))
      .child(div().flex_1())
      .child(chip("needs you", t.blocked, count("blocked")))
      .child(chip("working", t.working, count("working")))
      .child(chip("done", t.done, count("done")))
      .child(chip("idle", t.idle, count("idle")));
  }

  render() {
    const t = theme();
    const { nodes, edges, width, height } = place(buildTree());
    const focus = focused();
    return v_flex()
      .id("graph-root")
      .size_full()
      .bg(t.canvas)
      .child(this.legend(t, nodes))
      .child(
        div()
          .id("graph-scroll")
          .flex_1()
          .min_h(0)
          .overflow_scrollbar()
          .on_size_change((size, cx) => {
            this.size = size;
            cx.notify();
          })
          .child(
            div()
              .relative()
              .w(Math.max(width, this.size.width))
              .h(Math.max(height, this.size.height))
              .pl(Math.max(0, (this.size.width - width) / 2))
              .pt(Math.max(0, (this.size.height - height) / 2))
              .child(div().relative().w(width).h(height)
              .children(edges.length ? this.edges(t, edges, width, height) : [])
              .children(nodes.map((n) => this.node(t, n, focus)))),
          ),
      );
  }
}
