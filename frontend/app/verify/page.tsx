"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function VerifyHome() {
  const router = useRouter();
  const [code, setCode] = useState("");
  return (
    <main id="main" className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <h1 className="text-3xl font-extrabold">Verify a Proof Pack</h1>
      <p className="text-sm text-slate-800">Enter the receipt code printed on a BrandProof Proof Pack (it starts with BP-). You do not need an account.</p>
      <label className="label" htmlFor="code">Receipt code</label>
      <input id="code" className="input font-mono" placeholder="BP-XXXXXXXXXXXXXXXX" value={code} onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && code.trim()) router.push(`/verify/${encodeURIComponent(code.trim().toUpperCase())}`); }} />
      <button className="btn btn-brand" disabled={!code.trim()} onClick={() => router.push(`/verify/${encodeURIComponent(code.trim().toUpperCase())}`)}>Check receipt</button>
    </main>
  );
}
