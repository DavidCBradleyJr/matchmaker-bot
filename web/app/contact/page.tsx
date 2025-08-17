"use client";

import { MessageSquare, Users } from "lucide-react";

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white py-20 px-6">
      <div className="max-w-5xl mx-auto space-y-16">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-5xl font-extrabold mb-4 bg-gradient-to-r from-indigo-400 to-purple-500 bg-clip-text text-transparent">
            Contact Us
          </h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Need help, want to share feedback, or just want to chat?
            You can reach us directly on Discord.
          </p>
        </div>

        {/* Contact Options */}
        <div className="grid gap-8 md:grid-cols-2">
          {/* DM Developer */}
          <div className="bg-gray-800/50 backdrop-blur-md rounded-2xl shadow-lg p-10 text-center hover:scale-105 transform transition">
            <MessageSquare className="mx-auto h-14 w-14 text-purple-400 mb-6" />
            <h2 className="text-2xl font-bold mb-3">Message DevDeej</h2>
            <p className="text-gray-400 text-sm mb-6">
              Have a direct question? DM the developer instantly in Discord.
            </p>
            <a
              href="discord://-/users/123456789012345678"
              className="inline-block bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 px-6 rounded-xl transition"
            >
              Open in Discord App
            </a>
          </div>

          {/* Join Server */}
          <div className="bg-gray-800/50 backdrop-blur-md rounded-2xl shadow-lg p-10 text-center hover:scale-105 transform transition">
            <Users className="mx-auto h-14 w-14 text-green-400 mb-6" />
            <h2 className="text-2xl font-bold mb-3">Join Our Server</h2>
            <p className="text-gray-400 text-sm mb-6">
              Connect with the community, share feedback, and get updates.
            </p>
            <a
              href="https://discord.gg/7Cersw2kqv"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl transition"
            >
              Join Server
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
