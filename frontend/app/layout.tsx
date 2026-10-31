import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trial Match: find clinical trials a patient qualifies for",
  description: "Describe a patient in plain English and see recruiting clinical trials, with every eligibility criterion checked and explained.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
