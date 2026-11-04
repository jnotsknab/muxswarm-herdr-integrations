// Mux follow: a read-only code view of the file a Mux agent is editing.
// Follow on: shows the file named by the `mux.file` label of a Mux terminal (props.terminal, else the
// most recently active Mux) and reloads it as it changes. Follow off: stays on the current file.
// props { file } (herdr_show) opens one file with Follow off.
import { View, div } from "gpui-kit";
import { h_flex, v_flex, Editor, EditorState } from "gpui-base";
import { props, terminals, readTextFile, watchFolder, theme, settings } from "herdr";

const LANG = { ts: "js", tsx: "js", mts: "js", cts: "js", jsx: "js", mjs: "js", toml: "yaml", jsonc: "json", cs: "csharp", py: "python", md: "markdown", ps1: "powershell", yml: "yaml" };

// The Mux to follow: props.terminal, else the live terminal whose mux.fileat is newest.
function muxTerminal() {
  const live = terminals().filter((k) => k.state === "live" && k.labels?.["mux.port"]);
  const want = props()?.terminal;
  if (want) return live.find((k) => k.address === want || k.name === want) ?? null;
  return live.sort((a, b) => Number(b.labels["mux.fileat"] || 0) - Number(a.labels["mux.fileat"] || 0))[0] ?? null;
}

export default class MuxFollow extends View {
  init(_p, cx) {
    this.follow = !props()?.file;
    this.file = props()?.file ?? null;
    this.code = null;
    this.error = null;
    this.gen = 0;
    if (this.file) this.load(this.file, cx);
  }

  load(path, cx) {
    const gen = ++this.gen;
    this.file = path;
    this.error = null;
    cx.spawn(async (cx) => {
      while (gen === this.gen) {
        let text = null;
        try { text = await readTextFile(path); } catch (e) { text = null; this.error = String(e); }
        if (gen !== this.gen) return;
        if (text === null) this.error = this.error ?? "Not found (or larger than 1 MiB)";
        else if (text.includes("\0")) this.error = "Binary file";
        else {
          this.error = null;
          if (this.code && this.codeFile === path) this.code.set_value(text);
          else {
            this.code?.release();
            const t = theme(), ext = (path.split(".").pop() || "txt").toLowerCase();
            this.code = EditorState.new({ language: LANG[ext] ?? ext, readonly: true, value: text,
              font_family: settings().font_family, font_size: 12,
              syntax: { keyword: t.ansi5, string: t.ansi2, comment: t.dim, function: t.ansi4, type: t.ansi3, number: t.ansi1, constant: t.ansi6 } });
            this.codeFile = path;
          }
        }
        cx.notify();
        await watchFolder(path.replace(/[\\/][^\\/]+$/, ""));
      }
    });
  }

  render(cx) {
    const t = theme();
    const mux = muxTerminal();
    const target = mux?.labels?.["mux.file"] || null;
    if (this.follow && target && target !== this.file) this.load(target, cx);
    const name = this.file ? this.file.split(/[\\/]/).slice(-2).join(" / ") : "";
    const who = mux ? `${mux.labels["mux.agent"] || "Mux"} · ${mux.address}` : "no Mux reporting";
    const toggle = h_flex().id("mf-follow").h(22).px(8).gap(6).items_center().rounded(5).cursor_pointer()
      .border(1).border_color(this.follow ? t.accent : t.border).bg(this.follow ? t.accent + "22" : t.surface)
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => { this.follow = !this.follow; cx.notify(); })
      .child(div().size(7).rounded(4).bg(this.follow ? t.accent : t.dim))
      .child(div().text_size(11).text_color(this.follow ? t.foreground : t.muted).child(this.follow ? "Following" : "Follow"));
    return v_flex().id("mf-root").size_full().bg(t.surface)
      .child(h_flex().h(30).flex_none().px(10).gap(10).items_center().border_b(1).border_color(t.border)
        .child(toggle)
        .child(div().flex_1().min_w(0).truncate().text_size(11.5).text_color(t.foreground).child(name || "Waiting for Mux to edit a file"))
        .child(div().flex_none().text_size(10.5).text_color(t.dim).child(who)))
      .child(this.error
        ? div().p(14).text_size(12).text_color(t.dim).child(this.error)
        : this.code ? Editor.new(this.code).flex_1().min_h(0)
        : div().p(14).text_size(12).text_color(t.dim).child(this.follow ? "Files Mux edits (edit/write tools) open here as it works." : "Turn Follow on to track Mux's edits."));
  }

  async close() { this.gen++; this.code?.release(); }
}
