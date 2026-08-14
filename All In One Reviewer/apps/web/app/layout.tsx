import type { Metadata } from "next";
import { QueryProvider } from "@/lib/query-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AndyHub — Study workspace",
  description: "A focused study instrument for turning course material into active recall.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
