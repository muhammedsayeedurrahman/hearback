import type { Metadata } from "next";
import localFont from "next/font/local";

import "./globals.css";

/**
 * IBM Plex, self-hosted from `app/fonts`. The files are committed rather than fetched at build
 * time because the README promises this dashboard comes up on a dead venue network, and a font
 * request is still a network request.
 *
 * One family, two voices. The interface constantly sets what a human said beside what goes on the
 * wire to the voice provider; the mono has to be unmistakably machine text while sharing a
 * skeleton with the sans, or the record reads as two different documents.
 */
const plexSans = localFont({
  src: "./fonts/ibm-plex-sans-latin-wght-normal.woff2",
  weight: "100 700",
  style: "normal",
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Hearback — handover firewall",
  description:
    "Live truth state for a clinical handover: what was heard, what was corrected, what was verified, and what is safe to relay.",
};

export const viewport = {
  themeColor: "#e9ede8",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
