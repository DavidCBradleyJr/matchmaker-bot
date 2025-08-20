import { NextResponse } from "next/server";
import { Pool } from "pg";

function resolveDsn() {
  const env = (process.env.ENV || "staging").toLowerCase();
  if (env.startsWith("stag")) {
    return process.env.STAGING_DATABASE_URL || process.env.PROD_DATABASE_URL;
  }
  return process.env.PROD_DATABASE_URL || process.env.STAGING_DATABASE_URL;
}

let pool: Pool | null = null;
function getPool() {
  if (!pool) {
    const dsn = resolveDsn();
    if (!dsn) return null;
    pool = new Pool({ connectionString: dsn, ssl: { rejectUnauthorized: false }, max: 3 });
  }
  return pool;
}

// Force Node runtime (pg requires it)
export const runtime = "nodejs";

export async function GET() {
  try {
    const p = getPool();
    if (!p) {
      return NextResponse.json({ ok: false, error: "Database not configured" }, { status: 500 });
    }
    const { rows } = await p.query(`
      SELECT
        (SELECT COUNT(*)::bigint FROM bot_guilds) AS servers,
        COALESCE((SELECT value FROM bot_counters WHERE metric='ads_posted'),0)::bigint AS ads_posted,
        COALESCE((SELECT value FROM bot_counters WHERE metric='connections_made'),0)::bigint AS connections_made,
        COALESCE((SELECT value FROM bot_counters WHERE metric='matches_made'),0)::bigint AS matches_made,
        COALESCE((SELECT value FROM bot_meta WHERE key='bot_start_time'),'') AS bot_start_time
    `);
    const data = rows[0] || {
      servers: 0, ads_posted: 0, connections_made: 0, matches_made: 0, bot_start_time: ""
    };

    let uptime_seconds = 0;
    if (data.bot_start_time) {
      const started = Date.parse(data.bot_start_time as string);
      if (!Number.isNaN(started)) {
        uptime_seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
      }
    }

    return NextResponse.json({ ok: true, ...data, uptime_seconds }, { headers: { "Cache-Control": "no-store" } });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message ?? "Unknown error" }, { status: 500 });
  }
}
