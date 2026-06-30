import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Supervisor Agent",
  description: "Multi-agent AI chat – YouTube RAG · SQL Agent · Browser Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="antialiased flex flex-col h-screen bg-surface">
        <NavBar />
        <main className="flex-1 overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
