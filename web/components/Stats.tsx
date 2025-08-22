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
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default async function Stats() {
  let data: Stats | null = null;

  try {
    const res = await fetch(`/api/stats`, { cache: "no-store" });
    const json = await res.json();

    // Normalize alternative shapes so UI never blanks
    data = {
      ok: Boolean(json?.ok ?? true),
      servers: json?.servers ?? json?.guilds ?? 0,
      ads_posted: json?.ads_posted ?? json?.lfgAdsPosted ?? 0,
      connections_made: json?.connections_made ?? json?.matches_made ?? 0,
      matches_made: json?.matches_made ?? json?.connections_made ?? 0,
      bot_start_time: json?.bot_start_time ?? json?.startedAt ?? "",
      uptime_seconds: Number(json?.uptime_seconds ?? json?.uptime ?? 0),
    };
  } catch {
    data = null;
  }

  if (!data || data.ok === false) {
    return (
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-sm text-neutral-400">
        Couldn’t load live stats right now. Try again shortly.
      </div>
    );
  }

  const items = [
    { label: "Servers", value: fmt(data.servers) },
    { label: "Ads posted", value: fmt(data.ads_posted) },
    { label: "Connections", value: fmt(data.connections_made) },
    { label: "Uptime", value: fmtUptime(Number(data.uptime_seconds || 0)) },
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
