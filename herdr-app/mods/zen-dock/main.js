// Zen dock: a floating drawer on the left edge. Collapsed, only a status dot per agent peeks out;
// hovered, it slides open with names and messages. Click an agent to show it full screen.
import { View, div, svg, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, terminals, focused, theme, run, placement } from "herdr";

export default class ZenDock extends View {
  render() {
    const t = theme();
    const list = agents();
    const reports = new Map(terminals().map((k) => [k.address, k.report?.msg ?? ""]));
    const shown = focused()?.agent;
    const right = placement()?.edge === "right";
    const row = (a) => {
      const color = t[a.status] ?? t.dim;
      const dot = a.status === "working"
        ? svg("mods/workspace-chrome/spinner.svg").size(12).text_color(color).spin(900)
        : div().size(9).rounded(5).bg(color).when(a.status === "blocked", (el) => el.loop("opacity", { from: 0.3, to: 1, period: 1100 }));
      const p = a.program;
      const text = v_flex().w(210).min_w(0)
        .child(div().text_size(12.5).font_medium().text_color(a.address === shown ? t.accent : t.foreground).whitespace_nowrap().overflow_hidden().text_ellipsis().child((a.title || p?.name || a.address).replace(/^mux: /, "")))
        .child(div().text_size(11).text_color(t.muted).whitespace_nowrap().overflow_hidden().text_ellipsis().child(reports.get(a.address) || `${a.space_name} / ${a.tab_name}`));
      const ic = p?.icon ? (p.tint ? svg(p.icon).size(14).text_color(p.color ?? t.foreground) : image(p.icon).w(16).h(16)) : div().size(16);
      const lead = h_flex().w(28).flex_none().justify_center().child(dot);
      return h_flex()
        .id(`zd-${a.address}`)
        .h(40)
        .px(4)
        .gap(8)
        .items_center()
        .rounded(8)
        .when(a.address === shown, (el) => el.bg(t.selected))
        .hover((s) => s.bg(t.hover))
        .on_click(() => run("agent.focus", { terminal: a.address }))
        .children(right ? [text, ic, lead] : [lead, ic, text]);
    };
    return v_flex()
      .id("zd-root")
      .py(6)
      .px(2)
      .gap(2)
      .when(list.length === 0, (el) => el.child(h_flex().h(40).px(4).gap(8).items_center().child(h_flex().w(28).justify_center().child(div().size(9).rounded(5).bg(t.idle))).child(div().w(240).text_size(12).text_color(t.dim).child("No agents yet"))))
      .children(list.map(row));
  }
}
