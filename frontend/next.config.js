/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Thumbnails are served as <img> tags from the backend (NEXT_PUBLIC_API_URL)
  // and external provider URLs; we do not use next/image optimization for them,
  // so no remotePatterns config is required.
};

module.exports = nextConfig;
