"use client";
import { useEffect, useState } from "react";
import Shell, { useUser } from "@/components/Shell";
import { Chip, Empty, Meter, PageHeader, Stat, TableSkeleton, Toast } from "@/components/ui";
import { api } from "@/lib/api";

export default function Rulebook() {
  const { user } = useUser();
  const [rb, setRb] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState({ msg: "", kind: "ok" as "ok" | "error" });
  const owner = user?.role === "owner";
  const load = async () => { setRb(await api("/rulebook")); setRuns(await api("/redteam/runs")); };
  useEffect(() => { if (user) load().catch((e) => setToast({ msg: e.message, kind: "error" })); }, [user]);
  const call = async (key: string, path: string, body?: any, ok?: string) => {
    setBusy(key);
    try { await api(path, { body: body ?? {} }); await load(); if (ok) setToast({ msg: ok, kind: "ok" }); }
    catch (e: any) { setToast({ msg: e.message, kind: "error" }); }
    setBusy("");
  };
  if (!rb) return <Shell><div role="status" aria-label="Loading rulebook" className="space-y-4"><div className="skeleton h-12 w-64" /><div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-20" />)}</div><TableSkeleton rows={3} /></div><Toast {...toast} onClose={() => setToast({ ...toast, msg: "" })} /></Shell>;
  const latestByRule: Record<string, any> = {};
  runs.forEach((r) => { if (!latestByRule[r.rule_id]) latestByRule[r.rule_id] = r; });
  return (
    <Shell>
      <PageHeader title="Rulebook health" subtitle="Which rules are hit, overridden, ambiguous or easy to dodge. The red-team writes rule-bending content; every miss becomes a loophole with a tighter rule for the guideline owner to approve and re-test." />

      <section aria-label="Rulebook overview" className="stagger mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Rules tracked" value={rb.rules.length} />
        <Stat label="Unclear rules" value={rb.rules.filter((r: any) => r.diagnosis === "unclear").length} tone="text-warn" />
        <Stat label="Often ignored" value={rb.rules.filter((r: any) => r.diagnosis === "ignored").length} tone="text-stamp" />
        <Stat label="Red-team tested" value={rb.rules.filter((r: any) => r.redteam).length} tone="text-ok" />
      </section>

      <h2 className="mb-3 text-lg font-bold">Rules</h2>
      <div className="grid gap-4 xl:grid-cols-2">
        {rb.rules.map((r: any) => {
          const rt = r.redteam;
          const rtTone = rt ? (rt.caught === rt.total ? "ok" : rt.caught / rt.total >= 0.7 ? "amber" : "red") : "gray";
          return (
            <article key={r.rule_id} aria-label={`Rule ${r.rule_id}`} className="card flex flex-col">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0"><h3 className="font-bold"><span className="font-mono">{r.rule_id}</span> <span className="text-xs font-semibold text-slate-600">v{r.version}</span></h3><p className="text-sm text-slate-700">{r.title}</p></div>
                <div className="shrink-0">
                  {r.diagnosis === "unclear" ? <Chip tone="amber" title="People or the AI disagree about what this rule means">UNCLEAR RULE</Chip>
                    : r.diagnosis === "ignored" ? <Chip tone="red" title="Consistently overridden: the rule may be wrong, out of date or too broad">OFTEN IGNORED</Chip>
                    : r.diagnosis === "healthy" ? <Chip tone="green">ok</Chip> : <Chip tone="gray">not enough data</Chip>}
                </div>
              </div>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                <div><dt className="text-xs font-semibold text-slate-600">Hits</dt><dd className="font-display text-2xl font-extrabold">{r.hits}</dd><dd className="text-xs text-slate-700">{r.assets} asset(s)</dd></div>
                <div><dt className="text-xs font-semibold text-slate-600">Overridden</dt><dd className="font-display text-2xl font-extrabold">{r.decided ? `${Math.round(r.override_rate * 100)}%` : "-"}</dd>
                  <dd className="text-xs text-slate-700">{r.rejected} rejected, {r.waived} waived of {r.decided} decided</dd></div>
                <div><dt className="text-xs font-semibold text-slate-600">Red-team</dt><dd className="font-display text-2xl font-extrabold">{rt ? `${rt.caught}/${rt.total}` : "-"}</dd>
                  <dd className="text-xs text-slate-700">{rt ? <>caught (v{rt.rule_version})</> : r.eligible ? "not tested" : "n/a"}</dd></div>
              </dl>

              {r.decided > 0 && <div className="mt-3"><Meter label={`Override rate for ${r.rule_id}`} value={Math.round(r.override_rate * 100)} max={100} tone={r.override_rate > 0.3 ? "red" : "brand"} /></div>}
              {rt && <div className="mt-2"><Meter label={`Variants caught for ${r.rule_id}`} value={rt.caught} max={rt.total} tone={rtTone} /></div>}

              {r.ambiguity_score !== null && r.ambiguity_score !== undefined && (
                <div className="mt-3 text-xs text-slate-700">
                  <div className="mb-1 flex justify-between"><span className="font-semibold">Ambiguity score</span><span>{r.ambiguity_score.toFixed(2)}</span></div>
                  <Meter label={`Ambiguity of ${r.rule_id}`} value={Math.round(r.ambiguity_score * 100)} max={100} tone={r.ambiguity_score > 0.5 ? "red" : r.ambiguity_score > 0.25 ? "amber" : "ok"} />
                </div>
              )}
              {(r.ambiguity_reasons || []).length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-700">{r.ambiguity_reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>}
              {r.probe && <p className="mt-1 text-xs text-slate-700">AI probe: {Math.round(r.probe.disagreement * 100)}% self-disagreement ({r.probe.runs} runs, {r.probe.texts} texts)</p>}
              {rt && rt.holdout_total > 0 && <p className="mt-1 text-xs text-slate-700" title="Variants never used to write the proposal">Hold-out: {rt.holdout_caught}/{rt.holdout_total} caught</p>}
              {r.history?.length > 1 && <p className="mt-1 text-xs text-slate-700">History: {r.history.map((h: any) => `v${h.rule_version} ${h.caught}/${h.total}`).join(" → ")}</p>}

              {owner && (r.eligible || r.probeable) && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-200 pt-3">
                  {r.eligible && <button className="btn btn-brand" disabled={busy === r.rule_id} onClick={() => call(r.rule_id, "/redteam/run", { rule_id: r.rule_id }, `Red-team finished for ${r.rule_id}`)}>{busy === r.rule_id ? "Running..." : "Run red-team"}</button>}
                  {r.probeable && <button className="btn btn-ghost" disabled={busy === "probe" + r.rule_id} onClick={() => call("probe" + r.rule_id, "/redteam/ambiguity-probe", { rule_id: r.rule_id }, `AI probe finished for ${r.rule_id}`)}>{busy === "probe" + r.rule_id ? "Probing..." : "Probe AI consistency"}</button>}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <h2 className="mb-3 mt-8 text-lg font-bold">Repeated mistakes by team</h2>
      {rb.repeated_by_team.length === 0 ? <Empty>No team has broken the same rule in two or more assets yet.</Empty> : (
        <div className="card overflow-x-auto p-0"><table className="w-full"><thead><tr><th className="th">Team</th><th className="th">Rule</th><th className="th">Assets</th></tr></thead>
          <tbody>{rb.repeated_by_team.map((x: any) => <tr key={x.team + x.rule_id}><td className="td font-semibold">{x.team}</td><td className="td">{x.rule_id} <span className="text-xs">{x.title}</span></td><td className="td">{x.assets}</td></tr>)}</tbody></table></div>)}

      <h2 className="mb-3 mt-8 text-lg font-bold">Red-team runs and loophole reports</h2>
      {runs.length === 0 ? <Empty>No red-team run yet. {owner ? "Pick a rule above and press Run red-team." : "The guideline owner can run it."}</Empty> : runs.slice(0, 6).map((r) => {
        const p = r.proposal;
        return (
          <section key={r.id} className="card mb-4 p-5" aria-label={`Red-team run ${r.id}`}>
            <div className="flex flex-wrap items-center gap-2"><h3 className="font-bold">{r.rule_id} v{r.rule_version}</h3>
              <Chip tone={r.summary.missed ? "red" : "green"}>{r.summary.caught}/{r.summary.total} variants caught</Chip>
              {r.summary.holdout?.total > 0 && <Chip tone={r.summary.holdout.open.length ? "amber" : "green"}>{r.summary.holdout.caught}/{r.summary.holdout.total} hold-out caught</Chip>}
              <span className="text-xs text-slate-700">{r.created_at.replace("T", " ")} by {r.created_by} | {r.summary.sources.join(" + ")}</span></div>
            <details className="mt-2"><summary className="cursor-pointer text-sm font-semibold">Show all {r.results.length} variants</summary>
              <table className="mt-2 w-full"><thead><tr><th className="th">Variant</th><th className="th">Trick</th><th className="th">Set</th><th className="th">Result</th></tr></thead>
                <tbody>{r.results.map((v: any, i: number) => <tr key={i}><td className="td font-mono text-xs">{v.text}</td><td className="td text-xs">{v.technique}</td><td className="td text-xs">{v.split === "holdout" ? "hold-out" : "train"}</td><td className="td">{v.caught ? <Chip tone="green">CAUGHT</Chip> : <Chip tone="red">LOOPHOLE</Chip>}</td></tr>)}</tbody></table></details>
            {p && (
              <div className="mt-3 rounded-xl border border-slate-300 bg-slate-50 p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2"><b>Proposed tighter rule</b> <Chip tone={p.status === "approved" ? "green" : p.status === "rejected" ? "gray" : "amber"}>{p.status.toUpperCase()}</Chip></div>
                <p className="mt-1">{p.rationale}.</p>
                {p.retest && p.retest.total > 0 && (<div className="mt-3 grid gap-3 sm:grid-cols-2"><div><div className="mb-1 flex justify-between text-xs font-semibold text-slate-600"><span>Before</span><span>{p.retest.before_caught}/{p.retest.total}</span></div><Meter label="Caught before the change" value={p.retest.before_caught} max={p.retest.total} tone="red" /></div><div><div className="mb-1 flex justify-between text-xs font-semibold text-ok"><span>After</span><span>{p.retest.after_caught}/{p.retest.total}</span></div><Meter label="Caught after the change" value={p.retest.after_caught} max={p.retest.total} tone="ok" /></div></div>)}
                {p.retest && <p className="mt-2"><b>Re-test:</b> {p.retest.before_caught}/{p.retest.total} caught before, <b>{p.retest.after_caught}/{p.retest.total}</b> after. False positives on normal copy: {p.retest.false_positives.length}.
                  {p.retest.still_missed.length > 0 && <span> Still missed: {p.retest.still_missed.join(" | ")}</span>}</p>}
                {p.retest?.holdout_total > 0 && <p className="mt-1"><b>Generalisation (hold-out, not used to write this proposal):</b> {p.retest.holdout_before}/{p.retest.holdout_total} before, <b>{p.retest.holdout_after}/{p.retest.holdout_total}</b> after.
                  {p.retest.holdout_open.length > 0 && <span> <b>Still open:</b> {p.retest.holdout_open.join(" | ")}. These need a human rewrite of the rule.</span>}</p>}
                {p.retest?.guard?.dropped?.length > 0 && <p className="mt-1 text-xs">Left out because they would flag normal copy: {p.retest.guard.dropped.join(", ")}.</p>}
                {p.retest?.guard?.blocked && <p className="mt-1 font-semibold text-red-800" role="alert">Blocked: this change would flag normal copy ({p.retest.guard.false_positives.slice(0, 2).join(" | ")}). It cannot be approved as is.</p>}
                <details className="mt-1"><summary className="cursor-pointer text-xs font-semibold">Proposed rule settings</summary><pre className="overflow-x-auto text-xs">{JSON.stringify(p.proposed_params, null, 2)}</pre></details>
                {owner && p.status === "pending" && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button className="btn btn-ok" disabled={!!busy || !!p.retest?.guard?.blocked} onClick={() => call("p" + p.id, `/redteam/proposals/${p.id}/decision`, { action: "approve" }, "Rule updated to a new version")}>Approve tighter rule</button>
                    <button className="btn btn-ghost" disabled={!!busy} onClick={() => call("r" + p.id, `/redteam/proposals/${p.id}/retest`, {}, "Re-test complete")}>Re-test</button>
                    <button className="btn btn-danger" disabled={!!busy} onClick={() => call("x" + p.id, `/redteam/proposals/${p.id}/decision`, { action: "reject" })}>Reject</button>
                  </div>)}
              </div>)}
          </section>);
      })}
      <Toast {...toast} onClose={() => setToast({ ...toast, msg: "" })} />
    </Shell>
  );
}
