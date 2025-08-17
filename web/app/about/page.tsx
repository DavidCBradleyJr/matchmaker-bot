export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function About() {
  return (
    <div className="relative">
      {/* background accent */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-indigo-500/20 via-indigo-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="mb-10 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
          Built for gamers • Powered by discord.py
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight md:text-6xl">
          About <span className="bg-gradient-to-r from-indigo-400 to-violet-300 bg-clip-text text-transparent">Matchmaker Bot</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-white/70">
          Post once, reach every configured server’s LFG channel, and connect with one click.
          We keep things fast, minimal, and privacy-respecting.
        </p>
      </section>

      {/* value grid */}
      <section className="grid gap-6 md:grid-cols-3">
        <Card
          title="Broadcast LFG"
          body="Your ad fans out to each guild’s LFG channel. No more duplicating the same post across servers."
          foot="Scoped by server configuration"
        />
        <Card
          title="One-Click Connect"
          body="Players tap a button; both parties are DM’d to coordinate instantly. First click wins to avoid spam."
          foot="Atomic claim handling"
        />
        <Card
          title="Admin-Friendly"
          body="Simple setup, permission-aware posts, and sensible defaults so mods don’t have to babysit channels."
          foot="Zero-friction ops"
        />
      </section>

      {/* how it works */}
      <section className="mt-12 rounded-2xl border border-white/10 bg-zinc-900/60 p-6">
        <h2 className="mb-3 text-2xl font-semibold">Under the hood</h2>
        <ul className="space-y-4 text-white/80">
          <li className="flex gap-3">
            <Dot /> Minimal data footprint: ad records, message IDs, and per-guild LFG channel settings.
          </li>
        </ul>
      </section>
    </div>
  );
}

function Card({ title, body, foot }: { title: string; body: string; foot?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 text-white/75">{body}</p>
      {foot ? <p className="mt-4 text-xs text-white/50">{foot}</p> : null}
    </div>
  );
}

function Dot() {
  return <span className="mt-2 inline-block h-2 w-2 flex-none rounded-full bg-indigo-400" />;
}
