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
        {children}
      </body>
    </html>
  );
}
