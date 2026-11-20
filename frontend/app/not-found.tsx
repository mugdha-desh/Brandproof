import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main" className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-6">
      <h1 className="text-3xl font-extrabold">We could not find that page</h1>
      <p className="text-sm text-slate-800">The link may be old, or the asset may belong to someone else. Receipts can be checked on the Verify page without signing in.</p>
      <div className="flex gap-3">
        <Link className="btn btn-primary" href="/">Go to the dashboard</Link>
        <Link className="btn btn-ghost" href="/verify">Verify a receipt</Link>
      </div>
    </main>
  );
}
