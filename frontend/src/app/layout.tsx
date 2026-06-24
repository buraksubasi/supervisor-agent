import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Supervisor Agent",
  description: "Multi-agent AI chat – YouTube RAG · SQL Agent · Browser Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="antialiased">{children}</body>
    </html>
  );
}
