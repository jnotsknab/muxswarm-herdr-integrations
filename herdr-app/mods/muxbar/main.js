// Muxbar: native controls for a Mux session running in Herdr.
// Reads the `mux.*` labels the `herdr` Mux extension sets on its terminal (live, no polling) and
// sends actions to that extension's loopback endpoint (port + token are labels too). Mux queues
// commands and runs them when the session is idle (in its TUI, while the draft is empty).
// props: { terminal?: "t2" } pins one Mux; otherwise the Mux in the shown tab, else the most recent.
// Other mods ask Mux with askMux() from ./ask.js (same endpoint).
import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex, InputState, Input, Slider, SliderTrack, SliderIndicator, SliderThumb, SliderState, TextView } from "gpui-base";
import { props, terminals, panes, focused, theme, notify, run, openOverlay, closeOverlay, readTextFile, watchFolder } from "herdr";
import { muxTerminals, muxCall } from "./ask.js";
import { muxRecords, recordIcon, openTail } from "./mux.js";

const EFFORTS = ["low", "med", "high", "xhigh", "max"];
const WINDOWS = [64, 100, 128, 200, 256, 400, 500, 800, 1000]; // k tokens; the slider snaps to these
const PRUNE = [["all", "All"], ["dupes", "Duplicates"], ["tools", "Old tool output"], ["stale", "Stale"]];

function pick() {
  const all = muxTerminals();
  const want = props()?.terminal;
  if (want) return all.find((k) => k.address === want || k.name === want) ?? null;
  const tab = focused()?.tab;
  const here = new Set(panes().filter((p) => p.tab === tab).map((p) => p.terminal));
  return all.find((k) => here.has(k.address)) ?? all[0] ?? null;
}

const nearest = (list, v) => list.reduce((b, x) => (Math.abs(x - v) < Math.abs(b - v) ? x : b), list[0]);

export default class Muxbar extends View {
  init(_p, cx) {
    if (props()?.menu) return;
    if (props()?.tail) return this.initTail(cx);
    this.input = InputState.new({ placeholder: "Ask Mux… (Enter)" });
    this.input.on("submit", (_e, cx) => this.ask(cx));
    this.effort = SliderState.new({ min: 0, max: EFFORTS.length - 1, step: 1, value: 2 });
    this.effort.on("change", (_v, cx) => { this.dragEffort = true; cx.notify(); });
    this.effort.on("release", (v, cx) => { this.dragEffort = false; this.act("effort", EFFORTS[Math.round(v)], cx); });
    this.window = SliderState.new({ min: 0, max: WINDOWS.length - 1, step: 1, value: WINDOWS.length - 1 });
    this.window.on("change", (_v, cx) => { this.dragWindow = true; cx.notify(); });
    this.window.on("release", (v, cx) => { this.dragWindow = false; this.act("context", `${WINDOWS[Math.round(v)]}k`, cx); });
    this.busy = null;
    this.last = null;
  }

  // ---- a sub-agent's live transcript (opened by openTail from any mod) ----
  initTail(cx) {
    this.text = "";
    cx.spawn(async (cx) => {
      const file = props().tail.file;
      for (;;) {
        const t = await readTextFile(file);
        this.text = t ?? "*No transcript yet. It appears once the sub-agent writes output.*";
        cx.notify();
        await watchFolder(file.replace(/[\\/][^\\/]+$/, ""));
      }
    });
  }
  tail(t) {
    const p = props();
    const body = this.text.length > 8000 ? "…\n\n" + this.text.slice(-8000) : this.text;
    return v_flex().id("mt-root").size_full().bg(t.surface)
      .child(h_flex().h(34).flex_none().px(12).gap(8).items_center().border_b(1).border_color(t.border).bg(t.chrome)
        .child(recordIcon(p.tail.title, 14, t.accent))
        .child(div().flex_1().truncate().text_size(12.5).font_semibold().text_color(t.foreground).child(p.tail.title))
        .child(div().id("mt-close").px(8).h(22).rounded(5).flex().items_center().cursor_pointer().border(1).border_color(t.border).bg(t.raised).hover((s) => s.bg(t.hover).border_color(t.accent))
          .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
          .on_click(() => closeOverlay(p.overlay)).text_size(11.5).text_color(t.muted).child("Close")))
      .child(div().id("mt-body").flex_1().min_h(0).px(16).py(10).text_size(12.5).line_height(1.5).text_color(t.foreground).overflow_y_scrollbar()
        .child(TextView.markdown("mt-md", body).selectable(true).w_full()));
  }

