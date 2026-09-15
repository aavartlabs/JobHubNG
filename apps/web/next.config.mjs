/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // In Docker, use the service name; fallback to localhost for local dev
    const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://jobhub-platform-api:8080';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
