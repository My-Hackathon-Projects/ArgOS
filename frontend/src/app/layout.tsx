import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Footer } from "@/components/shell/footer";
import { NavBar } from "@/components/shell/nav-bar";

// Self-hosted via next/font: identical rendering on macOS and Windows (no Segoe UI fallback).
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono" });

export const metadata: Metadata = {
  title: "ArgOS",
  description: "Detect founders before they show up in any startup database.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f6f5f1",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${inter.variable} ${display.variable} ${mono.variable}`}
    >
      <body className="min-h-full">
        <Providers>
          <div className="flex min-h-screen flex-col">
            <NavBar />
            <main className="flex-1 pb-20">{children}</main>
            <Footer />
          </div>
        </Providers>
      </body>
    </html>
  );
}
