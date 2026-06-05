import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Skill Eval Platform",
  description: "Travel agent skill evaluation and leaderboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 font-mono antialiased">
        <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
          <span className="text-indigo-400 font-bold tracking-tight">Skill Eval</span>
          <Link href="/" className="text-sm text-gray-400 hover:text-white transition-colors">Leaderboard</Link>
          <Link href="/skills" className="text-sm text-gray-400 hover:text-white transition-colors">Skills</Link>
          <Link href="/eval" className="text-sm text-gray-400 hover:text-white transition-colors">Run Eval</Link>
          <Link href="/observability" className="text-sm text-gray-400 hover:text-white transition-colors">Observability</Link>
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
