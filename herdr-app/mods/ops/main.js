// Ops: the remote machines (hc machine add ...) at a glance. Per machine: link state, uptime/load, disk, memory and the
// user services that matter (running / failed). Read-only checks over `hc exec --on <machine>`.
import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { exec, machines, spaces, agents, theme, run, readTextFile, appHome } from "herdr";

// Services to pin per machine (shown first, red when not active), from ops.json next to this file:
//   { "pinned": { "<machine name>": ["my-service", "nginx"] } }
// Without it every machine just lists its running/failed user services.
let PINNED = {};
const PROBE = [
  "echo HOST=$(hostname)",
  "echo UP=$(cut -d. -f1 /proc/uptime)",
  "echo LOAD=$(cut -d' ' -f1-3 /proc/loadavg)",
  "echo DISK=$(df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}')",
  "echo MEM=$(free -m | awk '/Mem:/{printf \"%d/%d MB\", $3, $2}')",
  "systemctl --user list-units --type=service --all --no-legend --plain | awk '{print \"SVC=\"$1\" \"$3\" \"$4}'",
].join("; ");

const dur = (s) => {
  s = Number(s) || 0;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return d ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
};

export default class Ops extends View {
  init(_p, cx) {
    this.info = {};
    cx.spawn(async (cx) => {
      try {
        PINNED = JSON.parse((await readTextFile(`${appHome()}/mods/ops/ops.json`)) ?? "{}").pinned ?? {};
      } catch {}
      cx.notify();
    });
    this.refresh(cx);
    cx.timer.every(60000, (cx) => this.refresh(cx));
  }

  refresh(cx) {
    for (const m of machines()) {
      if (!m.name) continue;
      cx.spawn(async (cx) => {
        const t0 = Date.now();
        try {
          const r = await exec("sh", ["-c", PROBE], { on: m.name });
          const info = { ms: Date.now() - t0, svc: [], at: new Date() };
          for (const line of r.stdout.split("\n")) {
            const [k, ...rest] = line.split("=");
            const v = rest.join("=");
            if (k === "SVC") {
              const [unit, active, sub] = v.split(" ");
              if (!unit.startsWith("hc-")) info.svc.push({ name: unit.replace(/\.service$/, ""), active, sub });
            } else if (k) info[k.toLowerCase()] = v;
          }
          this.info[m.name] = info;
        } catch (e) {
          this.info[m.name] = { error: String(e?.message ?? e), at: new Date() };
        }
        cx.notify();
      });
    }
  }

  svc(t, s, pinned) {
    const ok = s.active === "active";
    const color = s.active === "failed" ? t.blocked : ok ? t.done : t.dim;
    return h_flex()
      .gap(6)
      .px(8)
      .h(24)
      .items_center()
      .rounded(6)
      .bg(pinned ? t.raised : t.surface)
      .border(1)
      .border_color(s.active === "failed" || (pinned && !ok) ? t.blocked : t.border)
      .child(div().size(7).rounded(4).bg(color))
      .child(div().text_size(11.5).text_color(ok ? t.foreground : t.muted).child(s.name))
      .when(!ok, (el) => el.child(div().text_size(10.5).text_color(color).child(s.sub || s.active)));
  }

