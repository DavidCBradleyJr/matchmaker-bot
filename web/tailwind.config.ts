import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: process.env.NEXT_PUBLIC_PRIMARY_COLOR || "#6366F1"
      }
    }
  },
  plugins: []
} satisfies Config;