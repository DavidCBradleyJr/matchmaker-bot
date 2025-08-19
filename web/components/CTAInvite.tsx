"use client";

import { memo, useMemo } from "react";

type Props = {
  permissions?: string;
  redirectUri?: string;
  className?: string;
};

function CTAInviteImpl({
  permissions,
  redirectUri,
  className = "",
}: Props) {
  const inviteUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (permissions) params.set("permissions", permissions);
    if (redirectUri) params.set("redirect_uri", redirectUri);
    const qs = params.toString();
    return `/api/invite${qs ? `?${qs}` : ""}`;
  }, [permissions, redirectUri]);

  return (
    <a
      href={inviteUrl}
      className={`inline-flex items-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 ${className}`}
    >
      Add to Discord
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[18px] w-[18px]">
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

export default memo(CTAInviteImpl);