  card(t, m) {
    const i = this.info[m.name] ?? {};
    const mySpaces = spaces().filter((s) => s.machine === m.name);
    const myAgents = agents().filter((a) => mySpaces.some((s) => s.id === a.space));
    const pin = PINNED[m.name] ?? [];
    const svc = i.svc ?? [];
    const pinned = pin.map((n) => svc.find((s) => s.name === n) ?? { name: n, active: "missing", sub: "missing" });
    const rest = svc.filter((s) => !pin.includes(s.name) && (s.active === "active" || s.active === "failed"));
    const failed = svc.filter((s) => s.active === "failed").length;
    const online = m.layout !== "unavailable" && !i.error;
    const stat = (k, v) => v_flex().gap(2).child(div().text_size(10).text_color(t.dim).child(k)).child(div().text_size(12.5).text_color(t.foreground).child(v ?? "\u2014"));
    return v_flex()
      .id(`ops-${m.name}`)
      .flex_1()
      .min_w(320)
      .p(14)
      .gap(12)
      .rounded(12)
      .bg(t.surface)
      .border(1)
      .border_color(failed ? t.blocked : t.border)
      .child(
        h_flex().gap(10).items_center()
          .child(svg("mods/workspace-chrome/server.svg").size(18).text_color(online ? t.accent : t.dim))
          .child(v_flex().flex_1()
            .child(div().text_size(14).font_semibold().text_color(t.foreground).child(m.name))
            .child(div().text_size(11).text_color(t.muted).child(`${i.host ?? ""}${i.ms ? ` \u00b7 ${i.ms} ms` : ""}`)))
          .child(div().px(8).h(22).flex().items_center().rounded(11).bg((online ? t.done : t.blocked) + "26").text_size(11).text_color(online ? t.done : t.blocked).child(online ? "online" : i.error ? "error" : m.layout))
          .child(div().id(`ops-new-${m.name}`).px(8).h(22).flex().items_center().rounded(6).border(1).border_color(t.border).text_size(11).text_color(t.muted).cursor_pointer()
            .hover((s) => s.text_color(t.foreground).border_color(t.accent))
            .on_click(() => run("space.new", { name: `${m.name} shell`, machine: m.name }))
            .child("+ space")),
      )
      .when(Boolean(i.error), (el) => el.child(div().text_size(11.5).text_color(t.blocked).child(i.error)))
      .child(h_flex().gap(18).child(stat("uptime", i.up ? dur(i.up) : null)).child(stat("load", i.load)).child(stat("disk", i.disk)).child(stat("memory", i.mem)))
      .child(h_flex().gap(18).child(stat("spaces", String(mySpaces.length))).child(stat("agents", String(myAgents.length))).child(stat("services", `${svc.filter((s) => s.active === "active").length} up${failed ? ` \u00b7 ${failed} failed` : ""}`)))
      .when(pinned.length > 0, (el) => el.child(div().text_size(10.5).font_semibold().text_color(t.dim).child("WATCHED")).child(h_flex().flex_wrap().gap(6).children(pinned.map((s) => this.svc(t, s, true)))))
      .when(rest.length > 0, (el) => el.child(div().text_size(10.5).font_semibold().text_color(t.dim).child("OTHER SERVICES")).child(h_flex().flex_wrap().gap(6).children(rest.map((s) => this.svc(t, s, false)))));
  }

  render(cx) {
    const t = theme();
    const list = machines().filter((m) => m.name);
    return v_flex()
      .id("ops-root")
      .size_full()
      .bg(t.canvas)
      .child(
        h_flex().h(36).flex_none().px(14).gap(10).items_center().border_b(1).border_color(t.border)
          .child(div().text_size(12.5).font_semibold().text_color(t.foreground).child("Machines"))
          .child(div().text_size(11).text_color(t.dim).child(`${list.length} remote \u00b7 refreshes every minute`))
          .child(div().flex_1())
          .child(div().id("ops-refresh").px(8).h(22).flex().items_center().rounded(6).border(1).border_color(t.border).text_size(11).text_color(t.muted).cursor_pointer()
            .hover((s) => s.text_color(t.foreground))
            .on_click((_e, cx) => this.refresh(cx))
            .child("refresh")),
      )
      .child(
        div().id("ops-scroll").flex_1().min_h(0).p(12).overflow_y_scrollbar()
          .when(list.length === 0, (el) => el.child(div().text_size(13).text_color(t.dim).child("No remote machines. Add one with + Add machine.")))
          .child(h_flex().flex_wrap().gap(12).items_start().children(list.map((m) => this.card(t, m)))),
      );
  }
}
