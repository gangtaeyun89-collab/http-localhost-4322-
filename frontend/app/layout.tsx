import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "통계차익 자동매매 | Stat Arb",
  description:
    "공적분 페어 발견 · 백테스트 · 실시간 시그널 · 자동 주문 실행",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <body className="min-h-screen bg-bg-base text-text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
