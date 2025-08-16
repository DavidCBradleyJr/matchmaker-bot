export const dynamic = 'force-dynamic'; // render at runtime, not during build
export const revalidate = 0;

export default function CTAInvite() {
  const env   = process.env.NEXT_PUBLIC_ENV || 'production';
  const cid   = process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID;
  const scope = process.env.NEXT_PUBLIC_DISCORD_SCOPES || 'bot%20applications.commands';
  const perms = process.env.NEXT_PUBLIC_DISCORD_PERMISSIONS || '274877991936';

  const inviteUrl = cid
    ? `https://discord.com/api/oauth2/authorize?client_id=${cid}&permissions=${perms}&scope=${scope}`
    : null;

  return (
    <div className="inline-flex items-center gap-3">
      {inviteUrl ? (
        <a
          href={inviteUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center rounded-xl border border-indigo-400/30 bg-indigo-500/20 px-5 py-3 text-indigo-200 hover:bg-indigo-500/30"
        >
          Add the Bot to Your Server
        </a>
      ) : (
        <span className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm">
          Invite unavailable (missing client id)
        </span>
      )}

      {env === 'staging' && (
        <span className="rounded-md border border-yellow-400/30 bg-yellow-500/10 px-2 py-1 text-xs text-yellow-200">
          STAGING
        </span>
      )}
    </div>
  );
}
