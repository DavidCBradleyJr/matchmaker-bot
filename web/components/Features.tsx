export default function Features() {
  const items = [
    { title: "Clean LFG posts", desc: "Short, scannable ads with Connect buttons.", icon: "🧭" },
    { title: "Owner controls", desc: "Choose the LFG channel. Keep your server tidy.", icon: "🛡️" },
    { title: "DM connect", desc: "One click to privately connect with the poster.", icon: "📨" },
    { title: "Built for scale", desc: "Fast, reliable, and ready for bigger queues.", icon: "⚡" },
  ];
  return (
    <section id="features" className="mx-auto max-w-7xl px-4 py-16 md:py-20">
      <h2 className="text-2xl md:text-3xl font-bold tracking-tight">Features</h2>
      <p className="mt-2 text-neutral-400 max-w-prose">
        Everything you need to find teammates faster and keep channels clean.
      </p>

      <div className="mt-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {items.map((it) => (
          <div
            key={it.title}
            className="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5 hover:border-neutral-700 transition"
          >
            <div className="text-2xl">{it.icon}</div>
            <div className="mt-3 font-semibold">{it.title}</div>
            <div className="mt-1 text-sm text-neutral-400">{it.desc}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
