import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { NavBar } from "@/components/shell/nav-bar";

export const metadata: Metadata = {
  title: "VC Brain — Sourcing",
  description: "Detect founders before they show up in any startup database.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f5f5f7",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>
          <NavBar />
          <main className="pb-20">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
