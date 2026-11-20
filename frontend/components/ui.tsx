"use client";
import { ReactNode } from "react";

export function Chip({ children, tone = "gray", title }: { children: ReactNode; tone?: string; title?: string }) {
  const tones: Record<string, string> = {
    gray: "bg-slate-100 text-slate-700 ring-slate-200", red: "bg-stampbg text-stamp ring-red-200", green: "bg-okbg text-ok ring-emerald-200",
    amber: "bg-warnbg text-warn ring-amber-200", navy: "bg-navy text-white ring-navy", blue: "bg-sky-50 text-sky-800 ring-sky-200",
  };
  return <span title={title} className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${tones[tone] || tones.gray}`}>{children}</span>;
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="rise mb-6 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-3xl font-extrabold">{title}</h1>{subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-600">{subtitle}</p>}</div>
      {children && <div className="flex gap-2">{children}</div>}
    </div>
  );
}

export const sevTone = (s: string) => (s === "high" ? "red" : s === "medium" ? "amber" : "gray");
export const verdictTone = (v: string) =>
  v === "Supported" ? "green" : v === "Contradicted" || v === "Outdated" ? "red" : v === "Unsupported" ? "amber" : "gray";
export const statusTone = (s: string) =>
  s === "Approved" ? "green" : s === "In review" ? "blue" : s === "Changes requested" ? "amber" : "gray";

export function Sev({ s }: { s: string }) { return <Chip tone={sevTone(s)}><span className="capitalize">{s} severity</span></Chip>; }
export function Verdict({ v }: { v: string }) { return v ? <Chip tone={verdictTone(v)}>{v}</Chip> : null; }
export function Method({ m }: { m: string }) {
  const label: Record<string, string> = { rule: "Rule", claims: "Claims", ai: "AI", heuristic: "Heuristic", trust: "Trust" };
  const tone: Record<string, string> = { rule: "navy", claims: "navy", ai: "blue", heuristic: "amber", trust: "red" };
  return <Chip tone={tone[m] || "gray"} title="How this finding was produced">{label[m] || m}</Chip>;
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="mb-4 inline-flex max-w-full flex-wrap gap-1 rounded-xl bg-slate-200/60 p-1">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`rounded-lg px-3.5 py-1.5 text-sm font-semibold transition ${value === t.id ? "bg-surface text-ink shadow-sm" : "text-slate-600 hover:text-ink"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Toast({ msg, kind, onClose }: { msg: string; kind: "error" | "ok"; onClose: () => void }) {
  if (!msg) return null;
  return (
    <div role="alert" className={`toast-in fixed bottom-5 left-1/2 z-50 flex max-w-xl -translate-x-1/2 items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-lg ${kind === "error" ? "border-red-200 bg-stampbg text-stamp" : "border-emerald-200 bg-okbg text-ok"}`}>
      <span className="font-semibold">{msg}</span>
      <button onClick={onClose} className="font-bold opacity-70 hover:opacity-100" aria-label="Dismiss">&times;</button>
    </div>
  );
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-surface/60 p-10 text-center text-sm text-slate-600"><p className="mx-auto max-w-md">{children}</p>{action && <div className="mt-4">{action}</div>}</div>;
}

export function Skeleton({ className = "h-5 w-full" }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} />;
}

export function TableSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="card space-y-3">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
    </div>
  );
}

const METER: Record<string, string> = { brand: "bg-brand", ok: "bg-ok", red: "bg-stamp", amber: "bg-amber-500", gray: "bg-slate-400" };
export function Meter({ value, max, tone = "brand", label }: { value: number; max: number; tone?: string; label: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((value / max) * 100))) : 0;
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max} className="h-2 overflow-hidden rounded-full bg-slate-200">
      <div style={{ width: pct + "%" }} className={`h-full rounded-full transition-[width] duration-700 ease-out ${METER[tone] || METER.brand}`} />
    </div>
  );
}

export function Stat({ label, value, tone = "text-ink" }: { label: string; value: ReactNode; tone?: string }) {
  return <div className="card p-4"><div className="text-xs font-semibold text-slate-600">{label}</div><div className={`mt-1 font-display text-3xl font-extrabold ${tone}`}>{value}</div></div>;
}

export function Switch({ checked, onChange, disabled, children }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; children: ReactNode }) {
  return (
    <label className={`flex items-start gap-4 rounded-xl border border-slate-200 p-4 transition ${disabled ? "opacity-70" : "cursor-pointer hover:border-slate-300 hover:bg-slate-50"}`}>
      <span className="relative mt-0.5 inline-flex h-6 w-11 shrink-0">
        <input type="checkbox" role="switch" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span aria-hidden className="absolute inset-0 rounded-full bg-slate-300 transition-colors peer-checked:bg-brand peer-focus-visible:ring-4 peer-focus-visible:ring-brand/30" />
        <span aria-hidden className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
      <span className="text-sm leading-relaxed">{children}</span>
    </label>
  );
}

export function SearchBox({ value, onChange, label, placeholder }: { value: string; onChange: (v: string) => void; label: string; placeholder?: string }) {
  return (
    <div className="relative max-w-md flex-1">
      <label className="sr-only" htmlFor={`sb-${label}`}>{label}</label>
      <svg aria-hidden viewBox="0 0 24 24" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
      <input id={`sb-${label}`} type="search" className="input pl-10" value={value} placeholder={placeholder || label} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
