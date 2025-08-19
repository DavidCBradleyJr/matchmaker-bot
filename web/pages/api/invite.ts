import type { NextApiRequest, NextApiResponse } from "next";

function pickClientId(host?: string): string | null {
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

  // Last resort: single var setup
  return process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID || null;
}

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  const clientId = pickClientId(req.headers.host);
  if (!clientId) {
    res.status(500).json({ error: "Missing Discord client id for this environment." });
    return;
  }

  const scope = "bot%20applications.commands"; // keep encoded
  const url = `https://discord.com/oauth2/authorize?client_id=${clientId}&scope=${scope}`;

  res.setHeader("Location", url);
  res.status(307).end();
}
