import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Header } from "@/components/header";
import "./globals.css";

export const metadata: Metadata = {
  title: "SMAT Scenario Explorer",
  description:
    "Explore merge scenarios, branch sources and analysis outputs from SMAT.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen">
        <Header />
        <main className="mx-auto w-full max-w-7xl px-4 pb-20 pt-8 sm:px-6 lg:px-8">
          {children}
        </main>
        <footer className="border-t border-white/5 py-8 text-center text-xs text-slate-500">
          SMAT-LLM · Scenario Explorer · leitura de{" "}
          <code className="font-mono text-slate-400">
            SMAT/output-test-dest
          </code>
        </footer>
      </body>
    </html>
  );
}
