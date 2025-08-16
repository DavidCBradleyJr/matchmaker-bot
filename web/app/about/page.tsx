export default function About() {
  return (
    <div className="prose prose-invert max-w-none">
      <h1>About the Bot</h1>
      <p>
        Matchmaker Bot helps gamers find teammates quickly using broadcast LFG posts and a
        one-click Connect flow that DM’s both sides. Built with Python and discord.py.
      </p>
      <h2>Core Features</h2>
      <ul>
        <li>Broadcast LFG posts to each server’s configured channel</li>
        <li>Connect button DMs both players to coordinate</li>
        <li>Admin command to set the LFG channel</li>
      </ul>
    </div>
  );
}