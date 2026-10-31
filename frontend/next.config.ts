import type { NextConfig } from "next";

// The browser calls /api/* on this origin; Next forwards it to the FastAPI backend.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default config;
