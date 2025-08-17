import CTAInvite from "@/components/CTAInvite";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Install() {
  const isStaging = process.env.NEXT_PUBLIC_ENV === "staging";
  const envBadge = isStaging ? (
    <span className="ms-2 rounded-md border border-yellow-400/30 bg-yellow-500/10 px-2 py-0.5 text-xs text-yellow-200">
      STAGING
    </span>
  ) : null;

  return (
    <div className="relative">
      {/* background accent */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-indigo-500/25 via-indigo-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="mb-10 text-center">
        <h1 className="text-4xl font-extrabold tracking-tight md:text-6xl">
          Install <span className="bg-gradient-to-r from-indigo-400 to-violet-300 bg-clip-text text-transparent">Matchmaker Bot</span>
          {envBadge}
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-white/70">
          A quick, safe setup. You’ll be posting LFG ads in under a minute.
        </p>
        <div className="mt-6 flex items-center justify-center">
          <CTAInvite />
        </div>
        <p className="mt-3 text-xs text-white/60">
          This site invites the {isStaging ? "staging" : "production"} bot.
        </p>
      </section>

      {/* stepper */}
      <section className="mx-auto w-full max-w-3xl">
        <ol className="relative space-y-6 border-s border-white/10 ps-6">
          <Step n={1} title="Add the bot">
            Click <em>Add the Bot to Your Server</em> above and finish the Discord prompt.
          </Step>
          <Step n={2} title="Choose an LFG channel">
            Pick or create a text channel where ads should be posted (e.g., <code>#lfg</code>).
          </Step>
          <Step n={3} title="Run the setup command">
            In your server, run:
            <Code>/lfg_channel_set #your-lfg-channel</Code>
            (Requires admin permissions.)
          </Step>
          <Step n={4} title="Post your first ad">
            Players can now run:
            <Code>/lfg_ad post game: Valorant</Code>
            Others click <b>I’m interested</b> — both sides are DM’d to coordinate.
          </Step>
        </ol>
      </section>

      {/* tips */}
      <section className="mt-12 grid gap-6 md:grid-cols-2">
        <Tip title="Permissions">
          Ensure the bot can <b>Send Messages</b> and <b>Embed Links</b> in the LFG channel.
        </Tip>
        <Tip title="Not active?">
          If a button says the ad isn’t active, it’s already been claimed or closed.
        </Tip>
      </section>
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="group">
      <span className="absolute -start-3 mt-1.5 inline-flex h-6 w-6 items-center justify-center rounded-full border border-indigo-400/40 bg-indigo-500/20 text-xs font-semibold text-indigo-200">
        {n}
      </span>
      <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-5 shadow-sm shadow-black/20 transition-colors group-hover:border-white/20">
        <h3 className="text-sm font-semibold tracking-wide text-white">{title}</h3>
        <div className="mt-2 text-white/80">{children}</div>
      </div>
    </li>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="mt-2 overflow-x-auto rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white/90">
      <code>{children}</code>
    </pre>
  );
}

function Tip({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <h4 className="text-sm font-semibold">{title}</h4>
      <p className="mt-2 text-white/75">{children}</p>
    </div>
  );
}
