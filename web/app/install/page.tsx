import CTAInvite from "@/components/CTAInvite";

export default function Install() {
  return (
    <div className="prose prose-invert max-w-none">
      <h1>Install & Setup</h1>
      <ol>
        <li><CTAInvite /></li>
        <li>In your server, choose a channel for LFG.</li>
        <li>Run <code>/lfg_channel_set #channel</code> (admin).</li>
        <li>Players run <code>/lfg_ad post</code> (e.g., <code>game: Valorant</code>).</li>
        <li>Others click <strong>I’m interested</strong>; both users are DM’d.</li>
      </ol>
      <p className="mt-6 text-sm opacity-70">
        Note: This site invites the <strong>production</strong> bot only. Premium/staging will be announced later.
      </p>
      <h2>Troubleshooting</h2>
      <ul>
        <li>Ensure the bot can send messages & embeds in the LFG channel.</li>
        <li>If the button says the ad isn’t active, it was already claimed or closed.</li>
      </ul>
    </div>
  );
}