/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Thumbnails are served as <img> tags from the backend and external provider
  // URLs; we do not use next/image optimization for them.
  //
  // Proxy the API to the FastAPI backend so the whole app is same-origin. This
  // lets a single public URL (e.g. a tunnel to :3000) serve both the UI and the
  // API with no CORS setup — the browser only ever talks to this origin.
  async rewrites() {
    const backend = process.env.OMNI_BACKEND_ORIGIN || 'http://127.0.0.1:8000';
    return [
      { source: '/api/:path*', destination: `${backend}/api/:path*` },
      { source: '/health', destination: `${backend}/health` },
    ];
  },
};

module.exports = nextConfig;
