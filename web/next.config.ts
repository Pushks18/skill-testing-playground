import type { NextConfig } from "next";

// The API is served by in-app Route Handlers under app/api/**. (An earlier
// version proxied /api/* to a separate backend on :8080; that afterFiles
// rewrite shadowed the dynamic route handlers — e.g. /api/skills/[name] — so
// it has been removed now that the backend lives here.)
const nextConfig: NextConfig = {};

export default nextConfig;