  // ---- the "more" popup: every other Mux command that makes sense from a button ----
  menu(t) {
    const p = props();
    const item = (label, action, arg, hint) => h_flex().id(`mm-${action}-${arg ?? ""}`).h(28).px(10).gap(8).items_center().rounded(6)
      .cursor_pointer().hover((s) => s.bg(t.hover))
      .on_click(async () => { closeOverlay(p.overlay); try { await muxCall(p.terminal, "/run", { action, arg }); } catch (e) { notify({ title: "Mux", body: String(e.message ?? e), level: "error" }); } })
      .child(div().flex_1().text_size(12.5).text_color(t.foreground).child(label))
      .child(div().text_size(10.5).text_color(t.dim).child(hint ?? ""));
    const head = (s) => div().px(10).pt(8).pb(3).text_size(10.5).font_semibold().text_color(t.dim).child(s);
    return div().id("mm-root").size_full().bg(t.popover).overflow_y_scrollbar().child(v_flex().w_full().p(4)
      .child(head("PRUNE (no model call)"))
      .children(PRUNE.map(([k, l]) => item(l, "prune", k, `/prune ${k === "all" ? "" : k}`)))
      .child(head("SESSION"))
      .child(item("Handoff doc", "handoff", null, "/handoff"))
      .child(item("Tokens", "tokens", null, "/tokens"))
      .child(item("Cost by model", "costall", null, "/cost all"))
      .child(item("Status", "status", null, "/status"))
      .child(item("Doctor", "doctor", null, "/doctor"))
      .child(item("Limits", "limits", null, "/limits"))
      .child(item("Context: ask provider for max", "context", "max", "/context max"))
      .child(head("VIEW"))
      .child(item("Full / compact tool output", "verbose", null, "/verbose"))
      .child(item("Sub-agent output", "subagentview", null, "/subagentview"))
      .child(item("Daemon output", "daemonview", null, "/daemonview"))
      .child(item("Tools", "tools", null, "/tools"))
      .child(item("Skills", "skills", null, "/skills"))
      .child(item("Sessions", "sessions", null, "/sessions"))
      .child(item("Models", "model", null, "/model"))
      .child(item("Clear screen", "clear", null, "/clear"))
      .child(head("NEEDS A MUX ENGINE UPDATE"))
      .child(div().px(10).pb(6).text_size(11).text_color(t.dim).child("Auto-continue, compaction threshold, parallel agents (/maxp), insight level and /set are not available to extensions yet.")));
  }

  async act(action, arg, cx) {
    const m = pick();
    if (!m) return;
    this.busy = action;
    cx?.notify();
    try {
      const r = await muxCall(m.address, "/run", { action, arg });
      this.last = r.line;
    } catch (e) {
      notify({ title: "Mux", body: String(e.message ?? e), level: "error", timeout: 6000 });
    } finally {
      this.busy = null;
      cx?.notify();
    }
  }

  async ask(cx) {
    const text = this.input.value().trim();
    const m = pick();
    if (!text || !m) return;
    try {
      await muxCall(m.address, "/ask", { text });
      this.input.set_value("");
      this.last = "asked";
    } catch (e) {
      notify({ title: "Mux", body: String(e.message ?? e), level: "error" });
    }
    cx.notify();
  }

  btn(t, id, label, onClick, opts = {}) {
    const on = opts.on;
    return h_flex().id(`mb-${id}`).h(24).px(9).gap(5).items_center().flex_none().rounded(6).cursor_pointer()
      .border(1).border_color(on ? t.accent : t.border).bg(on ? t.accent + "26" : t.raised)
      .when(this.busy === id, (el) => el.opacity(0.55))
      .hover((s) => s.bg(t.hover).border_color(t.accent))
      .on_click((_e, cx) => onClick(cx))
      .when(Boolean(opts.dot), (el) => el.child(div().size(6).rounded(3).bg(on ? t.accent : t.dim)))
      .child(div().text_size(11.5).text_color(on ? t.foreground : t.muted).child(label));
  }

  slider(t, state, label, value) {
    return h_flex().gap(7).items_center().flex_none()
      .child(div().text_size(10.5).text_color(t.dim).child(label))
      .child(Slider.new(state).w(92).child(
        SliderTrack.new(state).flex().items_center().h(18).w_full().cursor_pointer().child(
          SliderIndicator.new(state).relative().w_full().h(4).rounded(2).bg(t.border)
            .range_style((fill) => fill.rounded(2).bg(t.accent))
            .child(SliderThumb.new(state).size(12).rounded(6).bg(t.accent).ml(-6)))))
      .child(div().w(34).text_size(11).text_color(t.foreground).child(value));
  }

