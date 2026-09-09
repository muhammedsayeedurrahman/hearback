import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hearback — handover firewall",
  description:
    "Live truth state for a clinical handover: what was heard, what was corrected, what was verified, and what is safe to relay.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
