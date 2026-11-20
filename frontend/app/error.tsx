"use client";
import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <main id="main" className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-6">
      <h1 className="text-3xl font-extrabold">Something went wrong</h1>
      <p role="alert" className="text-sm text-slate-800">
        This page hit an unexpected problem. Nothing was approved or changed by it. Try again, and if it keeps happening, sign in again or tell the team what you were doing.
      </p>
      <div className="flex gap-3">
        <button className="btn btn-primary" onClick={reset}>Try again</button>
        <a className="btn btn-ghost" href="/">Back to the dashboard</a>
      </div>
    </main>
  );
}
