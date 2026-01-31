import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const everett = localFont({
  src: "./fonts/TWKEverett-Regular.woff2",
  weight: "400",
  style: "normal",
});

export const metadata: Metadata = {
  title: "InsuraAI - AI-workspace for insurance operations",
  description: "InsuraAI is an AI-workspace for insurance operations",
};

import { AuthProvider } from "@/contexts/auth-context";
import { QueryProvider } from "@/components/providers/query-provider";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${everett.className} antialiased`}
      >
        <QueryProvider>
          <AuthProvider>
            {children}
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
