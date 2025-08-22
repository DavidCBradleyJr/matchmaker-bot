// web/app/api/stats/route.ts
import { NextResponse } from "next/server";

type Stats = {
  guilds: number;
  lfgAdsPosted: number;
  connectionsMade: number;
  activeServersToday: number;
  updatedAt: string; // ISO
};

const parseNum = (v: string | undefined): number =>
  v && !Number.isNaN(Number(v)) ? Number(v) : 0;

export async function GET() {
  try {
    const envStats: Stats = {
      guilds: parseNum(process.env.NEXT_PUBLIC_SEED_STATS_GUILDS),
      lfgAdsPosted: parseNum(process.env.NEXT_PUBLIC_SEED_STATS_ADS),
      connectionsMade: parseNum(process.env.NEXT_PUBLIC_SEED_STATS_CONNECTIONS),
      activeServersToday: parseNum(process.env.NEXT_PUBLIC_SEED_STATS_ACTIVE),
      updatedAt: new Date().toISOString(),
    };

    const METRICS_URL = process.env.STATS_SOURCE_URL;
    if (METRICS_URL) {
      const r = await fetch(METRICS_URL, { cache: "no-store" });
      if (r.ok) {
        const m = await r.json();
        envStats.guilds = Number(m.guilds ?? envStats.guilds);
        envStats.lfgAdsPosted = Number(m.lfgAdsPosted ?? envStats.lfgAdsPosted);
        envStats.connectionsMade = Number(m.connectionsMade ?? envStats.connectionsMade);
        envStats.activeServersToday = Number(m.activeServersToday ?? envStats.activeServersToday);
        envStats.updatedAt = new Date().toISOString();
      }
    }

    return NextResponse.json(envStats, { status: 200 });
  } catch (err) {
    return NextResponse.json(
      {
        error: "STATS_API_ERROR",
        message: err instanceof Error ? err.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
