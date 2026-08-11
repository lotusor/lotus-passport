import { ProfileShell } from "@/components/ProfileShell";
import { SecurityView } from "@/components/profile/SecurityView";

export default function SecurityPage() {
  return (
    <ProfileShell
      title="安全设置"
      subtitle="集中管理你的身份认证方式。绑定通行密钥，让账户在面对密码泄露与钓鱼攻击时依然安全。"
    >
      <SecurityView />
    </ProfileShell>
  );
}
