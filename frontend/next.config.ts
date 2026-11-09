import type { NextConfig } from "next";

// Two builds from one codebase:
// - default: Next server that forwards /api/* to the FastAPI backend
// - NEXT_PUBLIC_ENGINE=browser: static site (GitHub Pages) where the Python
//   matcher runs in the browser with Pyodide
const browserEngine = process.env.NEXT_PUBLIC_ENGINE === "browser";
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const config: NextConfig = browserEngine
  ? { output: "export", basePath, images: { unoptimized: true }, trailingSlash: true }
  : {
      output: "standalone",
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
      },
    };

export default config;
