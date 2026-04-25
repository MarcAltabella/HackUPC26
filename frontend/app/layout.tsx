import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { CopilotBar } from "@/components/copilot-bar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "HP Metal Jet S100 — Digital Co-Pilot",
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
        {/* Full-viewport column: top bar | content | bottom bar */}
        <div className="flex flex-col h-screen overflow-hidden">

          {/* ── Top bar: scenario selector + global machine status ── */}
          <header className="flex items-center justify-between px-4 h-12 border-b border-border bg-background shrink-0">
            <div className="flex items-center gap-3">
              <span className="font-semibold text-sm tracking-tight">
                HP Metal Jet S100
              </span>
              <span className="text-muted-foreground text-xs">Digital Co-Pilot</span>
            </div>

            {/* Scenario pill — wired to state in a later milestone */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                baseline_nominal · run 0
              </span>
            </div>
          </header>

          {/* ── Page content ── */}
          <main className="flex-1 overflow-hidden">
            {children}
          </main>

          {/* ── Persistent bottom prompt bar (prompt-kit PromptInput) ── */}
          <CopilotBar />
        </div>
      </body>
    </html>
  );
}
