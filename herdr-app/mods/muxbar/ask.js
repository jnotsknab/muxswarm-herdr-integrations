// Talk to a Mux session through the `herdr` Mux extension's loopback endpoint.
// Any mod can import this: `import { askMux } from "../muxbar/ask.js";`
//   askMux("Explain this trade: ...")      -> sent to the Mux in the shown tab (else the most recent)
//   muxCall("t2", "/run", { action: "compact" })
// The extension publishes `mux.port` and `mux.token` labels on its terminal; only processes of this
// user can read them (same trust as hc itself).
import { terminals, panes, focused } from "herdr";

/** Live terminals running Mux with the herdr extension, most recently active first. */
export function muxTerminals() {
  return terminals()
    .filter((k) => k.state === "live" && k.labels?.["mux.port"] && k.labels?.["mux.token"])
    .sort((a, b) => (b.status_ms ?? 0) - (a.status_ms ?? 0));
}

/** The Mux in the shown tab, else the most recently active one. */
export function currentMux() {
  const all = muxTerminals();
  const tab = focused()?.tab;
  const here = new Set(panes().filter((p) => p.tab === tab).map((p) => p.terminal));
  return all.find((k) => here.has(k.address)) ?? all[0] ?? null;
}

export async function muxCall(address, path, body) {
  const m = muxTerminals().find((k) => k.address === address);
  if (!m) throw new Error(`no Mux with the herdr extension at ${address}`);
  const r = await fetch(`http://127.0.0.1:${m.labels["mux.port"]}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${m.labels["mux.token"]}`, "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  let out = null;
  try { out = await r.json(); } catch { out = null; }
  if (!r.ok) throw new Error(out?.error ?? `HTTP ${r.status}`);
  return out;
}

/** Send `text` to Mux as your next message (queued until the current turn ends). */
export async function askMux(text, address) {
  const m = address ? { address } : currentMux();
  if (!m) throw new Error("no Mux reporting (start Mux with the herdr extension in a Herdr terminal)");
  return muxCall(m.address, "/ask", { text });
}
