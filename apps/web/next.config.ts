import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    // The API listens on 18000 (docs, wizard port range). Port 8000 is a common default of other local projects, so the
    // proxy must never assume it. Read per call so a different origin can be set without rebuilding the config.
    const origin = (process.env.E2EAI_API_ORIGIN || "http://127.0.0.1:18000").replace(/\/+$/, "");
    return [
      {
        source: "/api/v1/:path*",
        destination: `${origin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
