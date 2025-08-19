"use client";

import { memo, useMemo } from "react";

type Props = {
  clientId?: string;
  redirectUri?: string;
  permissions?: string;
  className?: string;
};

function CTAInviteImpl({
  clientId = process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID,
  redirectUri,
  permissions,
  className = "",
}: Props) {
  const inviteUrl = useMemo(() => {
    if (!clientId) return null;

    const params = new URLSearchParams({
      client_id: clientId,
      scope: "bot applications.commands",
    });

    if (permissions) params.set("permissions", permissions);
    if (redirectUri) params.set("redirect_uri", redirectUri);

    return `https://discord.com/oauth2/authorize?${params.toString()}`;
  }, [clientId, permissions, redirectUri]);

  if (!inviteUrl) {
    return (
      <span
        title="Missing Discord client id — set NEXT_PUBLIC_DISCORD_CLIENT_ID in .env.local"
        className={`inline-flex cursor-not-allowed select-none items-center gap-2 rounded-2xl bg-zinc-300/40 px-5 py-3 text-sm font-medium text-zinc-600 dark:bg-zinc-700/40 dark:text-zinc-300 ${className}`}
      >
        Invite (coming soon)
      </span>
    );
  }

  return (
    <a
      href={inviteUrl}
      className={`inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 ${className}`}
    >
      Add to Discord
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="h-[18px] w-[18px]"
      >
        <path
          d="M13 5l7 7-7 7M5 12h14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </a>
  );
}

const CTAInvite = memo(CTAInviteImpl);
export default CTAInvite;
