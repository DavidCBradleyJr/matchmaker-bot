export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Privacy() {
  return (
    <div className="relative">
      {/* background accent */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-indigo-500/25 via-indigo-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="mb-10 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
          Updated • Minimal data footprint
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight md:text-6xl">
          Privacy <span className="bg-gradient-to-r from-indigo-400 to-violet-300 bg-clip-text text-transparent">Policy</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-white/70">
          We collect only what we need to run LFG posts and connections. No selling data. Ever.
        </p>
      </section>

      {/* summary cards */}
      <section className="grid gap-6 md:grid-cols-3">
        <Card title="What we store" items={[
          "Ad records (game, optional fields)",
          "Message IDs for posted ads",
          "Per-guild LFG channel settings",
        ]}/>
        <Card title="What we don’t store" items={[
          "Private DMs content",
          "Payment data (none today)",
          "Unnecessary personal info",
        ]}/>
        <Card title="Why we store it" items={[
          "To post ads reliably",
          "To handle one-click connect",
          "To let admins configure channels",
        ]}/>
      </section>

      {/* sections */}
      <Section title="Data we process">
        <p>
          When you post an LFG ad, we save the ad fields you provide and basic Discord identifiers
          (user/guild/channel/message IDs). This lets us publish across configured servers and manage claims.
        </p>
      </Section>

      <Section title="Direct messages">
        <p>
          “Connect” sends DMs via Discord. We don’t read your private messages; we only initiate the DM with each party.
        </p>
      </Section>

      <Section title="Retention & deletion">
        <p>
          Ad and post records may be retained for moderation and diagnostics. Server owners can request removal of their
          server’s data; individual users may ask us to remove their ads where feasible.
        </p>
      </Section>

      <Section title="Security">
        <p>
          We use least-privilege bot permissions and standard platform security (host secrets, TLS). No guarantees are
          absolute, but we aim for sensible, low-risk defaults.
        </p>
      </Section>
    </div>
  );
}

function Card({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <h3 className="text-lg font-semibold">{title}</h3>
      <ul className="mt-3 space-y-2 text-white/75">
        {items.map((t, i) => (
          <li key={i} className="flex gap-3">
            <Dot /> <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10 rounded-2xl border border-white/10 bg-zinc-900/60 p-6">
      <h2 className="mb-2 text-2xl font-semibold">{title}</h2>
      <div className="text-white/80">{children}</div>
    </section>
  );
}

function Dot() {
  return <span className="mt-2 inline-block h-2 w-2 flex-none rounded-full bg-indigo-400" />;
}