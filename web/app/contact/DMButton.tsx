"use client";

export default function DMButton({ userId }: { userId: string }) {
  function openDM(id: string) {
    const appLink = `discord://-/users/${id}`;
    const webLink = `https://discord.com/users/${id}`;
    const start = Date.now();

    // Try opening the app; if it doesn't switch focus quickly, fall back to web.
    const fallback = setTimeout(() => {
      if (Date.now() - start < 1500) {
        window.open(webLink, "_blank");
      }
    }, 500);

    window.location.href = appLink;
    setTimeout(() => clearTimeout(fallback), 2000);
  }

  return (
    <a
      href={`https://discord.com/users/${userId}`}
      onClick={(e) => {
        e.preventDefault();
        openDM(userId);
      }}
      aria-label="Open direct message with owner"
      className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium hover:bg-white/10"
    >
      Open Discord
    </a>
  );
}
