import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";
import Tour from "@/components/Tour";
import { THEME_SCRIPT } from "@/lib/theme";
// Fonts are bundled from npm (no Google Fonts request), so the Docker/Render build works offline from Google.
import "@fontsource/bricolage-grotesque/latin-500.css";
import "@fontsource/bricolage-grotesque/latin-700.css";
import "@fontsource/bricolage-grotesque/latin-800.css";
import "@fontsource/figtree/latin-400.css";
import "@fontsource/figtree/latin-500.css";
import "@fontsource/figtree/latin-600.css";
import "@fontsource/figtree/latin-700.css";
import "@fontsource/figtree/latin-800.css";


export const metadata: Metadata = { title: "BrandProof", description: "Evidence-backed, tamper-resistant brand governance before content is published" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head>
      <body>{children}<Tour /></body>
    </html>
  );
}
