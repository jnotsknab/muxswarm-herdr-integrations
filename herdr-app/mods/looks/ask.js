// Talk to a Mux session through the `herdr` Mux extension's loopback endpoint.
// Any mod can import this: `import { askMux } from "./ask.js";` (copy this file into the mod).
//   askMux("Explain this trade: ...")      -> sent to the Mux in the shown tab (else the most recent)
//   muxCall("t2", "/run", { action: "compact" })
// The extension publishes its port as the `mux.port` label; the token is in a file only this user
// can read, <app home>/mux/control/<terminal>.json, never in a label.
import { terminals, panes, focused, readTextFile, appHome } from "herdr";

/** Live terminals running Mux with the herdr extension, most recently active first. */
export function muxTerminals() {
  return terminals()
    .filter((k) => k.state === "live" && k.labels?.["mux.port"])
    .sort((a, b) => (b.status_ms ?? 0) - (a.status_ms ?? 0));
}

/** The Mux in the shown tab, else the most recently active one. */
export function currentMux() {
  const all = muxTerminals();
  const tab = focused()?.tab;
  const here = new Set(panes().filter((p) => p.tab === tab).map((p) => p.terminal));
  return all.find((k) => here.has(k.address)) ?? all[0] ?? null;
}

const TOKENS = {}; // "<address>:<port>" -> token

async function tokenFor(address, port, fresh) {
  const key = `${address}:${port}`;
  if (!fresh && TOKENS[key]) return TOKENS[key];
  const text = await readTextFile(`${appHome()}/mux/control/${address.replace(/[^A-Za-z0-9_.-]/g, "_")}.json`);
  const c = text ? JSON.parse(text) : null;
  if (!c || String(c.port) !== String(port)) throw new Error(`no control file for ${address} (restart its Mux or /refresh)`);
  TOKENS[key] = c.token;
  return c.token;
}

export async function muxCall(address, path, body) {
  const m = muxTerminals().find((k) => k.address === address);
  if (!m) throw new Error(`no Mux with the herdr extension at ${address}`);
  const port = m.labels["mux.port"];
  for (const fresh of [false, true]) {
    const token = await tokenFor(address, port, fresh);
    const r = await fetch(`http://127.0.0.1:${port}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (r.status === 401 && !fresh) continue; // token rotated (extension restarted): re-read once
    let out = null;
    try { out = await r.json(); } catch { out = null; }
    if (!r.ok) throw new Error(out?.error ?? `HTTP ${r.status}`);
    return out;
  }
}

/** Send `text` to Mux as your next message (queued until the current turn ends). */
export async function askMux(text, address) {
  const m = address ? { address } : currentMux();
  if (!m) throw new Error("no Mux reporting (start Mux with the herdr extension in a Herdr terminal)");
  return muxCall(m.address, "/ask", { text });
}
