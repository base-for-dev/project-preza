import type { Metadata } from "next";
import "./globals.css";
import { BOOT_SCRIPT } from "./lib/appearance";

export const metadata: Metadata = {
  title: "PREZA",
  description: "Читает дизайн-систему презентации, переносит на неё новый контент.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Browser extensions (e.g. Yandex) inject attributes onto <html> before React
    // hydrates, which triggers a harmless hydration mismatch warning.
    <html lang="ru" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
