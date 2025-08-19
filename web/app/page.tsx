"use client";

import { motion } from "motion/react";
import CTAInvite from "@/components/CTAInvite";
import FeatureCard from "@/components/FeatureCard";

export default function Page() {
  return (
    <div className="relative overflow-hidden">
      {/* Subtle background */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(900px_500px_at_50%_-10%,rgba(99,102,241,0.16),transparent_60%)] dark:bg-[radial-gradient(900px_500px_at_50%_-10%,rgba(99,102,241,0.12),transparent_60%)]" />
        <div className="absolute inset-0 opacity-[0.08] mix-blend-soft-light [background-image:repeating-linear-gradient(0deg,rgba(255,255,255,0.06)_0px,rgba(255,255,255,0.06)_1px,transparent_1px,transparent_2px)] dark:opacity-[0.06]" />
      </div>

      {/* Hero */}
      <section className="px-4 py-16 md:py-24">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mx-auto max-w-3xl text-center"
        >
          <span className="inline-flex items-center justify-center rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-zinc-300/80 backdrop-blur-sm">
            Minimal. Fast. Discord‑native.
          </span>

          <h1 className="mt-5 text-balance text-4xl font-semibold tracking-tight md:text-5xl">
            Find teammates <span className="text-indigo-400">instantly</span>.
          </h1>

          <p className="mx-auto mt-4 max-w-xl text-pretty text-base text-zinc-300/90">
            Post once. We broadcast to your channels. Players connect via polished DMs—no clutter.
          </p>

          <div className="mt-8 flex items-center justify-center">
            <CTAInvite />
          </div>

          <div className="mt-6 text-xs text-zinc-400/80">
            Trusted by servers who hate spammy LFGs.
          </div>
        </motion.div>
      </section>

      {/* How it works */}
      <section className="px-4 pb-12">
        <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-3">
          <FeatureCard title="Post" desc="Create a single LFG ad from any server." />
          <FeatureCard title="Broadcast" desc="We deliver it to your chosen channels." />
          <FeatureCard title="Connect" desc="Players click once; bot opens polished DMs." />
        </div>
      </section>
    </div>
  );
}