  render(cx) {
    const t = theme();
    if (props()?.menu) return this.menu(t);
    if (props()?.tail) return this.tail(t);
    const m = pick();
    if (!m) {
      return h_flex().id("mb-root").h_full().px(12).items_center().text_size(12).text_color(t.dim)
        .child("No Mux reporting. Start Mux with the herdr extension in a Herdr terminal.");
    }
    const L = m.labels;
    const pct = Number(L["mux.pct"] || 0);
    const effort = L["mux.effort"] || "";
    const ei = EFFORTS.indexOf(effort);
    if (ei >= 0 && !this.dragEffort && Math.round(this.effort.value()) !== ei) this.effort.set_value(ei);
    const wk = parseInt(L["mux.window"] || "0", 10);
    if (wk && !this.dragWindow && Math.abs(WINDOWS[Math.round(this.window.value())] - wk) > 1) this.window.set_value(WINDOWS.indexOf(nearest(WINDOWS, wk)));
    const shownWindow = WINDOWS[Math.round(this.window.value())];
    const gaugeColor = pct >= 85 ? t.blocked : pct >= 65 ? t.working : t.accent;
    const compacting = L["mux.compacting"] === "1";
    const flag = (k) => (L[k] === "1" ? true : L[k] === "0" ? false : null);
    const gauge = v_flex().w(150).flex_none().gap(3)
      .child(h_flex().justify_between().text_size(10.5)
        .child(div().text_color(t.dim).child(compacting ? "compacting…" : "context"))
        .child(div().text_color(t.foreground).child(L["mux.tokens"] ? `${L["mux.tokens"]} / ${L["mux.window"]} · ${pct}%` : "no session")))
      .child(div().w_full().h(5).rounded(3).bg(t.border)
        .child(div().h_full().rounded(3).bg(gaugeColor).w(Math.max(2, Math.min(150, pct * 1.5)))
          .when(compacting, (el) => el.loop("opacity", { from: 0.35, to: 1, period: 900 }))));
    const who = v_flex().w(150).flex_none().min_w(0)
      .child(div().text_size(12.5).font_semibold().text_color(t.foreground).truncate().child(L["mux.agent"] || "Mux"))
      .child(div().text_size(10.5).text_color(t.dim).truncate().child(`${m.address} · ${(L["mux.model"] || "").replace(/^.*\//, "").replace(/^claude-/, "")}`));
    const sep = () => div().w(1).h(22).flex_none().bg(t.border);
    const toggles = h_flex().gap(5).flex_none()
      .child(this.btn(t, "plan", "Plan", (cx) => this.act("plan", null, cx), { on: flag("mux.plan"), dot: true }))
      .child(this.btn(t, "ultra", "Ultra", (cx) => this.act("ultra", null, cx), { on: flag("mux.ultra"), dot: true }))
      .child(this.btn(t, "giga", "Giga", (cx) => this.act("giga", null, cx), { on: flag("mux.giga"), dot: true }));
    const actions = h_flex().gap(5).flex_none()
      .child(this.btn(t, "compact", "Compact", (cx) => this.act("compact", null, cx)))
      .child(this.btn(t, "prune", "Prune", (cx) => this.act("prune", "all", cx)))
      .child(this.btn(t, "retry", "Retry", (cx) => this.act("retry", null, cx)))
      .child(this.btn(t, "undo", "Undo", (cx) => this.act("undo", null, cx)))
      .child(this.btn(t, "diff", "Diff", (cx) => this.act("diff", null, cx)))
      .child(this.btn(t, "review", "Review", (cx) => this.act("review", null, cx)))
      .child(this.btn(t, "cost", "Cost", (cx) => this.act("cost", null, cx)))
      .child(this.btn(t, "more", "More…", () => openOverlay({ mod: "muxbar", kind: "popup", width: 280, height: 0.7, props: { menu: true, terminal: m.address } })));
    const askBox = Input.new(this.input).w(190).flex_none().h(26).px(8).rounded(6).border(1).border_color(t.input).bg(t.background).text_size(12).text_color(t.foreground);
    return h_flex().id("mb-root").size_full().px(12).gap(12).items_center().bg(t.chrome).overflow_x_scrollbar()
      .child(div().id("mb-who").cursor_pointer().on_click(() => run("agent.focus", { terminal: m.address })).child(who))
      .child(gauge)
      .children(muxRecords(m).map((r) => h_flex().id(`mb-rec-${r.rid}`).h(24).px(7).gap(5).items_center().flex_none().rounded(6).cursor_pointer()
        .border(1).border_color(r.status === "blocked" ? t.blocked : t.border).bg(t.raised).hover((s) => s.border_color(t.accent))
        .on_click(() => openTail(r))
        .child(recordIcon(r.agent, 12, t[r.status] ?? t.muted))
        .child(div().text_size(11).text_color(t.foreground).child(r.agent.replace(/Agent$/, "")))))
      .child(sep())
      .child(this.slider(t, this.effort, "effort", EFFORTS[Math.round(this.effort.value())] ?? "?"))
      .child(this.slider(t, this.window, "window", `${shownWindow}k`))
      .child(sep())
      .child(toggles)
      .child(sep())
      .child(actions)
      .child(sep())
      .child(askBox)
      .when(Boolean(this.last), (el) => el.child(div().flex_none().text_size(10.5).text_color(t.dim).child(`sent ${this.last}`)));
  }
}
