// Wall: a monitor grid of every live agent's screen (the last lines of `hc read`), refreshed every few
// seconds while shown. Click a tile to focus that agent; right-click to peek (live, interactive).
// Mux sub-agents (delegations, background jobs) get a tile too, showing their live transcript.
import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, terminals, theme, run, hc, settings, readTextFile, appHome } from "herdr";
import { allMuxRecords, recordIcon, openTail } from "./mux.js";

const LINES = 40;
const tail = (s) => (s ?? "").replace(/\r/g, "").split("\n").map((l) => l.replace(/\s+$/, "")).filter((l, i, a) => l || i < a.length - 1).slice(-LINES).join("\n");

export default class Wall extends View {
  init(_p, cx) {
    this.screens = {};
    this.size = { width: 1200, height: 800 };
    const pull = (cx) =>
      cx.spawn(async (cx) => {
        for (const a of this.list()) {
          try {
            if (a.rec) {
              // A Mux sub-agent has no terminal: show the tail of its transcript instead.
              const txt = await readTextFile(`${appHome()}/mux/tails/${a.rec.parent.replace(/[^A-Za-z0-9_.-]/g, "_")}/${a.rec.rid}.md`);
              if (txt != null) this.screens[a.address] = tail(txt);
              continue;
            }
            const r = await hc(["read", a.address, "--lines", "0"]);
            if (r.code === 0) this.screens[a.address] = tail(r.stdout);
          } catch {}
        }
        cx.notify();
      });
    pull(cx);
    cx.timer.every(4000, pull);
  }

  list() {
    const subs = terminals().filter((k) => k.parent && k.state === "live" && k.status).map((k) => ({
      address: k.address, status: k.status === "error" ? "blocked" : k.status, title: k.name || k.program?.name || k.address, program: k.program, pane: null,
    }));
    const top = agents().map((a) => ({ address: a.address, status: a.status, title: (a.title || a.program?.name).replace(/^mux: /, ""), program: a.program, pane: a.pane, where: `${a.space_name} / ${a.tab_name}` }));
    const recs = allMuxRecords(terminals()).map((r) => ({
      address: r.key, status: r.status, title: r.agent, sub: `under ${r.parent}`, rec: r, pane: null,
    }));
    return [...top, ...subs.filter((s) => !top.some((x) => x.address === s.address)), ...recs];
  }

  tile(t, a, w, h) {
    const color = t[a.status] ?? t.border;
    const p = a.program;
    return v_flex()
      .id(`tile-${a.address}`)
      .w(w)
      .h(h)
      .rounded(10)
      .overflow_hidden()
      .bg(t.background)
      .border(a.status === "blocked" || a.status === "working" ? 1.5 : 1)
      .border_color(a.status === "blocked" || a.status === "working" ? color : t.border)
      .cursor_pointer()
      .hover((s) => s.border_color(t.accent))
      .on_click(() => (a.rec ? openTail(a.rec) : a.pane ? run("pane.focus", { pane: a.pane }) : run("terminal.peek", { terminal: a.address })))
      .on_mouse_down("right", (_e, cx) => {
        cx.stop_propagation();
        if (a.rec) openTail(a.rec);
        else run("terminal.peek", { terminal: a.address });
      })
      .child(
        h_flex().h(28).flex_none().px(10).gap(8).items_center().bg(t.chrome).border_b(1).border_color(t.border)
          .when(Boolean(a.rec), (el) => el.child(recordIcon(a.title, 13, t.accent)))
          .when(!a.rec && Boolean(p?.icon), (el) => el.child(p.tint ? svg(p.icon).size(13).text_color(p.color ?? t.foreground) : image(p.icon).w(14).h(14)))
          .child(div().flex_1().min_w(0).text_size(12).font_medium().text_color(t.foreground).whitespace_nowrap().overflow_hidden().text_ellipsis().child(a.title))
          .child(div().text_size(10.5).text_color(t.dim).child(a.rec ? a.sub : a.address))
          .child(a.status === "working"
            ? svg("mods/workspace-chrome/spinner.svg").size(12).text_color(color).spin(900)
            : div().size(8).rounded(4).bg(color).when(a.status === "blocked", (el) => el.loop("opacity", { from: 0.3, to: 1, period: 1100 }))),
      )
      .child(
        v_flex().flex_1().min_h(0).p(8).justify_end().overflow_hidden().font_family(settings()?.font_family ?? "JetBrains Mono").text_size(10.5).line_height(1.3).text_color(t.terminal_foreground ?? t.foreground)
          .child(this.screens[a.address] ?? "\u2026"),
      );
  }

  render() {
    const t = theme();
    const list = this.list();
    const n = Math.max(1, list.length);
    const cols = Math.max(1, Math.min(n, Math.round(Math.sqrt(n * (this.size.width / Math.max(1, this.size.height)) / 1.4)) || 1));
    const rows = Math.ceil(n / cols);
    const gap = 10;
    const w = Math.max(220, (this.size.width - 20 - gap * (cols - 1)) / cols);
    const h = Math.max(160, (this.size.height - 20 - gap * (rows - 1)) / rows);
    return div()
      .id("wall-root")
      .size_full()
      .bg(t.canvas)
      .on_size_change((size, cx) => {
        this.size = size;
        cx.notify();
      })
      .child(
        div().id("wall-scroll").size_full().p(10).overflow_y_scrollbar()
          .when(list.length === 0, (el) => el.child(div().p(20).text_size(13).text_color(t.dim).child("No agents reporting status yet.")))
          .child(h_flex().flex_wrap().gap(gap).children(list.map((a) => this.tile(t, a, w, h)))),
      );
  }
}
