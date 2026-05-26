import { AppShell } from "@/components/layout/AppShell";
import { Placeholder } from "@/components/layout/Placeholder";

export default function CryptoPairsPage() {
  return (
    <AppShell market="crypto">
      <Placeholder
        title="암호화폐 페어 발견"
        subtitle="Crypto pair discovery"
        note="ccxt 어댑터 연결 후 활성화 예정. Binance · Bybit · Upbit 등을 지원합니다."
      />
    </AppShell>
  );
}
