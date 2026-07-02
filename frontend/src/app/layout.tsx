import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "What If? — AI-Powered Video Podcast Platform",
  description:
    "Transform conversations into cinematic video podcasts. AI writes the script, produces the scenes, and distributes to YouTube — automatically.",
  openGraph: {
    title: "What If? — AI-Powered Video Podcast Platform",
    description: "Transform conversations into cinematic video podcasts.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`dark ${inter.variable}`} suppressHydrationWarning>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
