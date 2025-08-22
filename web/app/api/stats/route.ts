import { NextResponse } from "next/server";
import { neon, neonConfig } from "@neondatabase/serverless";

function resolveDsn(): string {
  const env = (process.env.ENV || "staging").toLowerCase();
  if (env.startsWith("stag")) {
    return process.env.STAGING_DATABASE_URL || process.env.PROD_DATABASE_URL || "";
  }
  return process.env.PROD_DATABASE_URL || process.env.STAGING_DATABASE_URL || "";
}

const toNum = (v: unknown, fallback = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const dsn = resolveDsn();

  try {
    if (!dsn) {
      // No DSN → use seeds so the UI still shows something
      return NextResponse.json({
        ok: true,
        source: "missing_dsn",
        servers: toNum(process.env.NEXT_PUBLIC_SEED_STATS_GUILDS, 0),
        ads_posted: toNum(process.env.NEXT_PUBLIC_SEED_STATS_ADS, 0),
        connections_made: toNum(process.env.NEXT_PUBLIC_SEED_STATS_CONNECTIONS, 0),
        matches_made: toNum(process.env.NEXT_PUBLIC_SEED_STATS_MATCHES, 0),
        bot_start_time: String(process.env.NEXT_PUBLIC_SEED_STATS_STARTED_AT || ""),
        uptime_seconds: toNum(process.env.NEXT_PUBLIC_SEED_STATS_UPTIME, 0),
        updated_at: new Date().toISOString(),
      });
    }

    neonConfig.fetchConnectionCache = true;
    const sql = neon(dsn);

    const rows = await sql/*sql*/`
      SELECT
        COALESCE((SELECT COUNT(*)::int FROM bot_guilds), 0)                               AS servers,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='ads_posted'), 0)      AS ads_posted,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='connections_made'), 0)AS connections_made,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='matches_made'), 0)    AS matches_made,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='errors'), 0)          AS errors,
        COALESCE((SELECT value        FROM bot_meta     WHERE key='bot_start_time'), '')  AS bot_start_time
    `;

    const r = rows?.[0] ?? {
      servers: 0, ads_posted: 0, connections_made: 0, matches_made: 0, bot_start_time: "",
    };

    let uptime_seconds = 0;
    if (r.bot_start_time) {
      const started = Date.parse(String(r.bot_start_time));
      if (!Number.isNaN(started)) uptime_seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
    }

    return NextResponse.json({
      ok: true,
      source: "neon",
      servers: toNum(r.servers, 0),
      ads_posted: toNum(r.ads_posted, 0),
      connections_made: toNum(r.connections_made, 0),
      matches_made: toNum(r.matches_made, 0),
      bot_start_time: String(r.bot_start_time || ""),
      uptime_seconds,
      updated_at: new Date().toISOString(),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    // On query error, don’t silently show seeds; surface the problem
    return NextResponse.json({ ok: false, source: "query_error", error: "STATS_API_ERROR", message: msg }, { status: 200 });
  }
}
