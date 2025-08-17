export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Terms() {
  return (
    <div className="relative">
      {/* background accent */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-violet-500/25 via-violet-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="mb-10 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
          Community-first • Simple rules
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight md:text-6xl">
          Terms of <span className="bg-gradient-to-r from-violet-300 to-indigo-300 bg-clip-text text-transparent">Service</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-white/70">
          Use the bot respectfully. Don’t abuse it. We’ll do our best to keep it available and useful.
        </p>
      </section>

      {/* rules grid */}
      <section className="grid gap-6 md:grid-cols-2">
        <Rule title="Acceptable use">
          No spam, harassment, illegal activity, or evasion of server rules. Follow Discord’s Terms and each server’s policies.
        </Rule>
        <Rule title="Rate limits & fairness">
          We may throttle, hide, or remove posts that degrade experience for others or trigger platform limits.
        </Rule>
        <Rule title="Availability">
          The service is provided “as is.” Outages and maintenance can occur. We don’t guarantee uptime or continuity.
        </Rule>
        <Rule title="Changes">
          Features and policies may change over time. We’ll keep the site updated with the latest info.
        </Rule>
        <Rule title="Data handling">
          We store minimal operational data for LFG (see Privacy). You’re responsible for any content you post.
        </Rule>
        <Rule title="Contact">
          For issues, moderation concerns, or takedowns, contact server owners or the maintainers listed on the site.
        </Rule>
      </section>

      {/* footer note */}
      <section className="mt-10 rounded-2xl border border-white/10 bg-zinc-900/60 p-6 text-white/70">
        By using the bot, you agree to these terms. If you cannot agree, please remove the bot from your server.
      </section>
    </div>
  );
}

function Rule({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <h3 className="text-sm font-semibold tracking-wide">{title}</h3>
      <p className="mt-2 text-white/80">{children}</p>
    </div>
  );
}
