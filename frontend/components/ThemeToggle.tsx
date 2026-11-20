"use client";
import { useEffect, useState } from "react";

type Mode = "light" | "dark";

import { THEME_KEY as KEY } from "@/lib/theme";

export default function ThemeToggle({ className = "", onDark = false }: { className?: string; onDark?: boolean }) {
  const [mode, setMode] = useState<Mode>("light");
  useEffect(() => { setMode(document.documentElement.classList.contains("dark") ? "dark" : "light"); }, []);
  const flip = () => {
    const next: Mode = mode === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try { localStorage.setItem(KEY, next); } catch {}
    setMode(next);
  };
  const dark = mode === "dark";
  return (
    <button type="button" onClick={flip} aria-pressed={dark} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}
      className={`no-print grid h-9 w-9 place-items-center rounded-lg border transition hover:-translate-y-px ${onDark ? "border-white/25 text-white hover:bg-white/10" : "border-slate-300 bg-surface text-ink hover:bg-slate-50"} ${className}`}>
      <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        {dark ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> : <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />}
      </svg>
    </button>
  );
}
