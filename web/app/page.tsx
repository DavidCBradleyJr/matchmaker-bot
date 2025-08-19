// web/app/page.tsx
"use client";

import { motion } from "motion/react"; // if not installed, `npm i motion`
import Link from "next/link";

export default function Page() {
  return (
    <main className="relative overflow-hidden">
      {/* subtle background */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(900px_500px_at_50%_-10%,rgba(99,102,241,0.16),transparent_60%)] dark:bg-[radial-gradient(900px_500px_at_50%_-10%,rgba(99,102,241,0.12),transparent_60%)]" />
        <div className="absolute inset-0 opacity-[0.08] mix-blend-soft-light [background-image:repeating-linear-gradient(0deg,rgba(255,255,255,0.06)_0px,rgba(255,255,255,0.06)_1px,transparent_1px,transparent_2px)] dark:opacity-[0.06]" />
      </div>

      <section className="mx-auto max-w-6xl px-6 py-20 md:py-28">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mx-auto max-w-2xl text-center"
        >
          <span className="inline-flex items-center justify-center rounded-full border border-border/60 bg-background/60 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur-sm">
            Minimal. Fast. Discord‑native.
          </span>

          <h1 className="mt-5 text-balance text-4xl font-semibold tracking-tight md:text-5xl">
            Find teammates <span className="text-primary">instantly</span>.
          </h1>

          <p className="mx-auto mt-4 max-w-xl text-pretty text-base text-muted-foreground">
            Post once. We broadcast to your channels. Players connect via polished DMs—no clutter.
          </p>

          <div className="mt-8 flex items-center justify-center gap-3">
            <Link
              href="/invite"
              className="rounded-2xl bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm hover:opacity-90"
            >
              Add to Discord
            </Link>
            <a
              href="https://github.com/DavidCBradleyJr/matchmaker-bot"
              target="_blank"
              rel="noreferrer"
              className="rounded-2xl px-5 py-3 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              View code →
            </a>
          </div>

          <div className="mt-6 text-xs text-muted-foreground">
            Trusted by servers who hate spammy LFGs.
          </div>
        </motion.div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="grid gap-4 md:grid-cols-3">
          {[
            ["Post", "Create a single LFG ad from any server."],
            ["Broadcast", "We deliver it to your chosen channels."],
            ["Connect", "Players click once; bot opens polished DMs."],
          ].map(([title, text]) => (
            <div key={title} className="rounded-2xl border bg-background/60 p-6">
              <h3 className="text-base font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6 text-xs text-muted-foreground">
          <span>© {new Date().getFullYear()} Matchmaker</span>
          <span className="flex items-center gap-3">
            <a className="hover:text-foreground" href="/privacy">Privacy</a>
            <a className="hover:text-foreground" href="/terms">Terms</a>
          </span>
        </div>
      </footer>
    </main>
  );
}
