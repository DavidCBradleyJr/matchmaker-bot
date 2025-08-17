"use client";
import Link from "next/link";

export default function Header() {
  const name = process.env.NEXT_PUBLIC_SITE_NAME || "Matchmaker Bot";
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-zinc-900/60 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between p-4">
        <Link href="/" className="flex items-center gap-3">
          <img src="/logo.svg" alt="logo" className="h-8 w-8" />
          <span className="font-semibold">{name}</span>
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link href="/about" className="opacity-80 hover:opacity-100">About</Link>
          <Link href="/install" className="opacity-80 hover:opacity-100">Install</Link>
          <Link href="/privacy" className="opacity-80 hover:opacity-100">Privacy</Link>
          <Link href="/terms" className="opacity-80 hover:opacity-100">Terms</Link>
          <Link href="/contact" className="opacity-80 hover:opacity-100">Contact</Link>
        </nav>
      </div>
    </header>
  );
}
