"use client";

import { Mail, MessageSquare, Users } from "lucide-react";

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 to-black text-white py-16 px-6">
      <div className="max-w-4xl mx-auto space-y-12">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-5xl font-extrabold mb-4 bg-gradient-to-r from-indigo-400 to-purple-500 bg-clip-text text-transparent">
            Contact Us
          </h1>
          <p className="text-gray-400 text-lg">
            Got questions, feedback, or need help with Matchmaker Bot? Reach out below.
          </p>
        </div>

        {/* Contact Options */}
        <div className="grid gap-8 md:grid-cols-3">
          {/* Email */}
          <div className="bg-gray-800/50 rounded-2xl shadow-lg p-8 text-center hover:scale-105 transform transition">
            <Mail className="mx-auto h-12 w-12 text-indigo-400 mb-4" />
            <h2 className="text-xl font-bold mb-2">Email Us</h2>
            <p className="text-gray-400 text-sm mb-4">
              Get support or send feedback directly via email.
            </p>
            <a
              href="mailto:devdeej@example.com"
              className="inline-block bg-indigo-500 hover:bg-indigo-600 text-white font-semibold py-2 px-4 rounded-lg transition"
            >
              Send Email
            </a>
          </div>

          {/* DM Developer */}
          <div className="bg-gray-800/50 rounded-2xl shadow-lg p-8 text-center hover:scale-105 transform transition">
            <MessageSquare className="mx-auto h-12 w-12 text-purple-400 mb-4" />
            <h2 className="text-xl font-bold mb-2">Message DevDeej</h2>
            <p className="text-gray-400 text-sm mb-4">
              Have a direct question? DM the developer on Discord.
            </p>
            <a
              href="discord://-/users/154593850185351168"
              className="inline-block bg-purple-500 hover:bg-purple-600 text-white font-semibold py-2 px-4 rounded-lg transition"
            >
              Open in Discord
            </a>
          </div>

          {/* Join Server */}
          <div className="bg-gray-800/50 rounded-2xl shadow-lg p-8 text-center hover:scale-105 transform transition">
            <Users className="mx-auto h-12 w-12 text-green-400 mb-4" />
            <h2 className="text-xl font-bold mb-2">Join Our Server</h2>
            <p className="text-gray-400 text-sm mb-4">
              Chat with the community, share feedback, and stay updated.
            </p>
            <a
              href="https://discord.gg/7Cersw2kqv"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block bg-green-500 hover:bg-green-600 text-white font-semibold py-2 px-4 rounded-lg transition"
            >
              Join Server
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
