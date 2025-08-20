// web/components/Footer.tsx
export default function Footer() {
  return (
    <footer className="border-t border-neutral-900">
      <div className="mx-auto max-w-7xl px-4 py-10 flex flex-col md:flex-row gap-6 md:items-center md:justify-between text-sm text-neutral-400">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          <span>Matchmaker Bot</span>
          <span className="text-neutral-600">© {new Date().getFullYear()}</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <a href="/api/invite" className="hover:text-white">Add to Discord</a>
        </div>
      </div>
    </footer>
  );
}
