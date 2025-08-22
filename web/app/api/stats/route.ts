import { NextResponse } from "next/server";

const toNum = (v: unknown, fallback = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    let payload = {
      servers: toNum(process.env.NEXT_PUBLIC_SEED_STATS_GUILDS),
      ads_posted: toNum(process.env.NEXT_PUBLIC_SEED_STATS_ADS),
      connections_made: toNum(process.env.NEXT_PUBLIC_SEED_STATS_CONNECTIONS),
      matches_made: toNum(process.env.NEXT_PUBLIC_SEED_STATS_MATCHES),
      bot_start_time: process.env.NEXT_PUBLIC_SEED_STATS_STARTED_AT || "",
      uptime_seconds: toNum(process.env.NEXT_PUBLIC_SEED_STATS_UPTIME),
    };

    const METRICS_URL = process.env.STATS_SOURCE_URL;
    if (METRICS_URL) {
      const r = await fetch(METRICS_URL, { cache: "no-store" });
      if (r.ok) {
        const m = await r.json();
        payload = {
          servers: toNum(m.servers ?? m.guilds, payload.servers),
          ads_posted: toNum(m.ads_posted ?? m.lfgAdsPosted, payload.ads_posted),
          connections_made: toNum(m.connections_made ?? m.matches_made, payload.connections_made),
          matches_made: toNum(m.matches_made ?? m.connections_made, payload.matches_made),
          bot_start_time: m.bot_start_time ?? m.startedAt ?? payload.bot_start_time,
          uptime_seconds: toNum(m.uptime_seconds ?? m.uptime, payload.uptime_seconds),
        };
      }
    }

    return NextResponse.json({ ok: true, ...payload, updated_at: new Date().toISOString() });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        error: "STATS_API_ERROR",
        message: err instanceof Error ? err.message : "Unknown error",
      },
      { status: 200 }
    );
  }
}
