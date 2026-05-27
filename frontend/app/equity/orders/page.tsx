import { AppShell } from "@/components/layout/AppShell";
import { Placeholder } from "@/components/layout/Placeholder";

export default function Page() {
  return (
    <AppShell market="equity">
      <Placeholder title="orders" subtitle="equity / orders" note="곧 추가됩니다." />
    </AppShell>
  );
}
