import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Footer } from "@/components/shell/footer";
import { NavBar } from "@/components/shell/nav-bar";

export const metadata: Metadata = {
  title: "VC Brain",
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
