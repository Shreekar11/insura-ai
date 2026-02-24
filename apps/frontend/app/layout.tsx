import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const everett = localFont({
  src: "./fonts/TWKEverett-Regular.woff2",
  weight: "400",
  style: "normal",
});

const siteUrl = "https://insura-ai-sepia.vercel.app/";

export const metadata: Metadata = {
  title: {
    default: "InsuraAI - AI-workspace for insurance operations",
    template: "%s | InsuraAI",
  },
  description:
    "InsuraAI is an AI-workspace built for insurance operations. Boost productivity, automate workflows, and optimize your insurance processes.",
  metadataBase: new URL(siteUrl),
  openGraph: {
    title: "InsuraAI - AI-workspace for insurance operations",
    description:
      "InsuraAI is an AI-workspace built for insurance operations. Boost productivity, automate workflows, and optimize your insurance processes.",
    type: "website",
    locale: "en_US",
    url: siteUrl,
    siteName: "InsuraAI",
    images: [
      {
        url: "https://ujrhkyqkoasuxcpfzeyr.supabase.co/storage/v1/object/sign/docs/readme-landing.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV9lMWM5MDlkZS03NWRlLTQ2NzYtOTAxYS02ODFkMjhiM2ViZjUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJkb2NzL3JlYWRtZS1sYW5kaW5nLnBuZyIsImlhdCI6MTc3MTkzMjI1MSwiZXhwIjoxODY2NTQwMjUxfQ._b14JVcqcNyai_cxFnkK-0ohVA9omPf4XXiT7-NIVYo",
        width: 1200,
        height: 630,
        alt: "InsuraAI - AI-workspace for insurance operations",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "InsuraAI - AI-workspace for insurance operations",
    description: "InsuraAI is an AI-workspace built for insurance operations.",
    images: [
      "https://ujrhkyqkoasuxcpfzeyr.supabase.co/storage/v1/object/sign/docs/readme-landing.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV9lMWM5MDlkZS03NWRlLTQ2NzYtOTAxYS02ODFkMjhiM2ViZjUiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJkb2NzL3JlYWRtZS1sYW5kaW5nLnBuZyIsImlhdCI6MTc3MTkzMjI1MSwiZXhwIjoxODY2NTQwMjUxfQ._b14JVcqcNyai_cxFnkK-0ohVA9omPf4XXiT7-NIVYo",
    ],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
    },
  },
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
      <body className={`${everett.className} antialiased`}>
        <QueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
