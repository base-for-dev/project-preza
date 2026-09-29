import type { NextConfig } from "next";

// `PREZA_STATIC=1` builds the site as plain files (apps/web/.next-static) that the API
// server, and so the desktop app and the `preza` command, serve themselves.
const staticBuild = process.env.PREZA_STATIC === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(staticBuild
    ? { output: "export", trailingSlash: true, distDir: ".next-static", images: { unoptimized: true } }
    : {}),
};

export default nextConfig;
