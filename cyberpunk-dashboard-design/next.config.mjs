/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: 'http',
        hostname: '127.0.0.1',
        port: '5000',
      },
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '5000',
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: '/backend/api/:path*',
        destination: 'http://127.0.0.1:5000/api/:path*',
      },
      {
        source: '/backend/latest_image',
        destination: 'http://127.0.0.1:5000/latest_image',
      },
      {
        source: '/backend/login',
        destination: 'http://127.0.0.1:5000/login',
      },
      {
        source: '/backend/register',
        destination: 'http://127.0.0.1:5000/register',
      },
      {
        source: '/backend/logout',
        destination: 'http://127.0.0.1:5000/logout',
      },
      {
        source: '/manager/:path*',
        destination: 'http://127.0.0.1:5005/:path*',
      },
    ]
  },
}

export default nextConfig
