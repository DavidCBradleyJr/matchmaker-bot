export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function Contact() {
  return (
    <div className="relative">
      {/* background accent */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-indigo-500/25 via-indigo-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="mb-10 text-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
          Support • Get in touch
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight md:text-6xl">
          Contact <span className="bg-gradient-to-r from-indigo-400 to-violet-300 bg-clip-text text-transparent">Us</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-white/70">
          Whether you need help, want to report an issue, or just have feedback — we’re here for you.
        </p>
      </section>

      {/* cards */}
      <section className="grid gap-6 md:grid-cols-2">
        <Card
          title="Discord DM"
          description="Reach out directly on Discord."
          actionLabel="Message devdeej"
          href="https://discord.com/users/devdeej"
        />
        <Card
          title="Support Server"
          description="Join our official Discord server to get help, report bugs, or share suggestions."
          actionLabel="Join server"
          href="https://discord.gg/7Cersw2kqv"
        />
      </section>

      {/* faq style section */}
      <section className="mt-12 rounded-2xl border border-white/10 bg-zinc-900/60 p-6">
        <h2 className="mb-3 text-2xl font-semibold">Common reasons to contact us</h2>
        <ul className="space-y-3 text-white/80">
          <li className="flex gap-3"><Dot /> Reporting a bug with the bot or site</li>
          <li className="flex gap-3"><Dot /> Asking about premium features or staging bot access</li>
          <li className="flex gap-3"><Dot /> Requesting removal of data (ads, server configs)</li>
          <li className="flex gap-3"><Dot /> General feedback or feature suggestions</li>
        </ul>
      </section>
    </div>
  );
}

function Card({
  title,
  description,
  actionLabel,
  href,
}: {
  title: string;
  description: string;
  actionLabel: string;
  href: string;
}) {
  return (
    <div className="flex flex-col justify-between rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mt-2 text-white/75">{description}</p>
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-6 inline-flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
      >
        {actionLabel}
      </a>
    </div>
  );
}

function Dot() {
  return <span className="mt-2 inline-block h-2 w-2 flex-none rounded-full bg-indigo-400" />;
}