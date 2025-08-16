export default function FeatureCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900 p-6">
      <h3 className="mb-2 text-lg font-semibold">{title}</h3>
      <p className="opacity-80">{desc}</p>
    </div>
  );
}