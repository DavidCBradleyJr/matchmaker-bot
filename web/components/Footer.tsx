export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-white/10">
      <div className="mx-auto max-w-6xl p-6 text-sm opacity-70">
        © {year} Matchmaker Bot. Production bot only — premium coming soon.
      </div>
    </footer>
  );
}