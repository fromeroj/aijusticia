import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Justicia — Justicia precisa, verificable",
  description: "IA jurídica mexicana. Respuestas con citas verificadas contra fuentes oficiales.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#047857",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es-MX" className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full bg-white text-gray-900">{children}</body>
    </html>
  );
}
