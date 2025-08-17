"use client";

export const dynamic = "force-dynamic";
export const revalidate = 0;

import { MessageSquare, Users } from "lucide-react";

/**
 * Attempts to open the Discord app to a user's profile, falling back to the web profile.
 * The web profile includes a "Message" button to start a DM.
 */
function openDM(userId: string) {
  const appLink = `discord://-/users/${userId}`;
  const webLink = `https://discord.com/users/${userId}`;
  const start = Date.now();

  // Try opening the app; if it doesn't switch focus quickly, fall back to web.
  const fallback = setTimeout(() => {
    if (Date.now() - start < 1500) {
      window.open(webLink, "_blank");
    }
  }, 500);

  window.location.href = appLink;
  setTimeout(() => clearTimeout(fallback), 2000);
}

export default function ContactPage() {
  return (
    <div className="relative space-y-10">
      {/* background accent (match other pages) */}
      <div className="pointer-events-none absolute inset-x-0 -top-24 -z-10 h-64 bg-gradient-to-b from-indigo-500/25 via-indigo-500/10 to-transparent blur-3xl" />

      {/* hero */}
      <section className="text-center">
        <span className="inline-flex items-center gap-2 rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70">
          Support • Discord-first
        </span>
        <h1 className="mt-6 text-4xl font-extrabold tracking-tight md:text-6xl">
          Contact
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-white/75">
          Need help, want to share feedback, or just want to chat? The fastest way to reach us is on Discord.
        </p>
      </section>

      {/* cards */}
      <section className="grid gap-6 md:grid-cols-2">
        <ContactCard
          icon={<Users className="h-5 w-5" />}
          title="Community Support (Discord)"
          body="Join our server to ask questions, suggest features, and see announcements."
        >
          <a
            href="https://discord.gg/7Cersw2kqv"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium hover:bg-white/10"
          >
            Join Server
          </a>
        </ContactCard>

        <ContactCard
          icon={<MessageSquare className="h-5 w-5" />}
          title="Direct DM Support"
          body="Prefer a direct chat? DM the bot owner after joining; we’ll get back as soon as we can."
          foot="Availability may vary by timezone."
        >
          <a
            href="https://discord.com/users/154593850185351168"
            onClick={(e) => {
              e.preventDefault();
              openDM("154593850185351168");
            }}
            aria-label="Open direct message with owner"
            className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium hover:bg-white/10"
          >
            Open Discord
          </a>
        </ContactCard>
      </section>
    </div>
  );
}

function ContactCard({
  icon,
  title,
  body,
  foot,
  children
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  foot?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/60 p-6 shadow-sm shadow-black/20">
      <div className="flex items-center gap-2 text-white/80">
        {icon}
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      <p className="mt-2 text-white/75">{body}</p>
      {children ? <div className="mt-4">{children}</div> : null}
      {foot ? <p className="mt-4 text-xs text-white/50">{foot}</p> : null}
    </div>
  );
}
