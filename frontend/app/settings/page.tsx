import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary">
        <ArrowLeft className="h-3 w-3" /> 홈으로
      </Link>
      <h1 className="mt-6 text-2xl font-semibold">설정 / Settings</h1>
      <p className="mt-2 text-sm text-text-secondary">언어 · 테마 · 브로커 · 거래소 API · 알림.</p>
      <div className="mt-8 rounded border border-border-subtle bg-bg-panel p-6">
        <div className="text-2xs uppercase tracking-widest text-text-muted">곧 추가됩니다</div>
        <p className="mt-2 text-sm text-text-secondary">FastAPI 백엔드 연결 후 API 키 보관, 알림 채널, 한국어/영어 토글이 들어갑니다.</p>
      </div>
    </div>
  );
}
