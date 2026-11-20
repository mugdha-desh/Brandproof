// BrandProof pre-flight popup. Server text is only ever written with textContent, never as markup.
const $ = (id) => document.getElementById(id);
let server = "", token = "", tab = null;

function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function say(msg) { $("msg").hidden = !msg; $("msg").textContent = msg || ""; }
function show(which) { for (const id of ["setup", "check"]) $(id).hidden = id !== which; $("signout").hidden = which !== "check"; }

function cleanOrigin(v) {
  let u;
  try { u = new URL(v.trim()); } catch { throw new Error("Enter the server address, for example https://brandproof.example.com"); }
  const local = u.hostname === "localhost" || u.hostname === "127.0.0.1";
  if (u.protocol !== "https:" && !(local && u.protocol === "http:")) throw new Error("The server address must start with https://");
  return u.origin;
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  let r;
  try { r = await fetch(server + path, { ...opts, headers }); }
  catch { throw new Error("Could not reach the BrandProof server. Check the address and your connection."); }
  if (r.status === 401) { token = ""; await chrome.storage.session.remove("token"); show("setup"); throw new Error("Your session ended. Please sign in again."); }
  if (r.status === 429) throw new Error("Too many checks in a short time. Wait a minute and try again.");
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch {} throw new Error(typeof d === "string" && d ? d : `The server answered with an error (${r.status}).`); }
  return r.json();
}

async function login() {
  say("");
  try {
    const origin = cleanOrigin($("server").value);
    const granted = await chrome.permissions.request({ origins: [origin + "/*"] });
    if (!granted) throw new Error("Permission to contact that server was not granted.");
    server = origin;
    const r = await api("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value.trim(), password: $("password").value }) });
    token = r.token;
    await chrome.storage.local.set({ server });
    await chrome.storage.session.set({ token, email: $("email").value.trim() });
    $("password").value = "";
    await enter();
  } catch (e) { say(e.message); }
}

async function selection() {
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => String(window.getSelection() || "") });
    return (res && res.result) || "";
  } catch { return ""; }
}

async function enter() {
  show("check");
  const s = await chrome.storage.session.get(["email", "pending"]);
  $("who").textContent = s.email ? `Signed in as ${s.email} at ${new URL(server).host}. Nothing is approved or changed from here.` : "";
  if (s.pending) { $("text").value = s.pending; await chrome.storage.session.remove("pending"); chrome.action.setBadgeText({ text: "" }); }
  else { const t = await selection(); if (t) $("text").value = t.slice(0, 20000); }
}

function renderResult(b, assetId) {
  const box = $("result");
  box.replaceChildren();
  const sev = { high: 0, medium: 0, low: 0 };
  for (const f of b.findings) sev[f.severity] = (sev[f.severity] || 0) + 1;
  const sum = el("div", "summary");
  for (const [k, label] of [["high", "High"], ["medium", "Medium"], ["low", "Low"]]) { const d = el("div"); d.append(el("b", "", String(sev[k]))); d.append(label); sum.append(d); }
  box.append(sum);
  if (b.findings.some((f) => f.rule_id === "TRUST-02" || f.rule_id === "TRUST-01")) box.append(el("p", "error", "This text contains hidden or manipulated content. Do not publish it before a person looks at it."));
  if (!b.findings.length) box.append(el("p", "clean", "No findings. A person still approves in BrandProof."));
  for (const f of b.findings.slice(0, 12)) {
    const card = el("div", "finding " + f.severity);
    card.append(el("h3", "", f.title));
    const tags = el("p");
    for (const t of [f.severity, f.method, f.rule_id, f.verdict].filter(Boolean)) tags.append(el("span", "tag", t));
    card.append(tags);
    card.append(el("p", "", f.explanation));
    if (f.fix && f.fix.status === "verified") {
      const fx = el("div", "fix");
      fx.append(el("div", "", "Suggested wording (re-checked, keeps your intent):"));
      fx.append(el("div", "", f.fix.after || "(remove this part)"));
      if (f.fix.after) {
        const b2 = el("button", "", "Copy suggestion");
        b2.addEventListener("click", async () => { await navigator.clipboard.writeText(f.fix.after); b2.textContent = "Copied"; });
        fx.append(b2);
      }
      card.append(fx);
    }
    box.append(card);
  }
  if (b.findings.length > 12) box.append(el("p", "muted small", `${b.findings.length - 12} more in the full review.`));
  const nc = (b.run && b.run.not_checked) || [];
  if (nc.length) box.append(el("p", "muted small", `${nc.length} thing(s) were not checked. The full review lists them.`));
  const a = el("a", "", "Open the full review in BrandProof");
  a.href = `${server}/assets/${assetId}`; a.target = "_blank"; a.rel = "noopener noreferrer";
  box.append(el("p")); box.lastChild.append(a);
  box.hidden = false;
}

async function run() {
  say("");
  const text = $("text").value.trim(), intent = $("intent").value.trim();
  if (!intent) return say("Write what the text is for, in one line.");
  if (!text) return say("Select or paste some text first.");
  const btn = $("run"); btn.disabled = true; btn.textContent = "Checking…";
  try {
    const fd = new FormData();
    fd.append("title", "Browser check: " + (tab && tab.url ? new URL(tab.url).hostname : "page").slice(0, 80));
    fd.append("intent", intent); fd.append("channel", "social"); fd.append("text", text);
    const made = await api("/api/assets", { method: "POST", body: fd });
    renderResult(await api(`/api/assets/${made.id}`), made.id);
  } catch (e) { say(e.message); }
  finally { btn.disabled = false; btn.textContent = "Check"; }
}

async function main() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const l = await chrome.storage.local.get("server"); const s = await chrome.storage.session.get("token");
  server = l.server || ""; token = s.token || "";
  $("server").value = server;
  $("login").addEventListener("click", login);
  $("run").addEventListener("click", run);
  $("useSel").addEventListener("click", async () => { const t = await selection(); if (t) $("text").value = t.slice(0, 20000); else say("No text is selected on this page. Paste it instead."); });
  $("signout").addEventListener("click", async () => { token = ""; await chrome.storage.session.remove("token"); $("result").hidden = true; show("setup"); });
  if (server && token) await enter(); else show("setup");
}
main();
