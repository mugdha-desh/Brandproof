"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { useUser } from "@/components/Shell";
import { Chip, Verdict } from "@/components/ui";

const SEV_DOT: Record<string, string> = { high: "bg-stamp", medium: "bg-amber-500", low: "bg-slate-400" };
import { api } from "@/lib/api";

async function downloadPdf(id: string, setMsg: (m: string) => void) {
  try {
    const blob = await api(`/assets/${id}/proofpack.pdf`, { blob: true });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `proof-pack-${id}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e: any) { setMsg(e.message); }
}

function Row({ k, children, tone }: { k: string; children: any; tone?: "warn" }) {
  const box = tone === "warn" ? "my-3 rounded-xl border border-amber-600/30 bg-warnbg px-4" : "border-b border-dashed border-slate-200 last:border-b-0";
  return <div className={`grid gap-1 py-4 md:grid-cols-4 ${box}`}><div className={`text-sm font-bold ${tone === "warn" ? "text-warn" : "text-brand"}`}>{k}</div><div className="text-sm leading-relaxed md:col-span-3">{children}</div></div>;
}

function CopyCode({ code }: { code: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="no-print btn btn-ghost !px-2.5 !py-1 text-xs" onClick={async () => { try { await navigator.clipboard.writeText(code); setDone(true); setTimeout(() => setDone(false), 1600); } catch {} }}>
      {done ? "Copied" : "Copy code"}
    </button>
  );
}

export default function Proof() {
  const { id } = useParams<{ id: string }>();
  const { user } = useUser();
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => { if (user) api(`/assets/${id}/proofpack`).then(setP).catch((e) => setErr(e.message)); }, [user, id]);
  if (err) return <Shell><p role="alert" className="font-semibold text-stamp">{err}</p></Shell>;
  if (!p) return <Shell><div role="status" aria-label="Loading Proof Pack" className="mx-auto max-w-4xl space-y-4"><div className="skeleton h-32" /><div className="skeleton h-24" /><div className="skeleton h-64" /></div></Shell>;
  const s = p.summary, c = p.checks || {};
  const open = p.findings.filter((f: any) => f.status === "open" || f.status === "rejected");
  return (
    <Shell>
      <div className="no-print mb-3 flex gap-2"><Link href={`/assets/${id}`} className="btn btn-ghost">Back to review</Link><button className="btn btn-brand" onClick={() => downloadPdf(id, setMsg)}>Download Proof Pack PDF</button><button className="btn btn-ghost" onClick={() => window.print()}>Print this page</button>{msg && <span role="alert" className="self-center text-sm font-semibold text-stamp">{msg}</span>}</div>
      <article className="rise mx-auto max-w-4xl overflow-hidden rounded-2xl border border-slate-200 bg-surface shadow-soft">
        <div aria-hidden className={`h-1.5 ${p.asset.status === "Approved" ? "bg-ok" : "bg-amber-500"}`} />
        <header className="flex flex-wrap items-center gap-4 px-6 pb-5 pt-6 sm:px-8">
          <span aria-hidden className={`grid h-16 w-16 shrink-0 place-items-center rounded-full ${p.asset.status === "Approved" ? "bg-okbg text-ok" : "bg-warnbg text-warn"}`}>
            {p.asset.status === "Approved"
              ? <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
              : <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><h1 className="text-3xl font-extrabold">Proof Pack</h1><Chip tone={p.asset.status === "Approved" ? "green" : "amber"}>{p.asset.status}</Chip></div>
            <p className="mt-0.5 truncate text-sm font-semibold text-slate-800">{p.asset.title}</p>
            <p className="mt-0.5 text-xs text-slate-600">Generated {p.generated_at.replace("T", " ")} | v{p.version.n} | sha256 {p.version.sha256.slice(0, 16)}</p>
          </div>
        </header>
        <section aria-label="At a glance" className="grid grid-cols-2 border-y border-slate-200 bg-slate-50 sm:grid-cols-4">
          {[["Claims judged", c.claims_judged ?? 0, ""], ["Findings still open", open.length, open.length ? "text-warn" : "text-ok"], ["Fixes verified", s.fixes.verified, "text-ok"], ["External AI calls", p.ai_use.calls, ""]].map(([l, n, t]: any, i) => (
            <div key={l} className={`px-6 py-4 sm:px-8 ${i % 2 === 1 ? "border-l border-slate-200" : ""} ${i > 1 ? "max-sm:border-t max-sm:border-slate-200" : ""} sm:border-l sm:first:border-l-0`}>
              <div className={`font-display text-3xl font-extrabold ${t}`}>{n}</div><div className="text-xs font-semibold text-slate-600">{l}</div>
            </div>))}
        </section>
        <div className="px-6 pb-4 pt-2 sm:px-8">
        {p.receipt ? (
          <div className="my-3 rounded-xl border border-ok/30 bg-okbg p-4">
            <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-bold text-ok">Signed receipt</span><Chip tone={p.receipt.current ? "green" : "amber"}>{p.receipt.current ? "Receipt for this version" : "Receipt is for an earlier version"}</Chip></div>
            <div className="mt-2 flex flex-wrap items-center gap-3"><b className="font-mono text-xl tracking-wide">{p.receipt.code}</b><CopyCode code={p.receipt.code} /></div>
            <p className="mt-1 text-xs text-slate-700">Issued {p.receipt.issued_at.replace("T", " ")} by {p.receipt.issued_by}.</p>
            <div className="mt-1 break-all font-mono text-xs text-slate-700">digest {p.receipt.digest}</div>
            <div className="mt-2 text-xs">Anyone can check it without logging in: <Link className="font-semibold underline" href={`/verify/${p.receipt.code}`}>{p.receipt.verify_url}</Link></div>
          </div>
        ) : (
          <Row k="Signed receipt"><Chip tone="gray">None yet</Chip> A signed receipt is issued when the asset is approved.</Row>
        )}
        <Row k="Asset"><b>{p.asset.title}</b> ({p.asset.channel}) by {p.asset.creator}, team {p.asset.team}</Row>
        <Row k="Creator intent">{p.asset.intent}</Row>
        <Row k="Trust Layer">
          {p.trust.has_hidden ? <Chip tone="red">{p.trust.hidden.length} hidden item(s) found and removed</Chip> : <Chip tone="green">No hidden text</Chip>}{" "}
          {p.trust.injections?.length ? <Chip tone="red">{p.trust.injections.length} injection pattern(s), not obeyed</Chip> : <Chip tone="green">0 injection signals</Chip>}
          <div className="mt-1">Raw vs cleaned review: {!p.differential.ran ? "identical, single review" : p.differential.agree ? "ran, verdicts agree" : "ran, VERDICTS DIFFER (manipulation flag)"}</div>
        </Row>
        <Row k="Checks run">{c.deterministic_rules} deterministic rules, {c.file_checks} file checks, {c.claims_judged} claims judged, {c.judgment_rules} tone/messaging rules via <b>{c.judgment_method}</b>.
          <div><b>{s.abstained}</b> finding(s) were routed to a human because the reviewer was not confident.</div></Row>
        <Row k="Claim Ledger">{p.claim_ledger.length === 0 ? "No promotional claims." : (
          <ul className="space-y-2">{p.claim_ledger.map((x: any) => (
            <li key={x.label} className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-lg bg-slate-50 px-3 py-2"><span className="font-bold">{x.label}</span><span className="min-w-0 flex-1">{x.text}</span><Verdict v={x.verdict} /><span className="text-xs text-slate-600">{x.fact || "no fact"}</span></li>))}</ul>)}</Row>
        <Row k="Findings">{p.findings.length} total, {open.length} still open. Fixes proposed {s.fixes.proposed}, verified {s.fixes.verified}, withheld {s.fixes.withheld}.
          <ul className="mt-2 space-y-1 text-xs">{p.findings.slice(0, 40).map((f: any) => <li key={f.id} className="flex items-start gap-2"><span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[f.severity] || "bg-slate-400"}`} /><span>#{f.id} {f.rule} [{f.severity}, {f.method}] {f.title} - <b>{f.status}</b>{f.decided_by ? ` by ${f.decided_by}` : ""}</span></li>)}</ul></Row>
        <Row k="NOT checked" tone="warn"><ul className="list-disc pl-5">{p.not_checked.map((n: string) => <li key={n}>{n}</li>)}</ul><p className="mt-1 text-xs">Facts were valid as of {s.facts_as_of}.</p></Row>
        <Row k="Humans">{p.humans.length === 0 ? "No human decisions recorded yet." : <ol className="ml-1 space-y-3 border-l-2 border-slate-200 pl-4">{p.humans.map((h: any, i: number) => <li key={i} className="relative before:absolute before:-left-[1.4rem] before:top-1.5 before:h-2.5 before:w-2.5 before:rounded-full before:bg-brand before:ring-4 before:ring-surface">{h.ts.replace("T", " ")} {h.actor}: {h.action}{h.detail?.note ? ` ("${h.detail.note}")` : ""}{h.detail?.rule ? ` [${h.detail.rule}]` : ""}</li>)}</ol>}
          {p.waived.length > 0 && <div className="mt-1"><b>Waived by a reviewer:</b><ul className="list-disc pl-5">{p.waived.map((w: string) => <li key={w}>{w}</li>)}</ul></div>}
          <p className="mt-1 text-xs">Nothing was applied or approved by AI.</p></Row>
        <Row k="AI use">Provider: <b>{p.ai_use.provider}</b> {p.ai_use.model ? `(${p.ai_use.model})` : ""}; {p.ai_use.calls} external call(s); {p.ai_use.redactions} personal-data item(s) redacted. <div className="text-xs">{p.ai_use.note}</div></Row>
        <Row k="Version history"><ul className="list-disc pl-5">{p.versions.map((v: any) => <li key={v.n}>v{v.n}: {v.note} ({v.by}, sha256 {v.sha256})</li>)}</ul></Row>
        <Row k="Audit chain">{p.audit_chain.ok ? <Chip tone="green">Tamper-evident log verified: {p.audit_chain.entries} entries</Chip> : <Chip tone="red">Audit log FAILED verification at entry {p.audit_chain.first_bad_id}</Chip>}
          <div className="mt-1 font-mono text-xs">head {p.audit_chain.head}</div></Row>
        </div>
      </article>
    </Shell>
  );
}
