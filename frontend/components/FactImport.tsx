"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Chip } from "@/components/ui";

const TEMPLATE = "id,statement,kind,keywords,source,owner,valid_from,valid_to,qualifier\nF-40,Finora Save pays 6.5% a year on balances up to Rs 5 lakh.,rate,interest;rate;savings,Product sheet v12,Treasury,2026-11-01,2027-03-31,\n";

function when(ts?: string | null) { return ts ? ts.replace("T", " ") : "never"; }

export function ScheduleCard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api("/facts/feed").then(setS).catch(() => setS(null)); }, [refreshKey]);
  if (!s) return null;
  const r = s.last_result;
  return (
    <section aria-label="Automatic checks" className="card text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-bold">Automatic checks</h2>
        {s.enabled ? <Chip tone="green">every {s.every_hours} h</Chip> : <Chip tone="gray">scheduler off</Chip>}
        {s.feed_configured && <Chip tone="blue">feed: {s.feed_host}</Chip>}
        {s.confidential && <Chip tone="amber">confidential mode: feed paused</Chip>}
      </div>
      <p className="mt-2 text-slate-700">
        {s.enabled ? "BrandProof re-checks every approved asset against the current facts on a schedule, so an offer that expires overnight is caught without anyone clicking." : "The scheduler is switched off on this server. Use Scan now, or call the scan from a cron job."}
      </p>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs text-slate-700 sm:grid-cols-3">
        <div><dt className="font-semibold">Last run</dt><dd>{when(s.last_run)}</dd></div>
        <div><dt className="font-semibold">Next run</dt><dd>{s.enabled ? when(s.next_run) : "-"}</dd></div>
        <div><dt className="font-semibold">Last result</dt><dd>{r ? `${r.new_stale_alerts} new alert(s); feed: ${r.feed}` : "-"}</dd></div>
      </dl>
    </section>
  );
}

export default function FactImport({ onChanged, say }: { onChanged: () => void; say: (m: string, kind?: "ok" | "error") => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [feed, setFeed] = useState<any>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => { api("/facts/feed").then(setFeed).catch(() => setFeed(null)); }, [tick]);

  const send = async (dry: boolean) => {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData(); form.append("file", file); form.append("dry_run", dry ? "true" : "false");
      const r = await api("/facts/import", { form });
      setRes(r);
      if (!dry) {
        say(`Imported: ${r.created.length} added, ${r.updated.length} changed${r.new_stale_alerts ? `, ${r.new_stale_alerts} stale approval alert(s)` : ""}`);
        setFile(null); setTick(tick + 1); onChanged();
      }
    } catch (e: any) { setRes(null); say(e.message, "error"); }
    setBusy(false);
  };
  const syncFeed = async () => {
    setBusy(true);
    try {
      const r = await api("/facts/feed/sync", { method: "POST" });
      say(r.skipped || `Feed synced: ${r.created.length} added, ${r.updated.length} changed, ${r.errors.length} rejected`, r.skipped ? "error" : "ok");
      setTick(tick + 1); onChanged();
    } catch (e: any) { say(e.message, "error"); }
    setBusy(false);
  };
  const download = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" })); a.download = "fact-vault-template.csv"; a.click();
    URL.revokeObjectURL(a.href);
  };
  const changes = res ? res.created.length + res.updated.length : 0;

  return (
    <div className="space-y-4">
      <section aria-label="Import facts" className="card">
        <h2 className="font-bold">Import facts from a file</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-700">Upload a CSV or JSON file of facts (rates, terms, offer dates). You see exactly what would change first, and nothing is written until you apply it. Facts that are missing from the file are never deleted.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor="fact-file" className="sr-only">Facts file</label>
          <input id="fact-file" type="file" accept=".csv,.json,text/csv,application/json" className="input max-w-xs py-1.5" onChange={(e) => { setFile(e.target.files?.[0] || null); setRes(null); }} />
          <button className="btn btn-ghost" disabled={!file || busy} onClick={() => send(true)}>{busy && !res ? "Reading..." : "Preview changes"}</button>
          <button type="button" className="text-sm font-semibold text-brand underline" onClick={download}>Download CSV template</button>
        </div>

        {res && (
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm" role="region" aria-label="Import preview">
            <div className="flex flex-wrap gap-2">
              <Chip tone="green">{res.created.length} to add</Chip>
              <Chip tone="blue">{res.updated.length} to change</Chip>
              <Chip tone="gray">{res.unchanged.length} unchanged</Chip>
              {res.errors.length > 0 && <Chip tone="red">{res.errors.length} rejected</Chip>}
            </div>
            {res.updated.length > 0 && <ul className="mt-3 list-disc pl-5 text-xs text-slate-700">{res.updated.map((u: any) => <li key={u.id}><b>{u.id}</b>: {u.fields.join(", ")}</li>)}</ul>}
            {res.errors.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs" aria-label="Rejected rows">{res.errors.map((e: any) => <li key={e.row} className="text-stamp"><b>Row {e.row}{e.id ? ` (${e.id})` : ""}:</b> {e.problems.join("; ")}</li>)}</ul>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button className="btn btn-ok" disabled={busy || !changes || !res.dry_run} onClick={() => send(false)}>{`Apply ${changes} change(s)`}</button>
              <span className="text-xs text-slate-700">{res.dry_run ? "Rejected rows are skipped. After applying, approved assets are re-checked against the new facts." : "Applied."}</span>
            </div>
          </div>
        )}
      </section>

      {feed && (
        <section aria-label="Fact feed" className="card">
          <h2 className="font-bold">Live feed</h2>
          {feed.feed_configured ? (
            <>
              <p className="mt-1 text-sm text-slate-700">Pulled from <b>{feed.feed_host}</b>{feed.enabled ? ` every ${feed.every_hours} hours` : ""}. A feed can supply the facts themselves, never the matching rules. It is not called in confidential mode.</p>
              <button className="btn btn-ghost mt-3" disabled={busy || feed.confidential} onClick={syncFeed}>Sync feed now</button>
            </>
          ) : (
            <p className="mt-1 max-w-3xl text-sm text-slate-700">No feed is connected. To pull rates automatically, ask your administrator to set <code className="rounded bg-slate-100 px-1">BP_FACT_FEED_URL</code> to a CSV or JSON address on the server. It then syncs on the schedule below.</p>
          )}
        </section>
      )}
      <ScheduleCard refreshKey={tick} />
    </div>
  );
}
