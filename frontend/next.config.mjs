/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend rewrites: every /api/* call from the browser is proxied to the
  // FastAPI service. Override with NEXT_PUBLIC_API_URL in production.
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${api}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
