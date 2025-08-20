"use client";
import { motion } from "framer-motion";
import AnimatedBackground from "./AnimatedBackground";
import Link from "next/link";

export default function Hero() {
  return (
    <section className="relative border-b border-neutral-900">
      <AnimatedBackground />
      <div className="mx-auto max-w-7xl px-4 py-20 md:py-28">
        <div className="grid md:grid-cols-2 items-center gap-10">
          <div className="space-y-6">
            <motion.h1
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="text-4xl md:text-6xl font-extrabold tracking-tight"
            >
              Find teammates in seconds.
              <span className="block text-indigo-400">For devs & gamers.</span>
            </motion.h1>

            <motion.p
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: 0, opacity: 1, transition: { delay: 0.1 } }}
              className="text-neutral-300 md:text-lg max-w-prose"
            >
              Matchmaker Bot connects players across servers with clean LFG posts, smart filters, and DM connects — all without clutter.
            </motion.p>

            <motion.div
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: 0, opacity: 1, transition: { delay: 0.2 } }}
              className="flex flex-wrap items-center gap-3"
            >
              <a
                href="/api/invite"
                className="rounded-xl px-5 py-3 bg-indigo-500 hover:bg-indigo-400 transition font-medium"
              >
                Add to Discord
              </a>
              <Link
                href="#how"
                className="rounded-xl px-5 py-3 border border-neutral-700 hover:border-neutral-500 transition"
              >
                How it works
              </Link>
            </motion.div>

            <div className="pt-4 text-sm text-neutral-400">
              No spam. No clutter. Just better matches.
            </div>
          </div>

          <motion.div
            initial={{ scale: 0.98, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="relative rounded-2xl border border-neutral-800 bg-neutral-900/60 p-6 shadow-xl"
          >
            {/* Hero visual: compact mock of an LFG card */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="font-semibold">/lfg post</div>
                <span className="text-xs text-neutral-400">public</span>
              </div>
              <div className="rounded-xl bg-neutral-800/60 p-4">
                <div className="text-sm text-neutral-300">
                  <span className="text-emerald-400 font-semibold">Valorant</span> — Need 2 for ranked, VC preferred.
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <div className="text-xs text-neutral-400">by @neo • 2m ago</div>
                  <button className="rounded-lg px-3 py-1.5 bg-emerald-600/80 hover:bg-emerald-500 text-sm">
                    Connect
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center text-xs">
                <div className="rounded-lg bg-neutral-800/60 p-3">
                  <div className="text-neutral-200 font-semibold">1.2k</div>
                  <div className="text-neutral-500">matches</div>
                </div>
                <div className="rounded-lg bg-neutral-800/60 p-3">
                  <div className="text-neutral-200 font-semibold">350+</div>
                  <div className="text-neutral-500">servers</div>
                </div>
                <div className="rounded-lg bg-neutral-800/60 p-3">
                  <div className="text-neutral-200 font-semibold">24/7</div>
                  <div className="text-neutral-500">uptime</div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
