import { NextResponse, NextRequest } from "next/server";

function pickClientId(host?: string | null): string | null {
  const h = (host || "").toLowerCase();
  const isStaging = h.includes("staging") || h.startsWith("stg.") || h.includes("-staging");

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
  const clientId = pickClientId(req.headers.get("host"));
  if (!clientId) {
    return NextResponse.json(
      { error: "Missing Discord client id for this environment." },
      { status: 500 }
    );
  }

  const scope = "bot%20applications.commands";
  const url = `https://discord.com/oauth2/authorize?client_id=${clientId}&scope=${scope}`;
  return NextResponse.redirect(url, { status: 307 });
}
