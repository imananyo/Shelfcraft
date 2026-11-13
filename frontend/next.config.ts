import type { NextConfig } from "next";

// The browser only ever talks to this Next.js origin. /api/* is forwarded to the local
// FastAPI server, so provider API keys stay server-side and CORS is not needed.
const API_ORIGIN = process.env.SHELFCRAFT_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
        ],
      },
    ];
  },
  poweredByHeader: false,
  // Tailwind CSS v4 is compiled by its Turbopack loader (set up by create-next-app for Next 16).
  turbopack: {
    rules: {
      "*.css": { loaders: ["@tailwindcss/turbopack"], as: "*.css" },
    },
  },
};

export default nextConfig;
