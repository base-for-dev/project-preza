import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "project-preza",
  description: "Читает дизайн-систему презентации, переносит на неё новый контент.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
