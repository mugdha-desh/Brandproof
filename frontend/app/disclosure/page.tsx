"use client";
import { useEffect, useState } from "react";
import Shell, { useUser } from "@/components/Shell";
import { Chip, PageHeader, Stat, Switch, Toast } from "@/components/ui";
import { api } from "@/lib/api";

export default function Disclosure() {
  const { user } = useUser();
  const [d, setD] = useState<any>(null);
  const [toast, setToast] = useState({ msg: "", kind: "ok" as "ok" | "error" });
  const load = () => api("/disclosure").then(setD).catch((e) => setToast({ msg: e.message, kind: "error" }));
  useEffect(() => { if (user) load(); }, [user]);
  const set = async (body: any) => {
    try { await api("/settings", { method: "PUT", body }); await load(); setToast({ msg: "Setting saved", kind: "ok" }); }
    catch (e: any) { setToast({ msg: e.message, kind: "error" }); }
  };
  if (!d) return <Shell><div role="status" aria-label="Loading disclosure" className="space-y-4"><div className="skeleton h-12 w-80" /><div className="skeleton h-24" /><div className="skeleton h-56" /></div></Shell>;
  const owner = user?.role === "owner";
  return (
    <Shell>
      <PageHeader title="AI and external-service disclosure" subtitle={d.ai_note} />
      <section aria-label="Current AI status" className={`mb-6 flex items-center gap-4 rounded-2xl border p-5 ${d.confidential_mode ? "border-ok/30 bg-okbg" : d.llm_enabled ? "border-sky-200 bg-sky-50" : "border-amber-600/30 bg-warnbg"}`}>
        <span aria-hidden className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-surface/70">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d.confidential_mode ? <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></> : <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>}</svg>
        </span>
        <div className="min-w-0">{d.confidential_mode ? <Chip tone="green">Confidential mode ON: no external calls are made</Chip> : d.llm_enabled ? <Chip tone="blue">External model: {d.provider} / {d.model}</Chip> : <Chip tone="amber">No external AI configured: heuristic fallback only</Chip>}
          <p className="mt-1.5 text-sm text-slate-800">{d.confidential_mode ? "Reviews run on local rules, local OCR and the labelled heuristic." : d.llm_enabled ? "Personal data is replaced by tokens before text is sent." : "Nothing leaves the server. Some tone checks are weaker without a model."}</p></div>
      </section>
      <section aria-label="Disclosure totals" className="stagger mb-2 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Services listed" value={d.services.length} />
        <Stat label="Send data outside" value={d.services.filter((x: any) => x.external).length} tone={d.services.some((x: any) => x.external) ? "text-warn" : "text-ok"} />
        <Stat label="External calls" value={d.calls_by_purpose.reduce((n: number, c: any) => n + c.calls, 0)} />
        <Stat label="Items redacted" value={d.calls_by_purpose.reduce((n: number, c: any) => n + c.redactions, 0)} tone="text-ok" />
      </section>

      <h2 className="mb-3 mt-8 text-lg font-bold">Services and the data each receives</h2>
      <div className="card overflow-x-auto p-0"><table className="w-full"><thead><tr><th className="th">Service</th><th className="th">Data</th><th className="th">External</th></tr></thead>
        <tbody>{d.services.map((s: any) => <tr key={s.name}><td className="td font-semibold">{s.name}</td><td className="td">{s.data}</td><td className="td">{s.external ? <Chip tone="red">YES</Chip> : <Chip tone="green">No</Chip>}</td></tr>)}</tbody></table></div>

      <h2 className="mb-3 mt-8 text-lg font-bold">Privacy controls</h2>
      <div className="card max-w-3xl space-y-3 text-sm">
        <p>Emails, phone numbers, Aadhaar, PAN and card numbers are replaced by tokens before any text is sent to an external model.</p>
        <Switch disabled={!owner} checked={!!d.confidential_mode} onChange={(v) => set({ confidential_mode: v })}><b>Confidential mode.</b> Blocks every external AI call. Reviews run on local rules, local OCR and the labelled heuristic only, and the Proof Pack says so. Use it for unreleased or sensitive material. Tone and messaging checks that need an AI model are listed as not checked.</Switch>
        <Switch disabled={!owner} checked={d.retention_delete_after_approval} onChange={(v) => set({ retention_delete_after_approval: v })}><b>Delete content after approval.</b> Files and text are removed when an asset is approved; the Proof Pack and audit log are kept.</Switch>
        <Switch disabled={!owner || !d.llm_enabled} checked={d.images_to_llm} onChange={(v) => set({ images_to_llm: v })}><b>Allow images to be read by the AI vision model.</b> Off by default because pixels cannot be redacted. {!d.llm_enabled && "(No model configured.)"}</Switch>
        {!owner && <p className="text-xs text-slate-700">Only the guideline owner can change these settings.</p>}
      </div>

      <h2 className="mb-3 mt-8 text-lg font-bold">Calls by purpose</h2>
      <div className="card overflow-x-auto p-0">{d.calls_by_purpose.length === 0 ? <p className="p-6 text-center text-sm text-slate-600">No external calls have been made.</p> : (
        <table className="w-full"><thead><tr><th className="th">Purpose</th><th className="th">Calls</th><th className="th">Items redacted</th></tr></thead>
          <tbody>{d.calls_by_purpose.map((c: any) => <tr key={c.purpose}><td className="td">{c.purpose}</td><td className="td">{c.calls}</td><td className="td">{c.redactions}</td></tr>)}</tbody></table>)}</div>
      <h2 className="mb-3 mt-8 text-lg font-bold">Recent calls</h2>
      <div className="card overflow-x-auto p-0">{d.calls.length === 0 ? <p className="p-6 text-center text-sm text-slate-600">No calls recorded yet.</p> : (
        <table className="w-full"><thead><tr><th className="th">Time</th><th className="th">Model</th><th className="th">Purpose</th><th className="th">Asset</th><th className="th">Chars sent</th><th className="th">Redactions</th><th className="th">Status</th></tr></thead>
          <tbody>{d.calls.map((c: any, i: number) => <tr key={i}><td className="td">{c.ts.replace("T", " ")}</td><td className="td">{c.provider}/{c.model}</td><td className="td">{c.purpose}</td><td className="td">{c.asset_id ?? "-"}</td><td className="td">{c.chars}</td><td className="td">{c.redactions}</td><td className="td">{c.status}</td></tr>)}</tbody></table>)}</div>
      <Toast {...toast} onClose={() => setToast({ ...toast, msg: "" })} />
    </Shell>
  );
}
