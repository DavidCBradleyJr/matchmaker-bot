type Stats = {
  ok: boolean;
  servers: number;
  ads_posted: number;
  connections_made: number;
  matches_made: number;
  bot_start_time: string;
  uptime_seconds: number;
};

function fmt(n: number) {
  return new Intl.NumberFormat().format(n);
}
function fmtUptime(s: number) {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

export default async function Stats() {
  const base = process.env.NEXT_PUBLIC_BASE_URL || "";
  const res = await fetch(`${base}/api/stats`, { cache: "no-store" });
  const data = (await res.json()) as Stats;

  if (!data.ok) return null;

  const items = [
    { label: "Servers", value: fmt(Number(data.servers || 0)) },
    { label: "Ads posted", value: fmt(Number(data.ads_posted || 0)) },
    { label: "Connections", value: fmt(Number(data.connections_made || 0)) },
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
