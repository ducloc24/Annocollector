import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    // The monorepo has lockfiles at both the root and here; pin the root so
    // Next.js does not warn about an inferred workspace root.
    root: path.resolve(__dirname),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
