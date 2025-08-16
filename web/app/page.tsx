import CTAInvite from "@/components/CTAInvite";
import FeatureCard from "@/components/FeatureCard";

export default function Home() {
  const name = process.env.NEXT_PUBLIC_SITE_NAME || "Matchmaker Bot";
  const tagline = process.env.NEXT_PUBLIC_TAGLINE || "Find teammates. Fast.";
  return (
    <div className="space-y-12">
      <section className="space-y-6 pt-6 text-center">
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight">{name}</h1>
        <p className="mx-auto max-w-2xl opacity-80">{tagline}</p>
        <div className="flex items-center justify-center gap-4">
          <CTAInvite />
          <a href="/install" className="rounded-xl border border-white/10 px-5 py-3 hover:bg-white/5">
            How it works
          </a>
        </div>
        <p className="text-xs opacity-60">This site invites the <b>production</b> bot only.</p>
      </section>

      <section className="grid gap-6 md:grid-cols-3">
        <FeatureCard title="Cross-Guild LFG Broadcasts" desc="Post once, reach every configured server’s LFG channel." />
        <FeatureCard title="One-Click Connect" desc="Players tap a button; both parties are DM’d to coordinate." />
        <FeatureCard title="Admin Controls" desc="Per-guild LFG channel, sane defaults, permission-aware." />
      </section>
    </div>
  );
}