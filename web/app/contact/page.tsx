"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Mail, MessageCircle, Users } from "lucide-react";

export default function ContactPage() {
  // devdeej's Discord user ID — replace with your actual ID
  const DISCORD_USER_ID = "154593850185351168";
  const DISCORD_SERVER_URL = "https://discord.gg/7Cersw2kqv";

  const handleDiscordClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();

    // Attempt to open the Discord app
    window.location.href = `discord://discord.com/users/${DISCORD_USER_ID}`;

    // Fallback to web after a short delay if the app doesn't open
    setTimeout(() => {
      window.location.href = `https://discord.com/users/${DISCORD_USER_ID}`;
    }, 500);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 py-16 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <h1 className="text-4xl font-extrabold mb-6 bg-gradient-to-r from-indigo-400 to-pink-500 text-transparent bg-clip-text">
          Contact Us
        </h1>
        <p className="text-lg text-gray-300 mb-12">
          Got questions or need help with <strong>Matchmaker Bot</strong>? Reach
          out to us below.
        </p>

        <div className="grid gap-6 md:grid-cols-3">
          {/* Message devdeej */}
          <a
            href={`discord://discord.com/users/${DISCORD_USER_ID}`}
            onClick={handleDiscordClick}
            className="flex flex-col items-center justify-center rounded-2xl bg-indigo-600 hover:bg-indigo-700 p-6 transition"
          >
            <MessageCircle className="w-10 h-10 mb-3" />
            <h3 className="font-semibold text-lg">Message devdeej</h3>
            <p className="text-sm text-gray-200 mt-2">DM the developer</p>
          </a>

          {/* Discord Server */}
          <Link
            href={DISCORD_SERVER_URL}
            target="_blank"
            className="flex flex-col items-center justify-center rounded-2xl bg-pink-600 hover:bg-pink-700 p-6 transition"
          >
            <Users className="w-10 h-10 mb-3" />
            <h3 className="font-semibold text-lg">Join the Server</h3>
            <p className="text-sm text-gray-200 mt-2">
              Get support & connect with others
            </p>
          </Link>

          {/* Email (optional backup) */}
          <a
            href="mailto:support@matchmakerbot.dev"
            className="flex flex-col items-center justify-center rounded-2xl bg-gray-800 hover:bg-gray-700 p-6 transition"
          >
            <Mail className="w-10 h-10 mb-3" />
            <h3 className="font-semibold text-lg">Email Support</h3>
            <p className="text-sm text-gray-200 mt-2">support@matchmakerbot.dev</p>
          </a>
        </div>
      </div>
    </div>
  );
}
