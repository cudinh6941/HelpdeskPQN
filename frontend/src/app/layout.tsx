import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { NavigationProgressProvider } from "@/components/NavigationProgress";

const sans = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "IT Helpdesk",
  description: "Hệ thống tiếp nhận và xử lý sự cố IT nội bộ",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={sans.variable} suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        <AuthProvider>
          <NavigationProgressProvider>{children}</NavigationProgressProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
