export default function HowItWorks() {
  const steps = [
    { n: 1, title: "Add the bot", desc: "Invite with recommended perms." },
    { n: 2, title: "Set LFG channel", desc: "Owner/admin picks the channel." },
    { n: 3, title: "Post & connect", desc: "Members /lfg post, others Connect." },
  ];
  return (
    <section id="how" className="mx-auto max-w-7xl px-4 py-16 md:py-20 border-t border-neutral-900">
      <h2 className="text-2xl md:text-3xl font-bold tracking-tight">How it works</h2>
      <p className="mt-2 text-neutral-400 max-w-prose">
        Simple setup. Immediate value. Your LFG channel stays signal‑first.
      </p>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
        {steps.map((s) => (
          <div key={s.n} className="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5">
            <div className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500 text-sm font-semibold">
              {s.n}
            </div>
            <div className="mt-3 font-semibold">{s.title}</div>
            <div className="mt-1 text-sm text-neutral-400">{s.desc}</div>
          </div>
        ))}
      </div>

      <div className="mt-10">
        <a
          href="/api/invite"
          className="rounded-xl px-5 py-3 bg-indigo-500 hover:bg-indigo-400 transition font-medium text-white"
        >
          Add to Discord
        </a>
      </div>
    </section>
  );
}
