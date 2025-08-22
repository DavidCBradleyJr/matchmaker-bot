import { NextResponse } from "next/server";
import { neon, neonConfig } from "@neondatabase/serverless";

/**
 * Match the project's ENV rules (same as bot/db.py):
 * - ENV starting with "stag" -> prefer STAGING_DATABASE_URL, fallback to PROD
 * - otherwise -> prefer PROD_DATABASE_URL, fallback to STAGING
 */
function resolveDsnFromEnv(): string {
  const env = (process.env.ENV || "staging").toLowerCase();
  if (env.startsWith("stag")) {
    return (
      process.env.STAGING_DATABASE_URL ||
      process.env.PROD_DATABASE_URL ||
      ""
    );
  }
  return (
    process.env.PROD_DATABASE_URL ||
    process.env.STAGING_DATABASE_URL ||
    ""
  );
}

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  try {
    const dsn = resolveDsnFromEnv();
    if (!dsn) {
      // Allow quick smoke test via seed envs if DSN is missing
      const seeded = {
        servers: Number(process.env.NEXT_PUBLIC_SEED_STATS_GUILDS || 0),
        ads_posted: Number(process.env.NEXT_PUBLIC_SEED_STATS_ADS || 0),
        connections_made: Number(process.env.NEXT_PUBLIC_SEED_STATS_CONNECTIONS || 0),
        matches_made: Number(process.env.NEXT_PUBLIC_SEED_STATS_MATCHES || 0),
        bot_start_time: String(process.env.NEXT_PUBLIC_SEED_STATS_STARTED_AT || ""),
      };
      const uptime_seconds = Number(process.env.NEXT_PUBLIC_SEED_STATS_UPTIME || 0);
      return NextResponse.json({ ok: true, ...seeded, uptime_seconds, updated_at: new Date().toISOString() });
    }

    // Neon HTTP driver works great in serverless/edge environments
    neonConfig.fetchConnectionCache = true;
    const sql = neon(dsn);

    // Mirror bot/db.py: stats_snapshot()
    const rows = await sql/*sql*/`
      SELECT
        COALESCE((SELECT COUNT(*)::int FROM bot_guilds), 0)                               AS servers,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='ads_posted'), 0)      AS ads_posted,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='connections_made'), 0)AS connections_made,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='matches_made'), 0)    AS matches_made,
        COALESCE((SELECT value::int FROM bot_counters WHERE metric='errors'), 0)          AS errors,
        COALESCE((SELECT value        FROM bot_meta     WHERE key='bot_start_time'), '')  AS bot_start_time
    `;

    const r = (rows && rows[0]) || {
      servers: 0,
      ads_posted: 0,
      connections_made: 0,
      matches_made: 0,
      errors: 0,
      bot_start_time: "",
    };

    // Compute uptime_seconds from bot_start_time (if present)
    let uptime_seconds = 0;
    if (r.bot_start_time) {
      const started = Date.parse(String(r.bot_start_time));
      if (!Number.isNaN(started)) {
        uptime_seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
      }
    }

    return NextResponse.json(
      {
        ok: true,
        servers: Number(r.servers || 0),
        ads_posted: Number(r.ads_posted || 0),
        connections_made: Number(r.connections_made || 0),
        matches_made: Number(r.matches_made || 0),
        bot_start_time: String(r.bot_start_time || ""),
        uptime_seconds,
        updated_at: new Date().toISOString(),
      },
      { status: 200 }
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: "STATS_API_ERROR", message }, { status: 200 });
  }
}
