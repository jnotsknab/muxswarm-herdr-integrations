// Board: every agent (and hc sub-agent) as a card in a status column. Click: focus; right-click: peek.
import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, terminals, spaces, theme, run, setAgentOrder } from "herdr";
import { recordIcon, openTail } from "./mux.js";

const COLS = [
  { id: "blocked", empty: "Nothing needs you", label: "Needs you" },
  { id: "working", empty: "No one is working", label: "Working" },
  { id: "done", empty: "Nothing finished unseen", label: "Done" },
  { id: "idle", empty: "No idle agents", label: "Idle" },
];
const since = (ms) => {
  if (!ms) return "";
  const m = Math.floor((Date.now() - ms) / 60000);
  return m < 1 ? "<1m" : m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
};

export default class Board extends View {
  init(_p, cx) {
    cx.timer.every(30000, (cx) => cx.notify());
  }

  cards() {
    const terms = new Map(terminals().map((t) => [t.address, t]));
    const tabs = new Map(spaces().flatMap((s) => s.tabs.map((tb) => [tb.id, { ...tb, space: s.name, machine: s.machine }])));
    const list = agents().map((a) => {
      const t = terms.get(a.address);
      const tab = tabs.get(a.tab);
      return {
        address: a.address, pane: a.pane, status: a.status, program: a.program, pinned: a.pinned,
        title: (a.title || a.program?.name || a.address).replace(/^mux: /, ""),
        msg: t?.report?.msg ?? "", where: `${tab?.machine ? tab.machine + " \u00b7 " : ""}${a.space_name} / ${a.tab_name}`,
        since: t?.status_ms, sub: false,
      };
    });
    for (const t of terminals()) {
      for (const [rid, r] of Object.entries(t.records ?? {})) {
        list.push({
          address: `${t.address}#${rid}`, peek: t.address, status: r.state === "error" ? "blocked" : r.state, program: t.program,
          rec: { key: `${t.address}/${rid}`, parent: t.address, rid, agent: r.title || rid },
          title: r.title || rid, msg: r.msg ?? "", where: `inside ${terms.get(t.address)?.name || t.address}`, since: t.status_ms, sub: true,
        });
      }
    }
    for (const k of terminals()) {
      if (!k.parent || k.state !== "live" || !k.status || list.some((c) => c.address === k.address)) continue;
      list.push({
        address: k.address, status: k.status === "error" ? "blocked" : k.status, program: k.program,
        title: k.name || k.program?.name || k.address, msg: k.report?.msg ?? "", where: `under ${k.parent}`, since: k.status_ms, sub: true,
      });
    }
    return list;
  }

  card(t, c) {
    const color = t[c.status] ?? t.dim;
    const p = c.program;
    const icon = c.rec ? recordIcon(c.title, 15, t.accent)
      : p?.icon ? (p.tint ? svg(p.icon).size(16).text_color(p.color ?? t.foreground) : image(p.icon).w(18).h(18)) : null;
    return v_flex()
      .id(`card-${c.address}`)
      .p(10)
      .gap(6)
      .rounded(10)
      .bg(t.surface)
      .border(1)
      .border_color(c.status === "blocked" ? t.blocked : t.border)
      .border_l(3)
      .cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .on_click(() => (c.rec ? openTail(c.rec) : c.pane ? run("pane.focus", { pane: c.pane }) : run("terminal.peek", { terminal: c.peek ?? c.address })))
      .on_mouse_down("right", (_e, cx) => {
        cx.stop_propagation();
        run("terminal.peek", { terminal: c.peek ?? c.address });
      })
      .child(
        h_flex().gap(8).items_center()
          .child(div().size(24).flex_none().rounded(6).bg(c.rec ? t.raised : p?.tile ?? t.raised).flex().items_center().justify_center().when(Boolean(icon), (el) => el.child(icon)))
          .child(div().flex_1().min_w(0).text_size(13).font_semibold().text_color(t.foreground).whitespace_nowrap().overflow_hidden().text_ellipsis().child(c.title))
          .when(c.status === "working", (el) => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).text_color(color).spin(900)))
          .when(c.status === "blocked", (el) => el.child(div().size(8).rounded(4).bg(color).loop("opacity", { from: 0.3, to: 1, period: 1100 }))),
      )
      .when(Boolean(c.msg), (el) => el.child(div().text_size(12).text_color(t.muted).line_height(1.35).child(c.msg)))
      .child(
        h_flex().gap(6).text_size(10.5).text_color(t.dim)
          .child(div().flex_1().whitespace_nowrap().overflow_hidden().text_ellipsis().child(c.where))
          .child(div().flex_none().child(`${c.address}${c.since ? " \u00b7 " + since(c.since) : ""}`)),
      );
  }

  render() {
    const t = theme();
    const cards = this.cards();
    setAgentOrder(COLS.flatMap((col) => cards.filter((c) => c.status === col.id && !c.sub).map((c) => c.address)));
    return h_flex()
      .id("board-root")
      .size_full()
      .p(10)
      .gap(10)
      .bg(t.canvas)
      .children(
        COLS.map((col) => {
          const mine = cards.filter((c) => c.status === col.id).sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
          return v_flex()
            .id(`col-${col.id}`)
            .flex_1()
            .min_w(0)
            .h_full()
            .rounded(12)
            .bg(t.chrome)
            .border(1)
            .border_color(t.border)
            .child(
              h_flex().h(36).flex_none().px(12).gap(8).items_center()
                .child(div().size(8).rounded(4).bg(t[col.id] ?? t.dim))
                .child(div().text_size(12).font_semibold().text_color(t.foreground).child(col.label))
                .child(div().text_size(12).text_color(t.dim).child(String(mine.length))),
            )
            .child(
              v_flex().id(`col-list-${col.id}`).flex_1().min_h(0).px(8).pb(8).gap(8).overflow_y_scrollbar()
                .when(mine.length === 0, (el) => el.child(div().mt(6).p(14).rounded(10).border(1).border_color(t.border).text_size(11.5).text_color(t.dim).text_center().child(col.empty)))
                .children(mine.map((c) => this.card(t, c))),
            );
        }),
      );
  }
}
