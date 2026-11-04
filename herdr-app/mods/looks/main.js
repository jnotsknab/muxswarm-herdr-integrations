// Looks: one click switches Herdr's theme AND the Mux look (/theme herdr-<look>) together.
// A strip of swatches (graphite, ink, moss, paper). props.look marks the layout's own look.
// Mux is reached through the `herdr` Mux extension's control endpoint (see ask.js).
import { View, div } from "gpui-kit";
import { h_flex } from "gpui-base";
import { props, theme, themes, run, notify, layout } from "herdr";
import { muxTerminals, muxCall } from "./ask.js";

const LOOKS = [
  ["graphite", "Graphite"],
  ["ink", "Ink"],
  ["moss", "Moss"],
  ["paper", "Paper"],
];

export default class Looks extends View {
  init() {
    this.current = props()?.look ?? null;
    this.busy = false;
  }

  async apply(look, cx) {
    if (this.busy) return;
    this.busy = true;
    this.current = look;
    cx.notify();
    // A fixed theme on the shown layout's root (app.theme would set only one half of a light/dark
    // pair, so paper would stay hidden under a dark appearance). Personal layouts take it in full;
    // shipped ones accept look fields too.
    const tree = layout();
    if (tree && typeof tree === "object") {
      tree.theme = look;
      try { await run("layout.set", { layout: tree }); } catch { run("app.theme", { name: look }); }
    } else run("app.theme", { name: look });
    const muxes = muxTerminals();
    const errors = [];
    for (const m of muxes) {
      try {
        await muxCall(m.address, "/run", { action: "theme", arg: `herdr-${look}` });
      } catch (e) {
        errors.push(`${m.address}: ${e?.message ?? e}`);
      }
    }
    if (errors.length) notify({ title: "Looks", body: errors.join("\n"), level: "warning", timeout: 6000 });
    else notify({ title: `Look: ${look}`, body: muxes.length ? `Herdr + ${muxes.length} Mux` : "Herdr (no Mux reporting)", level: "success", timeout: 2500 });
    this.busy = false;
    cx.notify();
  }

  swatch(t, look, label) {
    const c = themes().find((x) => x.name === look)?.colors ?? {};
    const on = this.current === look;
    return h_flex().id(`look-${look}`).h(22).px(8).gap(6).items_center().flex_none().rounded(11).cursor_pointer()
      .border(1).border_color(on ? t.accent : t.border).bg(on ? t.accent + "22" : "#00000000")
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => this.apply(look, cx))
      .child(h_flex().gap(0).rounded(6).overflow_hidden().border(1).border_color(t.border)
        .child(div().w(9).h(12).bg(c.background ?? t.background))
        .child(div().w(9).h(12).bg(c.accent ?? t.accent))
        .child(div().w(9).h(12).bg(c.working ?? t.working)))
      .child(div().text_size(11.5).text_color(on ? t.foreground : t.muted).child(label));
  }

  render() {
    const t = theme();
    return h_flex().id("looks-root").size_full().px(10).gap(8).items_center()
      .child(div().text_size(11).font_semibold().text_color(t.dim).child("LOOK"))
      .children(LOOKS.map(([k, l]) => this.swatch(t, k, l)))
      .child(div().flex_1())
      .child(div().text_size(10.5).text_color(t.dim).child("switches Herdr and Mux together"));
  }
}
