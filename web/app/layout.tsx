import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Matchmaker Bot — Find Teammates Fast",
  description: "A cross-server LFG Discord bot that connects developers and gamers in seconds.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL ?? "https://example.com"),
  openGraph: {
    title: "Matchmaker Bot — Find Teammates Fast",
    description: "A cross-server LFG Discord bot that connects developers and gamers in seconds.",
    type: "website",
  },
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Dark mode by default; Tailwind handles colors via classes
  return (
    <html lang="en" className="dark">
      <body className="bg-neutral-950 text-neutral-100 antialiased">{children}</body>
    </html>
  );
}
