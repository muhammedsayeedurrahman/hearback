import type { NextConfig } from "next";

/** The dashboard is a pure client of the sidecar; it holds no truth state of its own. */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  // This repo keeps its own agent notes; the generated ones would only drift from them.
  agentRules: false,
};

export default nextConfig;
