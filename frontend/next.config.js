/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "pro.arcgis.com" },
      { protocol: "https", hostname: "desktop.arcgis.com" },
      { protocol: "https", hostname: "doc.esri.com" },
    ],
  },
};
module.exports = nextConfig;
