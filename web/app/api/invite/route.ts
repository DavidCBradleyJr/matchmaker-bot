import { NextResponse, NextRequest } from "next/server";

function pickClientId(host?: string | null): string | null {
  const h = (host || "").toLowerCase();

  // Heuristic for staging; tighten if you have exact hostnames.
  const isStaging =
    h.includes("staging") || h.startsWith("stg.") || h.includes("-staging");

  const prodId =
    process.env.PROD_DISCORD_CLIENT_ID ||
    process.env.NEXT_PUBLIC_PROD_DISCORD_CLIENT_ID ||
    null;

  const stagingId =
    process.env.STAGING_DISCORD_CLIENT_ID ||
    process.env.NEXT_PUBLIC_STAGING_DISCORD_CLIENT_ID ||
    null;

  if (isStaging && stagingId) return stagingId;
  if (!isStaging && prodId) return prodId;

  return process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID || null;
}

export function GET(req: NextRequest) {
  const host = req.headers.get("host");
  const clientId = pickClientId(host);
  if (!clientId) {
    return NextResponse.json(
      { error: "Missing Discord client id for this environment." },
      { status: 500 }
    );
  }

  // Accept optional passthrough params from the site (e.g., permissions/redirect_uri)
  const incoming = req.nextUrl.searchParams;
  const permissions = incoming.get("permissions") ?? undefined;
  const redirectUri = incoming.get("redirect_uri") ?? undefined;

  const url = new URL("https://discord.com/oauth2/authorize");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("scope", "bot applications.commands");
  if (permissions) url.searchParams.set("permissions", permissions);
  if (redirectUri) url.searchParams.set("redirect_uri", redirectUri);

  return NextResponse.redirect(url.toString(), { status: 307 });
}
