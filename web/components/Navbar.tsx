// web/components/Navbar.tsx
import Link from "next/link";

export default function Navbar() {
  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur supports-[backdrop-filter]:bg-neutral-950/60 bg-neutral-950/80 border-b border-neutral-800">
      <nav className="mx-auto max-w-7xl px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          <span>Matchmaker Bot</span>
        </Link>
        <div className="hidden md:flex items-center gap-6 text-sm text-neutral-300">
          <Link href="#features" className="hover:text-white">Features</Link>
          <Link href="#how" className="hover:text-white">How it works</Link>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/api/invite"
            className="rounded-xl px-4 py-2 bg-indigo-500 hover:bg-indigo-400 transition text-sm font-medium"
          >
            Add to Discord
          </a>
        </div>
      </nav>
    </header>
  );
}
