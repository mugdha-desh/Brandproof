"use client";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Chip, Verdict } from "@/components/ui";

async function sha256Hex(f: File) {
  const buf = await crypto.subtle.digest("SHA-256", await f.arrayBuffer());
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function Check({ ok, label, detail }: { ok: boolean | null; label: string; detail?: string }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span aria-hidden className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-xs font-bold text-white ${ok === null ? "bg-slate-400" : ok ? "bg-emerald-600" : "bg-red-600"}`}>{ok === null ? "-" : ok ? "✓" : "✗"}</span>
      <span><b>{label}</b>{detail && <span className="block text-xs text-slate-700">{detail}</span>}<span className="sr-only">{ok === null ? " not checked" : ok ? " passed" : " failed"}</span></span>
    </li>
  );
}

export default function VerifyReceipt() {
  const { code } = useParams<{ code: string }>();
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  const [file, setFile] = useState<{ name: string; ok: boolean } | null>(null);
  const [digest, setDigest] = useState<boolean | null>(null);
  const [dtext, setDtext] = useState("");
  useEffect(() => {
    fetch(`/api/verify/${encodeURIComponent(code)}`).then(async (r) => {
      if (!r.ok) throw new Error(r.status === 404 ? "No receipt with this code." : "Could not check this receipt right now.");
      setV(await r.json());
    }).catch((e) => setErr(e.message));
  }, [code]);
  if (err) return <main id="main" className="mx-auto max-w-xl p-6"><h1 className="text-2xl font-extrabold">Receipt not found</h1><p role="alert" className="mt-2 font-semibold text-stamp">{err}</p><p className="mt-2 text-sm">Check the code on the Proof Pack and try again.</p></main>;
  if (!v) return <main id="main" className="p-6 text-sm text-slate-600"><p>Checking receipt…</p></main>;
  const s = v.snapshot;
  return (
    <main id="main" className="mx-auto max-w-3xl space-y-4 p-4 md:p-8">
      <header className={`rounded-2xl border-2 p-5 ${v.valid ? "border-emerald-600 bg-emerald-50" : "border-red-600 bg-red-50"}`}>
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-700">BrandProof receipt {v.code}</div>
        <h1 className="mt-1 text-3xl font-extrabold">{v.valid ? "Receipt is genuine and intact" : "This receipt FAILED verification"}</h1>
        <p className="mt-1 text-sm">{s.asset.title} ({s.asset.channel}), version {s.asset.version}. Status when issued: <b>{s.status}</b>. Issued {v.issued_at.replace("T", " ")} UTC.</p>
        {v.stale_alerts_open > 0 && <p role="alert" className="mt-2 rounded-md border border-stamp bg-red-50 p-2 text-sm font-semibold text-stamp">This receipt is genuine, but {v.stale_alerts_open} claim(s) in the approved asset no longer match the current facts. The owner has been alerted.</p>}
        {v.asset_now.changed_since && <p role="status" className="mt-2 rounded-md bg-amber-100 p-2 text-sm font-semibold">The asset has changed since this approval (now version {v.asset_now.version}). This receipt covers version {s.asset.version} only.</p>}
      </header>

      <section className="card" aria-label="What was verified"><h2 className="font-bold">What was verified</h2>
        <ul className="mt-3 space-y-3">
          <Check ok={v.signature_valid} label="Signature matches" detail="Signed by this BrandProof server when the receipt was issued." />
          <Check ok={v.digest_valid} label="Contents unchanged" detail={`SHA-256 of the receipt contents: ${v.digest}`} />
          <Check ok={v.anchor.in_log} label="Recorded in the audit log" detail={`Audit entry #${v.anchor.id} still exists with the same hash.`} />
          <Check ok={v.anchor.chain_ok} label="Audit log is tamper-evident and intact" detail={`${v.anchor.entries} entries, each linked to the one before.`} />
        </ul></section>

      <section className="card" aria-label="Check a file"><h2 className="font-bold">Is your file the approved one?</h2>
        <p className="mt-1 text-xs text-slate-700">Pick the file you were given. It is hashed in your browser and never uploaded.</p>
        <input type="file" className="mt-2 text-sm" aria-label="File to compare" onChange={async (e) => { const f = e.target.files?.[0]; if (!f) return; const h = await sha256Hex(f); setFile({ name: f.name, ok: h === s.asset.content_sha256 }); }} />
        {file && <p role="status" className={`mt-2 text-sm font-semibold ${file.ok ? "text-emerald-700" : "text-stamp"}`}>{file.ok ? `${file.name} is byte-for-byte the approved version.` : `${file.name} does NOT match the approved version.`}</p>}
        <p className="mt-2 break-all font-mono text-xs text-slate-700">approved sha256 {s.asset.content_sha256}</p>
        <label className="label mt-3" htmlFor="dg">Digest printed on your Proof Pack (optional)</label>
        <input id="dg" className="input font-mono text-xs" value={dtext} onChange={(e) => { setDtext(e.target.value); setDigest(e.target.value.trim() ? e.target.value.trim().toLowerCase() === v.digest : null); }} />
        {digest !== null && <p role="status" className={`mt-1 text-sm font-semibold ${digest ? "text-emerald-700" : "text-stamp"}`}>{digest ? "Digest matches this receipt." : "Digest does not match."}</p>}
      </section>

      <section className="card"><h2 className="font-bold">What the review covered</h2>
        <p className="mt-2 text-sm">{s.review.findings} findings, {s.review.abstained} routed to a human because the reviewer was not confident. Fixes: {s.review.fixes.proposed ?? 0} proposed, {s.review.fixes.verified ?? 0} verified, {s.review.fixes.withheld ?? 0} withheld.</p>
        <p className="mt-2 text-sm">Trust Layer: {s.trust.hidden_items} hidden item(s), {s.trust.injection_signals} instruction(s) aimed at AI reviewers (not obeyed), {s.trust.lookalike_words ?? 0} look-alike word(s){s.trust.manipulation_flag ? ", manipulation flag raised" : ", no manipulation flag"}.</p>
        {s.claim_ledger.length > 0 && <table className="mt-3 w-full"><caption className="sr-only">Claim ledger</caption><thead><tr><th className="th">Claim</th><th className="th">Kind</th><th className="th">Verdict</th><th className="th">Fact</th></tr></thead>
          <tbody>{s.claim_ledger.map((c: any) => <tr key={c.label}><td className="td font-bold">{c.label}</td><td className="td">{c.kind}</td><td className="td"><Verdict v={c.verdict} /></td><td className="td">{c.fact || "no fact"}</td></tr>)}</tbody></table>}
        <p className="mt-3 text-xs text-slate-700">Claim wording, the copy itself, comments and email addresses are deliberately not published here.</p></section>

      <section className="card"><h2 className="font-bold">Humans and AI</h2>
        <ul className="mt-2 list-disc pl-5 text-sm">{s.approvals.map((a: any, i: number) => <li key={i}>Approved by a {a.role} at {a.at.replace("T", " ")}</li>)}</ul>
        <p className="mt-2 text-sm">AI use: <b>{s.ai_use.provider}</b> {s.ai_use.model ? `(${s.ai_use.model})` : ""}, {s.ai_use.calls} call(s), {s.ai_use.redactions} personal-data item(s) redacted. <Chip tone="green">Nothing auto-applied</Chip></p></section>

      <section className="card"><h2 className="font-bold">NOT checked</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{s.not_checked.map((n: string) => <li key={n}>{n}</li>)}</ul>
        <p className="mt-2 text-xs text-slate-700">Facts were valid as of {s.facts_as_of}.</p></section>
    </main>
  );
}
