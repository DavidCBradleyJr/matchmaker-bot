export default function CTA() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 md:py-20">
      <div className="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-8 md:p-10 text-center">
        <h3 className="text-xl md:text-2xl font-bold tracking-tight">
          Ready to build your squad?
        </h3>
        <p className="mt-2 text-neutral-400">
          Add Matchmaker Bot to your server and start connecting in seconds.
        </p>
        <div className="mt-6">
          <a
            href="/api/invite"
            className="inline-block rounded-xl px-5 py-3 bg-indigo-500 hover:bg-indigo-400 transition font-medium"
          >
            Add to Discord
          </a>
        </div>
      </div>
    </section>
  );
}
