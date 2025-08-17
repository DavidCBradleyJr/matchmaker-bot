import Link from "next/link";

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-white/10">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 p-6 text-sm opacity-80 md:flex-row md:items-center md:justify-between">
        <div>© {year} Matchmaker Bot. Production bot only — premium coming soon.</div>
        <nav className="flex items-center gap-4">
          <Link href="/about" className="hover:opacity-100 opacity-80">About</Link>
          <Link href="/install" className="hover:opacity-100 opacity-80">Install</Link>
          <Link href="/privacy" className="hover:opacity-100 opacity-80">Privacy</Link>
          <Link href="/terms" className="hover:opacity-100 opacity-80">Terms</Link>
          <Link href="/contact" className="hover:opacity-100 opacity-80">Contact</Link>
        </nav>
      </div>
    </footer>
  );
}
