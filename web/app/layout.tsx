import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { CellProvider } from "@/components/cell-provider";
import { Header } from "@/components/header";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Hired Hands",
    template: "%s · Hired Hands",
  },
  description:
    "A workcell of three robot arms that takes pick-and-place jobs from people and agents and settles every one on the XRP Ledger.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <CellProvider>
          <Header />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        </CellProvider>
      </body>
    </html>
  );
}
