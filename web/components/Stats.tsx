"use client";

import { useEffect, useState } from "react";

type Stats = {
  ok: boolean;
  servers: number | string;
  ads_posted: number | string;
  connections_made: number | string;
  matches_made: number | string;
  bot_start_time: string;
  uptime_seconds: number;
};

function fmt(n: number | string) {
  const num = typeof n === "string" ? Number(n) : n;
  return new Intl.NumberFormat().format(Number.isFinite(num) ? (num as number) : 0);
}
function fmtUptime(s: number) {
  const sec = Number.isFinite(s) ? s : 0;
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h`;
  return `${Math.floor((sec % 3600) / 60)}m`;
}

export default function Stats() {
  const [data, setData] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // NEW: ticking "clock" so uptime updates without reloading
  const [nowSec, setNowSec] = useState<number>(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const id = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 60_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/stats", { cache: "no-store" });
        const json = await res.json();
        if (!res.ok || json?.ok === false) throw new Error("Stats unavailable");
        setData({
          ok: Boolean(json.ok ?? true),
          servers: json.servers ?? json.guilds ?? 0,
          ads_posted: json.ads_posted ?? json.lfgAdsPosted ?? 0,
          connections_made: json.connections_made ?? json.matches_made ?? 0,
          matches_made: json.matches_made ?? json.connections_made ?? 0,
          bot_start_time: json.bot_start_time ?? json.startedAt ?? "",
          uptime_seconds: Number(json.uptime_seconds ?? json.uptime ?? 0),
        });
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg bg-neutral-800/60 p-3 text-center">
            <div className="h-6 w-16 mx-auto bg-neutral-700 rounded mb-1" />
            <div className="h-3 w-20 mx-auto bg-neutral-700/80 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (!data || error) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400">
        Couldn’t load stats. Try again later.
      </div>
    );
  }

  // Derived uptime from bot_start_time (fallback to API uptime_seconds)
  const startEpoch = Number(data.bot_start_time ?? 0);
  const derivedUptime =
    Number.isFinite(startEpoch) && startEpoch > 0
      ? Math.max(0, nowSec - Math.floor(startEpoch))
      : Number(data.uptime_seconds || 0);

  const items = [
    { label: "Servers", value: fmt(data.servers) },
    { label: "Ads posted", value: fmt(data.ads_posted) },
    { label: "Connections", value: fmt(data.connections_made) },
    { label: "Uptime", value: fmtUptime(derivedUptime) },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {items.map((it) => (
        <div key={it.label} className="rounded-lg bg-neutral-800/60 p-3 text-center">
          <div className="text-neutral-200 font-semibold">{it.value}</div>
          <div className="text-neutral-500 text-xs">{it.label}</div>
        </div>
      ))}
    </div>
  );
}
