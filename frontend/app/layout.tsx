import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { NavLinks } from "@/components/nav-links";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "BLUE LOBSTER",
  description: "Industrial Digital Twin Companion — Stage 3",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-background text-foreground antialiased`}>
        <div className="flex flex-col h-screen overflow-hidden">

          <header className="relative flex items-center justify-between px-4 h-12 border-b border-border bg-background shrink-0">
            <div className="flex items-center gap-3 shrink-0">
              <span className="font-semibold text-sm tracking-tight">
                BLUE LOBSTER
              </span>
            </div>

            <div className="absolute left-1/2 -translate-x-1/2">
              <NavLinks />
            </div>

            <div className="shrink-0 w-[120px]" />
          </header>

          <main className="flex-1 overflow-hidden">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
