import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "project-preza",
  description: "Читает дизайн-систему презентации, переносит на неё новый контент.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Browser extensions (e.g. Yandex) inject attributes onto <html> before React
    // hydrates, which triggers a harmless hydration mismatch warning.
    <html lang="ru" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
